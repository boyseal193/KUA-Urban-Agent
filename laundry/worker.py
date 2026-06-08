"""Laundry async scan worker.

Called by ``jobs.orchestrator.run_job`` whenever it picks up a ``scan_jobs``
row with ``job_type='laundry_scan'``. Keeps the same heartbeat / cancel /
status semantics as the storage worker so existing UI hooks (poll job state,
cancel, etc.) work without modification.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

from jobs import store as job_store
from jobs.constants import JOB_CANCELLED, JOB_FAILED, JOB_RUNNING, JOB_SUCCESS

from laundry import pipeline, store as laundry_store

log = logging.getLogger("kua.laundry.worker")


def _safe_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        import json
        try: payload = json.loads(payload)
        except Exception: payload = {}
    return payload if isinstance(payload, dict) else {}


def run_laundry_scan(job_id: str) -> Dict[str, Any]:
    job = job_store.get_job(job_id)
    started = time.monotonic()
    worker_id = os.getenv("WORKER_ID") or f"laundry-worker-{os.getpid()}"

    if job.get("status") == JOB_CANCELLED:
        return job_store.build_job_response(job_id)

    payload = _safe_payload(job)
    filters = payload.get("filters") or {}
    overrides = payload.get("overrides") or {}
    listing_url = payload.get("url") or job.get("search_url") or None
    raw_text = payload.get("raw_text")
    use_llm = bool(payload.get("use_llm_extraction", True))
    limit = int(payload.get("listing_limit") or job.get("listing_limit") or 10)
    search_type = (payload.get("search_type") or filters.get("search_type") or "").lower()

    try:
        job_store.update_job(job_id, status=JOB_RUNNING, started_at=job_store._now(),
                              worker_id=worker_id, progress_pct=5)
        job_store.touch_heartbeat(job_id, worker_id)
    except Exception as exc:
        log.warning("Failed to mark job as running: %s", exc)

    try:
        results: List[Dict[str, Any]] = []
        approved = manual = rejected = failed = skipped = 0

        if raw_text and not listing_url:
            res = pipeline.analyse_listing(
                raw_text=raw_text, listing_url=None, source="manual_text",
                overrides=overrides, filters=filters, use_llm=use_llm,
                job_id=job_id, persist=True,
            )
            results = [res]
        elif listing_url and search_type == "area_search":
            area = pipeline.analyse_area(
                search_url=listing_url, limit=limit, overrides=overrides,
                filters=filters, job_id=job_id,
            )
            results = area.get("results") or []
            approved = area["summary"]["approved"]; manual = area["summary"]["manual_review"]
            rejected = area["summary"]["rejected"]; skipped = area["summary"]["skipped"]
            failed = area["summary"]["failed"]
        elif listing_url:
            res = pipeline.analyse_url(
                url=listing_url, overrides=overrides, filters=filters,
                use_llm=use_llm, job_id=job_id, persist=True,
            )
            results = [res]
        else:
            raise ValueError("Job has neither a URL nor raw_text payload")

        for res in results:
            if not isinstance(res, dict): continue
            if res.get("skipped"): skipped += 1; continue
            if not res.get("success"): failed += 1; continue
            ds = (res.get("scoring") or {}).get("deal_status")
            if ds == "approved_candidate": approved += 1
            elif ds == "manual_review": manual += 1
            else: rejected += 1

        final = {
            "success": True,
            "summary": {
                "approved": approved, "manual_review": manual,
                "rejected": rejected, "skipped": skipped, "failed": failed,
                "total": len(results),
            },
            "results": results,
            "elapsed_sec": round(time.monotonic() - started, 2),
        }

        try:
            job_store.update_job(
                job_id, status=JOB_SUCCESS, progress_pct=100,
                finished_at=job_store._now(),
                listings_total=len(results),
                listings_processed=len(results),
                summary=final["summary"],
            )
        except Exception as exc:
            log.warning("Failed to mark job as success (telemetry only): %s", exc)
            try:
                job_store.update_job(job_id, status=JOB_SUCCESS, progress_pct=100,
                                      finished_at=job_store._now())
            except Exception:
                pass

        try:
            return job_store.build_job_response(job_id)
        except Exception:
            return final
    except Exception as exc:
        log.exception("Laundry scan failed: %s", exc)
        try:
            job_store.update_job(job_id, status=JOB_FAILED, error_message=str(exc)[:1000],
                                  finished_at=job_store._now())
        except Exception:
            pass
        try:
            return job_store.build_job_response(job_id)
        except Exception:
            return {"success": False, "error": str(exc), "job_id": job_id}
