"""Production-grade scan pipeline orchestrator.

Hardening guarantees:
  * Every step runs under a wall-clock timeout (concurrent.futures) so a
    hung scrape or LLM call cannot freeze the worker forever.
  * Transient errors retry with exponential backoff.
  * The job heartbeat is touched between steps so /health/pipeline and
    the dead-job sweeper can detect crashed workers.
  * Cancellation is honoured between every listing.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, List, Optional

from jobs.constants import (
    DEFAULT_STEP_TIMEOUT_SEC,
    JOB_CANCELLED,
    JOB_FAILED,
    JOB_RUNNING,
    JOB_SUCCESS,
    JOB_TIMEOUT,
    RETRY_BASE_DELAY_SEC,
    RETRY_MAX_DELAY_SEC,
    STEP_FAILED,
    STEP_SUCCESS,
    STEP_TIMEOUT,
    STEP_TIMEOUTS_SEC,
    WORKER_JOB_TIMEOUT_SEC,
)
from jobs.errors import StoreError
from jobs.logging_util import classify_error, format_traceback, get_logger
from jobs import store

from scraper import scrape_idealista_search_urls, scrape_listing_text
from extractor import extract_property_from_text
from economics import calculate_economics
from auto_scoring import calculate_auto_scores
from scoring import score_property
from memo import generate_ic_memo
from location import geocode_address
from excel_exporter import export_scan_to_excel


_step_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kua-step")


def _retry_delay(attempt: int) -> float:
    return min(RETRY_BASE_DELAY_SEC * (2 ** max(0, attempt - 1)), RETRY_MAX_DELAY_SEC)


def _step_timeout(step_key: str) -> int:
    return int(STEP_TIMEOUTS_SEC.get(step_key, DEFAULT_STEP_TIMEOUT_SEC))


def _run_with_retry(
    job_id: str,
    step_key: str,
    fn: Callable[[], Any],
    *,
    listing_index: Optional[int] = None,
    listing_url: Optional[str] = None,
    max_attempts: int = 3,
) -> Any:
    if listing_index is None:
        listing_index = store.JOB_LEVEL_INDEX
    log = get_logger(job_id, step_key)
    timeout_sec = _step_timeout(step_key)
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        step_row = store.start_step(job_id, step_key, listing_index=listing_index)
        store.touch_heartbeat(job_id)

        try:
            future = _step_executor.submit(fn)
            try:
                result = future.result(timeout=timeout_sec)
            except FuturesTimeout:
                # Best-effort cancel; the underlying thread may still run
                # but the worker continues with the next attempt/step.
                future.cancel()
                raise TimeoutError(
                    f"Step '{step_key}' exceeded {timeout_sec}s wall-clock timeout"
                )

            duration_ms = int((time.monotonic() - started) * 1000)
            store.finish_step(
                job_id,
                step_key,
                listing_index=listing_index,
                status=STEP_SUCCESS,
                output_data={"result": result} if not isinstance(result, dict) else result,
                duration_ms=duration_ms,
            )
            log.info("Step succeeded in %sms (attempt %s)", duration_ms, attempt)
            return result

        except Exception as exc:
            last_exc = exc
            duration_ms = int((time.monotonic() - started) * 1000)
            error_type, retryable = classify_error(exc)
            if isinstance(exc, TimeoutError):
                step_status = STEP_TIMEOUT
                retryable = True
            else:
                step_status = STEP_FAILED
            tb = format_traceback(exc)
            try:
                store.finish_step(
                    job_id,
                    step_key,
                    listing_index=listing_index,
                    status=step_status,
                    error_type=error_type,
                    error_message=str(exc),
                    traceback=tb,
                    retryable=retryable,
                    duration_ms=duration_ms,
                )
                store.record_error(
                    job_id,
                    step_id=step_row.get("id"),
                    listing_url=listing_url,
                    error_type=error_type,
                    message=str(exc),
                    traceback=tb,
                    retryable=retryable,
                    attempt=attempt,
                )
            except StoreError as store_exc:
                log.warning("Could not persist step failure: %s", store_exc)

            log.warning("Step failed attempt %s/%s: %s", attempt, max_attempts, exc)
            if not retryable or attempt >= max_attempts:
                raise
            time.sleep(_retry_delay(attempt))

    if last_exc:
        raise last_exc
    raise RuntimeError(f"Step {step_key} failed without exception")


# ---------------------------------------------------------------------------
# Lazy imports from main (avoid circular module load).
# ---------------------------------------------------------------------------
def _clean_property_data(data: dict) -> dict:
    from main import clean_property_data
    return clean_property_data(data)


def _is_valid_property_data(data: dict):
    from main import is_valid_property_data
    return is_valid_property_data(data)


def _assign_deal_status(score: dict) -> str:
    from main import assign_deal_status
    return assign_deal_status(score)


def _generate_rejection_note(property_data: dict, economics: dict, score: dict) -> str:
    from main import generate_rejection_note
    return generate_rejection_note(property_data, economics, score)


# ---------------------------------------------------------------------------
# Per-listing pipeline
# ---------------------------------------------------------------------------
def _process_listing(job_id: str, listing_index: int, url: str) -> dict:
    store.ensure_listing_steps(job_id, listing_index, url)
    store.upsert_listing_result(job_id, listing_index, url, status="running")

    def scrape():
        scraped = scrape_listing_text(url)
        if not scraped.get("success"):
            raise RuntimeError(scraped.get("error") or "Scrape failed")
        return scraped

    scraped = _run_with_retry(job_id, "scrape_listing", scrape, listing_index=listing_index, listing_url=url)
    raw_text = scraped.get("raw_text", "") if isinstance(scraped, dict) else ""

    def extract():
        data = extract_property_from_text(raw_text)
        if not isinstance(data, dict):
            data = {}
        data["listing_url"] = url
        return data

    extracted = _run_with_retry(
        job_id, "extract_property_data", extract, listing_index=listing_index, listing_url=url
    )

    def validate():
        cleaned = _clean_property_data(extracted)
        valid, err = _is_valid_property_data(cleaned)
        if not valid:
            raise ValueError(err or "Invalid extraction")
        return cleaned

    try:
        data = _run_with_retry(
            job_id, "validate_extraction", validate, listing_index=listing_index, listing_url=url
        )
    except Exception as exc:
        store.upsert_listing_result(
            job_id,
            listing_index,
            url,
            status="failed",
            error_message=str(exc),
            result={"success": False, "error": str(exc), "source_url": url},
        )
        return {"success": False, "error": str(exc), "source_url": url}

    def economics_step():
        full_address = (
            f"{data.get('address') or data.get('neighbourhood') or data.get('city')}, "
            f"{data.get('city')}, Spain"
        )
        coordinates = geocode_address(full_address) or {"lat": None, "lng": None}
        data["latitude"] = coordinates.get("lat")
        data["longitude"] = coordinates.get("lng")
        econ = calculate_economics(
            gba_m2=data.get("gba_m2"),
            rent_per_m2=data.get("rent_per_m2"),
            price_per_m2_nra=data.get("price_per_m2_nra"),
            nra_efficiency=data.get("nra_efficiency"),
            asking_price=data.get("asking_price"),
            asking_rent_month=data.get("asking_rent_month"),
        )
        return {"data": data, "economics": econ, "coordinates": coordinates}

    econ_out = _run_with_retry(
        job_id, "calculate_economics", economics_step, listing_index=listing_index, listing_url=url
    )
    data = econ_out["data"]
    economics = econ_out["economics"]

    def score_step():
        auto_scores = calculate_auto_scores(data, economics)
        final_score = score_property(
            {
                "extracted": data,
                "economics": economics,
                "auto_scores": auto_scores,
            }
        )
        return {"auto_scores": auto_scores, "final_score": final_score}

    score_out = _run_with_retry(
        job_id, "score_property", score_step, listing_index=listing_index, listing_url=url
    )
    final_score = score_out["final_score"]

    def classify():
        return _assign_deal_status(final_score)

    deal_status = _run_with_retry(
        job_id, "classify_deal", classify, listing_index=listing_index, listing_url=url
    )

    def memo_step():
        property_insert = {
            "source": "url_auto",
            "listing_url": data.get("listing_url"),
            "address": data.get("address"),
            "city": data.get("city"),
            "neighbourhood": data.get("neighbourhood"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "gba_m2": data.get("gba_m2"),
            "asking_price": data.get("asking_price"),
            "asking_rent_month": data.get("asking_rent_month"),
            "rent_per_m2": data.get("rent_per_m2"),
            "ceiling_height": data.get("ceiling_height"),
            "loading_access": data.get("loading_access"),
            "access_type": data.get("access_type"),
            "floor_level": data.get("floor_level"),
            "building_type": data.get("building_type"),
            "current_use": data.get("current_use"),
            "description": data.get("description"),
            "score": final_score.get("score"),
            "verdict": final_score.get("verdict"),
            "classification": final_score.get("classification"),
            "status": "analysed",
            "deal_status": deal_status,
        }
        if deal_status in ["approved_candidate", "manual_review"]:
            memo_text = generate_ic_memo(
                property_data=property_insert,
                economics=economics,
                score=final_score,
            )
        else:
            memo_text = _generate_rejection_note(property_insert, economics, final_score)
        return {"memo_text": memo_text, "property_insert": property_insert}

    memo_out = _run_with_retry(
        job_id, "generate_memo", memo_step, listing_index=listing_index, listing_url=url
    )
    memo_text = memo_out["memo_text"]
    property_insert = memo_out["property_insert"]

    def save_step():
        from database import supabase

        property_response = supabase.table("properties").insert(property_insert).execute()
        if not property_response.data:
            raise RuntimeError("Supabase did not return inserted property row")
        property_id = property_response.data[0]["id"]

        enriched_score = dict(final_score)
        auto_scores = score_out.get("auto_scores")
        if isinstance(auto_scores, dict) and "auto_scores" in auto_scores:
            enriched_score.setdefault("auto_scores", auto_scores.get("auto_scores"))

        analysis_insert = {
            "property_id": property_id,
            "input": data,
            "economics": economics,
            "score": enriched_score,
            "verdict": final_score.get("verdict"),
            "classification": final_score.get("classification"),
            "deal_killer": final_score.get("deal_killer"),
            "ic_memo": memo_text,
        }
        supabase.table("analyses").insert(analysis_insert).execute()

        try:
            store.save_extracted_property(
                job_id, url, property_id, data, economics, enriched_score
            )
            store.save_generated_memo(
                job_id, url, property_id, memo_text, final_score.get("verdict"), deal_status
            )
        except StoreError:
            # Pipeline tables missing is reported by /health/database; do not
            # block the core save path here.
            pass

        return {
            "property_id": property_id,
            "extracted": data,
            "economics": economics,
            "score": enriched_score,
            "deal_status": deal_status,
            "ic_memo": memo_text,
            "source_url": url,
            "success": True,
        }

    result = _run_with_retry(
        job_id, "save_to_supabase", save_step, listing_index=listing_index, listing_url=url
    )

    store.upsert_listing_result(
        job_id,
        listing_index,
        url,
        status="success",
        property_id=result.get("property_id"),
        deal_status=deal_status,
        score=final_score.get("score"),
        verdict=final_score.get("verdict"),
        result=result,
    )
    return result


# ---------------------------------------------------------------------------
# Top-level job runner
# ---------------------------------------------------------------------------
def run_job(job_id: str) -> dict:
    log = get_logger(job_id, "orchestrator")
    job = store.get_job(job_id)
    started = time.monotonic()
    worker_id = os.getenv("WORKER_ID") or f"worker-{os.getpid()}"

    if job.get("status") == JOB_CANCELLED:
        return store.build_job_response(job_id)

    try:
        search_url = job.get("search_url") or ""
        limit = int(job.get("listing_limit") or 10)
        generate_excel = bool(job.get("generate_excel", True))
        filters_used = job.get("filters") or {}

        if not search_url:
            raise ValueError("Job has no search_url")

        store.touch_heartbeat(job_id, worker_id)

        def collect_urls():
            scraped = scrape_idealista_search_urls(search_url, limit=limit)
            if not scraped.get("success"):
                raise RuntimeError(scraped.get("error") or "URL collection failed")
            urls = scraped.get("urls") or []
            return {"urls": urls, "count": len(urls)}

        collected = _run_with_retry(job_id, "collect_listing_urls", collect_urls)
        urls: List[str] = collected.get("urls") or []
        store.update_job(job_id, listings_total=len(urls), progress_pct=5)

        results: List[dict] = []
        approved = manual = rejected = failed = 0

        for idx, url in enumerate(urls):
            if time.monotonic() - started > WORKER_JOB_TIMEOUT_SEC:
                store.update_job(
                    job_id,
                    status=JOB_TIMEOUT,
                    error_message="Job exceeded global wall-clock timeout",
                    finished_at=store._now(),
                )
                log.warning("Job exceeded global timeout; stopping at idx=%s", idx)
                return store.build_job_response(job_id)

            current_job = store.get_job(job_id)
            if current_job.get("status") == JOB_CANCELLED:
                log.info("Job cancelled — stopping pipeline")
                store.update_job(job_id, finished_at=store._now())
                return store.build_job_response(job_id)

            store.touch_heartbeat(job_id, worker_id)

            try:
                result = _process_listing(job_id, idx, url)
                results.append(result)
                if result.get("success") and result.get("property_id"):
                    ds = result.get("deal_status")
                    if ds == "approved_candidate":
                        approved += 1
                    elif ds == "manual_review":
                        manual += 1
                    else:
                        rejected += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                err_result = {"success": False, "error": str(exc), "source_url": url}
                results.append(err_result)
                try:
                    store.upsert_listing_result(
                        job_id, idx, url, status="failed", error_message=str(exc), result=err_result
                    )
                except StoreError:
                    pass
                log.exception("Listing %s failed: %s", idx, exc)

            done = idx + 1
            pct = 5 + int((done / max(len(urls), 1)) * 85)
            try:
                store.update_job(
                    job_id,
                    listings_done=done,
                    listings_failed=failed,
                    approved_count=approved,
                    manual_review_count=manual,
                    rejected_count=rejected,
                    progress_pct=min(pct, 90),
                )
            except StoreError:
                pass

        # ----------------------------------------------------------------
        # Export artifacts (Excel, CSV, JSON, IC memo, ZIP) — non-fatal.
        # A failed export NEVER fails the scan. We log the failure and
        # continue so the user still gets a successful scan + UI cues that
        # they can retry the export from the frontend.
        # ----------------------------------------------------------------
        excel_path = None
        if generate_excel and results:
            from jobs.exports_service import generate_all_exports

            def export_step():
                outcome = generate_all_exports(job_id)
                # Bubble up storage path of the canonical Excel export if any.
                row = None
                try:
                    from jobs import exports_store
                    row = exports_store.get_export(job_id, "excel")
                except Exception:
                    row = None
                return {
                    "outcome": outcome,
                    "excel_path": (row or {}).get("file_path") if row else None,
                }

            try:
                export_out = _run_with_retry(
                    job_id,
                    "export_artifacts",
                    export_step,
                    max_attempts=1,  # Don't retry: we already retry per-format internally.
                )
                if isinstance(export_out, dict):
                    excel_path = export_out.get("excel_path")
            except Exception as exc:
                log.warning("Export artifacts step failed (non-fatal): %s", exc)
                try:
                    store.record_error(
                        job_id,
                        error_type="ExportError",
                        message=str(exc)[:1000],
                        traceback=format_traceback(exc),
                        retryable=True,
                    )
                except Exception:
                    pass

        def notify():
            return {"notified": True, "listings": len(results)}

        try:
            _run_with_retry(job_id, "notify_frontend", notify)
        except Exception:
            # notification is best-effort
            pass

        final_status = JOB_SUCCESS if results else JOB_FAILED
        store.update_job(
            job_id,
            status=final_status,
            progress_pct=100,
            excel_path=excel_path,
            finished_at=store._now(),
            result_summary={
                "scanned_count": len(results),
                "approved_candidates_count": approved,
                "manual_review_count": manual,
                "rejected_count": rejected + failed,
                "top_deals_count": approved + manual,
            },
        )
        log.info("Job completed status=%s listings=%s", final_status, len(results))
        return store.build_job_response(job_id)

    except Exception as exc:
        log.exception("Job failed: %s", exc)
        try:
            store.update_job(
                job_id,
                status=JOB_FAILED,
                error_message=str(exc)[:1000],
                finished_at=store._now(),
            )
            store.record_error(
                job_id,
                error_type=type(exc).__name__,
                message=str(exc),
                traceback=format_traceback(exc),
                retryable=False,
            )
        except Exception:
            pass
        raise
