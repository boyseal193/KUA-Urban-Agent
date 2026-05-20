"""Supabase persistence layer for async scan jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import supabase
from jobs.constants import (
    JOB_QUEUED,
    JOB_RUNNING,
    PIPELINE_STEPS,
    STEP_PENDING,
    STEP_RUNNING,
    STEP_SUCCESS,
    STEP_FAILED,
    STEP_SKIPPED,
)
from jobs.logging_util import format_traceback, get_logger, safe_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(job_id: str, level: str, message: str, step_id: Optional[str] = None, context: Optional[dict] = None):
    supabase.table("scan_logs").insert({
        "job_id": job_id,
        "step_id": step_id,
        "level": level,
        "message": message,
        "context": safe_json(context or {}),
    }).execute()


def create_job(
    *,
    job_type: str,
    search_url: str,
    filters: dict,
    listing_limit: int,
    generate_excel: bool,
    created_by: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    job_id = str(uuid.uuid4())
    row = {
        "id": job_id,
        "job_type": job_type,
        "status": JOB_QUEUED,
        "created_by": created_by,
        "search_url": search_url,
        "filters": filters,
        "listing_limit": listing_limit,
        "generate_excel": generate_excel,
        "request_id": request_id or job_id,
        "started_at": None,
        "finished_at": None,
    }
    supabase.table("scan_jobs").insert(row).execute()

    # Seed job-level steps
    for order, step_key in enumerate(PIPELINE_STEPS):
        supabase.table("scan_steps").insert({
            "job_id": job_id,
            "listing_index": None,
            "step_key": step_key,
            "step_order": order,
            "status": STEP_PENDING,
        }).execute()

    _log(job_id, "info", "Job created and queued", context={"search_url": search_url})
    return get_job(job_id)


def get_job(job_id: str) -> dict:
    res = supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute()
    if not res.data:
        raise KeyError(f"Job not found: {job_id}")
    return res.data[0]


def list_jobs(limit: int = 20) -> List[dict]:
    res = (
        supabase.table("scan_jobs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def claim_next_job() -> Optional[dict]:
    """Atomically claim the oldest queued job."""
    res = (
        supabase.table("scan_jobs")
        .select("*")
        .eq("status", JOB_QUEUED)
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    job = res.data[0]
    job_id = job["id"]

    updated = (
        supabase.table("scan_jobs")
        .update({"status": JOB_RUNNING, "started_at": _now()})
        .eq("id", job_id)
        .eq("status", JOB_QUEUED)
        .execute()
    )
    if not updated.data:
        return None
    _log(job_id, "info", "Job claimed by worker")
    return updated.data[0]


def update_job(job_id: str, **fields) -> dict:
    fields["updated_at"] = _now()
    res = supabase.table("scan_jobs").update(fields).eq("id", job_id).execute()
    return res.data[0] if res.data else get_job(job_id)


def get_steps(job_id: str, listing_index: Optional[int] = None) -> List[dict]:
    q = supabase.table("scan_steps").select("*").eq("job_id", job_id)
    if listing_index is None:
        q = q.is_("listing_index", "null")
    else:
        q = q.eq("listing_index", listing_index)
    res = q.order("step_order").execute()
    return res.data or []


def ensure_listing_steps(job_id: str, listing_index: int, listing_url: str) -> None:
    from jobs.constants import LISTING_LEVEL_STEPS

    existing = (
        supabase.table("scan_steps")
        .select("id")
        .eq("job_id", job_id)
        .eq("listing_index", listing_index)
        .limit(1)
        .execute()
    )
    if existing.data:
        return

    base_order = 100 + listing_index * len(LISTING_LEVEL_STEPS)
    for i, step_key in enumerate(LISTING_LEVEL_STEPS):
        supabase.table("scan_steps").insert({
            "job_id": job_id,
            "listing_index": listing_index,
            "listing_url": listing_url,
            "step_key": step_key,
            "step_order": base_order + i,
            "status": STEP_PENDING,
        }).execute()


def start_step(job_id: str, step_key: str, listing_index: Optional[int] = None) -> dict:
    q = (
        supabase.table("scan_steps")
        .select("*")
        .eq("job_id", job_id)
        .eq("step_key", step_key)
    )
    if listing_index is None:
        q = q.is_("listing_index", "null")
    else:
        q = q.eq("listing_index", listing_index)
    res = q.limit(1).execute()
    if not res.data:
        raise KeyError(f"Step not found: {step_key}")
    step = res.data[0]
    attempt = int(step.get("attempt") or 0) + 1
    updated = (
        supabase.table("scan_steps")
        .update({
            "status": STEP_RUNNING,
            "attempt": attempt,
            "started_at": _now(),
            "error_message": None,
            "error_type": None,
        })
        .eq("id", step["id"])
        .execute()
    )
    update_job(job_id, current_step=step_key)
    return updated.data[0] if updated.data else step


def finish_step(
    job_id: str,
    step_key: str,
    *,
    listing_index: Optional[int] = None,
    status: str = STEP_SUCCESS,
    output_data: Optional[dict] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    retryable: bool = True,
    duration_ms: Optional[int] = None,
) -> dict:
    q = supabase.table("scan_steps").select("id").eq("job_id", job_id).eq("step_key", step_key)
    if listing_index is None:
        q = q.is_("listing_index", "null")
    else:
        q = q.eq("listing_index", listing_index)
    res = q.limit(1).execute()
    if not res.data:
        raise KeyError(f"Step not found: {step_key}")
    step_id = res.data[0]["id"]
    payload = {
        "status": status,
        "finished_at": _now(),
        "output_data": safe_json(output_data) if output_data else None,
        "error_type": error_type,
        "error_message": error_message,
        "retryable": retryable,
        "duration_ms": duration_ms,
    }
    updated = supabase.table("scan_steps").update(payload).eq("id", step_id).execute()
    return updated.data[0] if updated.data else {}


def record_error(
    job_id: str,
    *,
    step_id: Optional[str] = None,
    listing_url: Optional[str] = None,
    error_type: str,
    message: str,
    traceback: Optional[str] = None,
    retryable: bool = True,
    attempt: int = 1,
) -> None:
    supabase.table("scan_errors").insert({
        "job_id": job_id,
        "step_id": step_id,
        "listing_url": listing_url,
        "error_type": error_type,
        "message": message,
        "traceback": traceback,
        "retryable": retryable,
        "attempt": attempt,
    }).execute()
    _log(job_id, "error", message, step_id=step_id, context={"error_type": error_type})


def upsert_listing_result(job_id: str, listing_index: int, listing_url: str, **fields) -> dict:
    existing = (
        supabase.table("scan_listing_results")
        .select("id")
        .eq("job_id", job_id)
        .eq("listing_index", listing_index)
        .limit(1)
        .execute()
    )
    payload = {
        "job_id": job_id,
        "listing_index": listing_index,
        "listing_url": listing_url,
        **fields,
    }
    if existing.data:
        res = (
            supabase.table("scan_listing_results")
            .update(payload)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        res = supabase.table("scan_listing_results").insert(payload).execute()
    return res.data[0] if res.data else payload


def get_listing_results(job_id: str) -> List[dict]:
    res = (
        supabase.table("scan_listing_results")
        .select("*")
        .eq("job_id", job_id)
        .order("listing_index")
        .execute()
    )
    return res.data or []


def get_logs(job_id: str, limit: int = 100) -> List[dict]:
    res = (
        supabase.table("scan_logs")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_errors(job_id: str, limit: int = 50) -> List[dict]:
    res = (
        supabase.table("scan_errors")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def save_extracted_property(job_id: str, listing_url: str, property_id: Optional[str], extracted: dict, economics: Optional[dict], score: Optional[dict]) -> None:
    supabase.table("extracted_properties").insert({
        "job_id": job_id,
        "listing_url": listing_url,
        "property_id": property_id,
        "extracted": safe_json(extracted),
        "economics": safe_json(economics) if economics else None,
        "score": safe_json(score) if score else None,
    }).execute()


def save_generated_memo(job_id: str, listing_url: str, property_id: Optional[str], memo_text: str, verdict: Optional[str], deal_status: Optional[str]) -> None:
    supabase.table("generated_memos").insert({
        "job_id": job_id,
        "listing_url": listing_url,
        "property_id": property_id,
        "memo_text": memo_text,
        "verdict": verdict,
        "deal_status": deal_status,
    }).execute()


def build_job_response(job_id: str) -> dict:
    job = get_job(job_id)
    steps = (
        supabase.table("scan_steps")
        .select("*")
        .eq("job_id", job_id)
        .order("step_order")
        .execute()
    ).data or []
    listings = get_listing_results(job_id)
    logs = get_logs(job_id, limit=50)
    errors = get_errors(job_id, limit=20)

    results = [r.get("result") for r in listings if r.get("result")]
    approved = [r for r in results if isinstance(r, dict) and r.get("deal_status") == "approved_candidate"]
    manual = [r for r in results if isinstance(r, dict) and r.get("deal_status") == "manual_review"]
    rejected = [r for r in listings if r.get("status") == "failed" or (isinstance(r.get("result"), dict) and r.get("result", {}).get("deal_status") == "rejected")]

    return {
        "success": True,
        "job": job,
        "steps": steps,
        "listings": listings,
        "logs": logs,
        "errors": errors,
        "summary": {
            "scanned_count": job.get("listings_done", 0),
            "approved_candidates_count": job.get("approved_count", 0),
            "manual_review_count": job.get("manual_review_count", 0),
            "rejected_count": job.get("rejected_count", 0),
            "top_deals": approved + manual,
            "approved_candidates": approved,
            "manual_review_deals": manual,
            "rejected_history": rejected,
            "all_results": results,
            "excel_export_generated": bool(job.get("excel_path")),
            "excel_export_path": job.get("excel_path"),
        },
    }
