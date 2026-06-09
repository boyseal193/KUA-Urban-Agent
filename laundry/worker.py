"""Laundry async scan worker.

Called by ``jobs.orchestrator.run_job`` whenever the storage worker loop
picks up a ``scan_jobs`` row with ``job_type='laundry_scan'``. Mirrors the
storage worker's semantics (heartbeats, cancel, step rows, listing rows)
so the existing UI components render laundry runs without modification.

End-to-end pipeline
-------------------
    1. ingest_inputs       — parse the queued payload
    2. discover_urls       — when search_type is automatic_scan / area_search
    3. underwrite_listings — per-listing pipeline + persistence
    4. summarize           — write final counters / status

Status transitions written into ``scan_jobs.status``:
    queued → running → success      (>=1 listing scored)
    queued → running → no_results   (worker ran, discovered/processed 0)
    queued → running → failed       (unrecoverable error)
    queued → running → cancelled    (operator cancelled mid-run)
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback as _tb
from typing import Any, Dict, List, Optional, Tuple

from jobs import store as job_store
from jobs.constants import JOB_CANCELLED, JOB_FAILED, JOB_RUNNING, JOB_SUCCESS

from laundry import pipeline, scanner, store as laundry_store

log = logging.getLogger("kua.laundry.worker")

JOB_NO_RESULTS = "no_results"  # custom status for "ran cleanly but found 0 listings"

# Search types that mean "the URL is a search-results page, discover children".
AREA_SEARCH_TYPES = {"area_search", "automatic_scan"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        try: payload = json.loads(payload)
        except Exception: payload = {}
    return payload if isinstance(payload, dict) else {}


def _detect_mode(*, listing_url: Optional[str], raw_text: Optional[str],
                  search_type: str) -> str:
    """Return one of: 'inline_text', 'area_discover', 'single_listing'."""
    if raw_text and not listing_url:
        return "inline_text"
    if listing_url and search_type in AREA_SEARCH_TYPES:
        return "area_discover"
    return "single_listing"


def _classify_result(res: Dict[str, Any]) -> str:
    """Bucket a pipeline analyse_url/analyse_listing result into one of:
    'approved', 'manual_review', 'rejected', 'skipped', 'failed'."""
    if not isinstance(res, dict): return "failed"
    if not res.get("success"): return "failed"
    if res.get("skipped"): return "skipped"
    ds = (res.get("scoring") or {}).get("deal_status")
    if ds == "approved_candidate": return "approved"
    if ds == "manual_review": return "manual_review"
    return "rejected"


# ---------------------------------------------------------------------------
# Worker entrypoint
# ---------------------------------------------------------------------------
def run_laundry_scan(job_id: str) -> Dict[str, Any]:
    started = time.monotonic()
    worker_id = os.getenv("WORKER_ID") or f"laundry-worker-{os.getpid()}"

    try:
        job = job_store.get_job(job_id)
    except Exception as exc:
        log.exception("Could not load job %s: %s", job_id, exc)
        return {"success": False, "error": f"job_load_failed: {exc}", "job_id": job_id}

    if (job.get("status") or "").lower() == "cancelled":
        return {"success": True, "skipped": "cancelled", "job_id": job_id}

    payload = _safe_payload(job)
    filters = payload.get("filters") or {}
    overrides = payload.get("overrides") or {}
    listing_url = payload.get("url") or job.get("search_url") or None
    raw_text = payload.get("raw_text")
    use_llm = bool(payload.get("use_llm_extraction", True))
    listing_limit = max(int(payload.get("listing_limit") or job.get("listing_limit") or 10), 1)
    search_type = (payload.get("search_type") or filters.get("search_type") or "manual_url").lower()

    log.info(
        "laundry.scan start job_id=%s mode=%s search_type=%s url=%s text_len=%s limit=%s",
        job_id, _detect_mode(listing_url=listing_url, raw_text=raw_text, search_type=search_type),
        search_type, listing_url, len(raw_text or ""), listing_limit,
    )

    # Mark job running + first heartbeat
    laundry_store.update_job(
        job_id,
        status=JOB_RUNNING,
        started_at=job_store._now(),
        worker_id=worker_id,
        progress_pct=2,
        error_message=None,
    )
    try:
        job_store.touch_heartbeat(job_id, worker_id)
    except Exception:
        pass

    counters = {"done": 0, "total": 0, "approved": 0, "manual_review": 0, "rejected": 0, "failed": 0, "skipped": 0}
    results: List[Dict[str, Any]] = []

    try:
        # ----------------------------------------------------------------
        # STEP 1 — ingest
        # ----------------------------------------------------------------
        laundry_store.start_step(job_id, laundry_store.JOB_STEP_INGEST)
        if not listing_url and not raw_text:
            laundry_store.finish_step(
                job_id, laundry_store.JOB_STEP_INGEST,
                status=laundry_store.STEP_FAILED,
                error_message="No listing_url, search URL or raw text supplied",
            )
            _finalize_no_results(job_id, reason="No URL or raw text supplied", counters=counters)
            return _final_response(job_id, JOB_NO_RESULTS)
        laundry_store.finish_step(
            job_id, laundry_store.JOB_STEP_INGEST, status=laundry_store.STEP_SUCCESS,
            output={"listing_url": listing_url, "has_text": bool(raw_text), "search_type": search_type},
        )
        log.info("laundry.scan step=ingest_inputs OK job_id=%s", job_id)

        mode = _detect_mode(listing_url=listing_url, raw_text=raw_text, search_type=search_type)

        # ----------------------------------------------------------------
        # STEP 2 — discover (when applicable)
        # ----------------------------------------------------------------
        listing_targets: List[Tuple[Optional[str], Optional[str]]] = []  # (url, raw_text)

        if mode == "inline_text":
            laundry_store.finish_step(
                job_id, laundry_store.JOB_STEP_DISCOVER, status=laundry_store.STEP_SKIPPED,
                output={"reason": "inline_text_only"},
            )
            listing_targets = [(None, raw_text)]
        elif mode == "single_listing":
            laundry_store.finish_step(
                job_id, laundry_store.JOB_STEP_DISCOVER, status=laundry_store.STEP_SKIPPED,
                output={"reason": "single_listing_url"},
            )
            listing_targets = [(listing_url, None)]
        else:  # area_discover
            laundry_store.start_step(job_id, laundry_store.JOB_STEP_DISCOVER,
                                       listing_url=listing_url)
            try:
                urls = scanner.discover_listing_urls(listing_url, limit=listing_limit)
            except Exception as exc:
                log.exception("URL discovery crashed: %s", exc)
                laundry_store.finish_step(
                    job_id, laundry_store.JOB_STEP_DISCOVER,
                    status=laundry_store.STEP_FAILED,
                    error_type=type(exc).__name__, error_message=str(exc),
                )
                _finalize_failed(job_id, error=f"discovery_crashed: {exc}", counters=counters)
                return _final_response(job_id, JOB_FAILED)

            log.info("laundry.scan step=discover_urls discovered=%s job_id=%s", len(urls), job_id)
            laundry_store.finish_step(
                job_id, laundry_store.JOB_STEP_DISCOVER,
                status=laundry_store.STEP_SUCCESS if urls else laundry_store.STEP_FAILED,
                output={"discovered_count": len(urls), "search_url": listing_url, "urls": urls[:20]},
                error_message=None if urls else "No listings discovered from the generated search URL.",
            )
            if not urls:
                _finalize_no_results(
                    job_id,
                    reason=(
                        "Generated search URL returned 0 listings. "
                        "Try widening the filters (max size, neighbourhoods) or use Area Search "
                        "with a custom URL."
                    ),
                    counters=counters,
                )
                # Skip the underwrite + summary placeholders by marking them
                laundry_store.finish_step(job_id, laundry_store.JOB_STEP_UNDERWRITE,
                                            status=laundry_store.STEP_SKIPPED)
                laundry_store.finish_step(job_id, laundry_store.JOB_STEP_SUMMARY,
                                            status=laundry_store.STEP_SUCCESS,
                                            output={"reason": "no_listings_to_score"})
                return _final_response(job_id, JOB_NO_RESULTS)

            listing_targets = [(u, None) for u in urls[:listing_limit]]

        # ----------------------------------------------------------------
        # STEP 3 — underwrite each listing
        # ----------------------------------------------------------------
        counters["total"] = len(listing_targets)
        laundry_store.set_job_counters(job_id, listings_total=counters["total"], progress_pct=10)
        laundry_store.start_step(job_id, laundry_store.JOB_STEP_UNDERWRITE)

        for idx, (url, text) in enumerate(listing_targets):
            # Cancellation check between listings
            if laundry_store.is_job_cancelled(job_id):
                log.info("laundry.scan cancelled mid-run job_id=%s after=%s", job_id, idx)
                laundry_store.finish_step(job_id, laundry_store.JOB_STEP_UNDERWRITE,
                                            status=laundry_store.STEP_SKIPPED,
                                            output={"cancelled_after": idx})
                laundry_store.update_job(job_id, status="cancelled", finished_at=job_store._now())
                return _final_response(job_id, "cancelled")

            try:
                job_store.touch_heartbeat(job_id, worker_id)
            except Exception:
                pass

            laundry_store.start_step(
                job_id, laundry_store.LISTING_STEP_PROCESS,
                listing_index=idx, listing_url=url,
            )
            step_started = time.monotonic()

            try:
                if text and not url:
                    res = pipeline.analyse_listing(
                        raw_text=text, listing_url=None, source="manual_text",
                        overrides=overrides, filters=filters, use_llm=use_llm,
                        job_id=job_id, persist=True,
                    )
                else:
                    res = pipeline.analyse_url(
                        url=url, overrides=overrides, filters=filters,
                        use_llm=use_llm, job_id=job_id, persist=True,
                    )
            except Exception as exc:
                log.exception("Listing %s failed: %s", url or "<inline>", exc)
                res = {"success": False, "url": url, "error": str(exc),
                        "traceback": _tb.format_exc(limit=8)}

            bucket = _classify_result(res)
            counters[bucket] = counters.get(bucket, 0) + 1
            counters["done"] = idx + 1
            results.append(res)

            laundry_store.record_listing_result(
                job_id, idx,
                listing_url=url,
                status=("success" if res.get("success") and not res.get("skipped") else
                        "skipped" if res.get("skipped") else "failed"),
                property_id=res.get("property_id"),
                deal_status=(res.get("scoring") or {}).get("deal_status"),
                score=(res.get("scoring") or {}).get("score"),
                error_message=res.get("error") or res.get("reason"),
                result={
                    "verdict": (res.get("scoring") or {}).get("verdict"),
                    "classification": (res.get("scoring") or {}).get("classification"),
                    "preferred_market": (res.get("scoring") or {}).get("preferred_market"),
                    "address": (res.get("extracted") or {}).get("address"),
                    "floor_area_m2": (res.get("economics") or {}).get("floor_area_m2"),
                    "ebitda_eur": (res.get("economics") or {}).get("ebitda_eur"),
                    "payback_years": (res.get("economics") or {}).get("payback_years"),
                },
            )

            step_ms = int((time.monotonic() - step_started) * 1000)
            listing_status = (
                laundry_store.STEP_SUCCESS if res.get("success") and not res.get("skipped")
                else laundry_store.STEP_SKIPPED if res.get("skipped")
                else laundry_store.STEP_FAILED
            )
            laundry_store.finish_step(
                job_id, laundry_store.LISTING_STEP_PROCESS,
                listing_index=idx, status=listing_status,
                error_type=(None if res.get("success") else type(res.get("error", "Error")).__name__),
                error_message=res.get("error"),
                duration_ms=step_ms,
                output={"deal_status": (res.get("scoring") or {}).get("deal_status"),
                         "score": (res.get("scoring") or {}).get("score")},
            )

            progress = 10 + int(((idx + 1) / max(counters["total"], 1)) * 80)
            laundry_store.set_job_counters(
                job_id,
                listings_done=counters["done"],
                listings_failed=counters["failed"],
                approved_count=counters["approved"],
                manual_review_count=counters["manual_review"],
                rejected_count=counters["rejected"],
                progress_pct=min(progress, 95),
            )
            log.info(
                "laundry.scan listing %s/%s url=%s bucket=%s score=%s ms=%s",
                idx + 1, counters["total"], url, bucket,
                (res.get("scoring") or {}).get("score"), step_ms,
            )

        laundry_store.finish_step(
            job_id, laundry_store.JOB_STEP_UNDERWRITE,
            status=laundry_store.STEP_SUCCESS,
            output={k: counters[k] for k in ("approved", "manual_review", "rejected", "failed", "skipped")},
        )

        # ----------------------------------------------------------------
        # STEP 4 — summarize
        # ----------------------------------------------------------------
        laundry_store.start_step(job_id, laundry_store.JOB_STEP_SUMMARY)
        scored_anything = (counters["approved"] + counters["manual_review"] + counters["rejected"]) > 0
        final_status = JOB_SUCCESS if scored_anything else JOB_NO_RESULTS

        summary = {
            "approved_count": counters["approved"],
            "manual_review_count": counters["manual_review"],
            "rejected_count": counters["rejected"],
            "failed_count": counters["failed"],
            "skipped_count": counters["skipped"],
            "total": counters["total"],
            "elapsed_sec": round(time.monotonic() - started, 2),
        }
        laundry_store.finish_step(
            job_id, laundry_store.JOB_STEP_SUMMARY,
            status=laundry_store.STEP_SUCCESS, output=summary,
        )
        laundry_store.update_job(
            job_id,
            status=final_status,
            progress_pct=100,
            finished_at=job_store._now(),
            error_message=(None if scored_anything else
                            "Worker processed listings but every one was skipped or failed to score."),
        )
        log.info(
            "laundry.scan finished job_id=%s status=%s approved=%s review=%s rejected=%s failed=%s",
            job_id, final_status, counters["approved"], counters["manual_review"],
            counters["rejected"], counters["failed"],
        )
        return _final_response(job_id, final_status)

    except Exception as exc:
        log.exception("Laundry worker crashed: %s", exc)
        _finalize_failed(job_id, error=str(exc)[:1000], counters=counters)
        return _final_response(job_id, JOB_FAILED)


# ---------------------------------------------------------------------------
# Status finalization helpers
# ---------------------------------------------------------------------------
def _finalize_no_results(job_id: str, *, reason: str, counters: Dict[str, int]) -> None:
    laundry_store.set_job_counters(
        job_id,
        listings_total=counters.get("total", 0),
        listings_done=counters.get("done", 0),
        listings_failed=counters.get("failed", 0),
        approved_count=counters.get("approved", 0),
        manual_review_count=counters.get("manual_review", 0),
        rejected_count=counters.get("rejected", 0),
        progress_pct=100,
    )
    laundry_store.update_job(
        job_id, status=JOB_NO_RESULTS, finished_at=job_store._now(),
        error_message=reason,
    )


def _finalize_failed(job_id: str, *, error: str, counters: Dict[str, int]) -> None:
    laundry_store.set_job_counters(
        job_id,
        listings_total=counters.get("total", 0),
        listings_done=counters.get("done", 0),
        listings_failed=counters.get("failed", 0),
        approved_count=counters.get("approved", 0),
        manual_review_count=counters.get("manual_review", 0),
        rejected_count=counters.get("rejected", 0),
        progress_pct=100,
    )
    laundry_store.update_job(
        job_id, status=JOB_FAILED, finished_at=job_store._now(),
        error_message=error,
    )


def _final_response(job_id: str, status: str) -> Dict[str, Any]:
    return {"success": status in (JOB_SUCCESS, JOB_NO_RESULTS), "job_id": job_id, "status": status}
