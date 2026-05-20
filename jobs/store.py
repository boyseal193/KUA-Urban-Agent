"""Supabase persistence layer for the K.U.A. async scan pipeline.

All Supabase operations are wrapped with structured error handling so a
missing table or transient PostgREST failure cannot crash a request or the
worker loop. Callers receive either a typed result or a typed exception
(DatabaseSetupError or StoreError).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional, TypeVar

from postgrest.exceptions import APIError

from database import supabase
from jobs.constants import (
    ACTIVE_JOB_STATUSES,
    JOB_FAILED,
    JOB_HEARTBEAT_STALE_SEC,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_TIMEOUT,
    PIPELINE_STEPS,
    STEP_PENDING,
    STEP_RUNNING,
    STEP_SUCCESS,
    TERMINAL_JOB_STATUSES,
)
from jobs.db_health import (
    _is_missing_column_error,
    _is_missing_table_error,
    assert_pipeline_ready,
    check_missing_tables,
)
from jobs.errors import DatabaseSetupError, StoreError
from jobs.logging_util import get_logger, safe_json

T = TypeVar("T")

# Job-level steps use listing_index = -1 (NULL would break the UNIQUE
# (job_id, listing_index, step_key) constraint in PostgreSQL).
JOB_LEVEL_INDEX = -1


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_from_api_error(exc: APIError, *, table: str, operation: str) -> None:
    if _is_missing_table_error(exc):
        from jobs.db_health import check_schema

        snapshot = check_schema(force=True)
        missing_tables = list(snapshot.get("missing_tables") or [])  # type: ignore[arg-type]
        missing_columns = dict(snapshot.get("missing_columns") or {})  # type: ignore[arg-type]
        if not missing_tables and not missing_columns:
            missing_tables = [table]
        raise DatabaseSetupError(
            missing_tables=missing_tables, missing_columns=missing_columns
        ) from exc

    code = getattr(exc, "code", None)
    if code in ("42703", "PGRST204") or _is_missing_column_error(exc):
        from jobs.db_health import check_schema

        snapshot = check_schema(force=True)
        raise DatabaseSetupError(
            missing_tables=list(snapshot.get("missing_tables") or []),  # type: ignore[arg-type]
            missing_columns=dict(snapshot.get("missing_columns") or {}),  # type: ignore[arg-type]
        ) from exc

    message = str(exc)
    if hasattr(exc, "message") and isinstance(exc.message, dict):
        message = exc.message.get("message", message)

    raise StoreError(
        f"Supabase {operation} failed on {table}: {message}",
        table=table,
        operation=operation,
        retryable=False,
        cause=exc,
    ) from exc


def _execute(fn: Callable[[], T], *, table: str, operation: str) -> T:
    try:
        return fn()
    except DatabaseSetupError:
        raise
    except StoreError:
        raise
    except APIError as exc:
        _raise_from_api_error(exc, table=table, operation=operation)
    except Exception as exc:
        if _is_missing_table_error(exc) or _is_missing_column_error(exc):
            from jobs.db_health import check_schema

            snapshot = check_schema(force=True)
            raise DatabaseSetupError(
                missing_tables=list(snapshot.get("missing_tables") or []) or [table],  # type: ignore[arg-type]
                missing_columns=dict(snapshot.get("missing_columns") or {}),  # type: ignore[arg-type]
            ) from exc
        raise StoreError(
            f"{operation} failed on {table}: {exc}",
            table=table,
            operation=operation,
            retryable=False,
            cause=exc,
        ) from exc
    # Should be unreachable; quiets type checkers.
    raise StoreError(
        f"{operation} on {table} returned no value",
        table=table,
        operation=operation,
        retryable=False,
    )


def _log(
    job_id: str,
    level: str,
    message: str,
    step_id: Optional[str] = None,
    context: Optional[dict] = None,
) -> None:
    """Insert a structured log row. Never raises (except DatabaseSetupError)."""
    try:
        _execute(
            lambda: supabase.table("scan_logs")
            .insert(
                {
                    "job_id": job_id,
                    "step_id": step_id,
                    "level": level,
                    "message": message[:2000],
                    "context": safe_json(context or {}),
                }
            )
            .execute(),
            table="scan_logs",
            operation="insert",
        )
    except DatabaseSetupError:
        raise
    except StoreError:
        # Logging must never crash the pipeline.
        pass


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
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
    assert_pipeline_ready(force=True)

    job_id = str(uuid.uuid4())
    row = {
        "id": job_id,
        "job_type": job_type,
        "status": JOB_QUEUED,
        "created_by": created_by,
        "search_url": search_url,
        "filters": safe_json(filters),
        "payload": safe_json(
            {
                "search_url": search_url,
                "filters": filters,
                "listing_limit": listing_limit,
                "generate_excel": generate_excel,
            }
        ),
        "listing_limit": listing_limit,
        "generate_excel": generate_excel,
        "request_id": request_id or job_id,
    }

    _execute(
        lambda: supabase.table("scan_jobs").insert(row).execute(),
        table="scan_jobs",
        operation="insert",
    )

    # Seed job-level steps so the frontend can render the pipeline immediately.
    for order, step_key in enumerate(PIPELINE_STEPS):
        _execute(
            lambda sk=step_key, ord=order: supabase.table("scan_steps")
            .insert(
                {
                    "job_id": job_id,
                    "listing_index": JOB_LEVEL_INDEX,
                    "step_key": sk,
                    "step_order": ord,
                    "status": STEP_PENDING,
                }
            )
            .execute(),
            table="scan_steps",
            operation="insert",
        )

    _log(job_id, "info", "Job created and queued", context={"search_url": search_url})
    return get_job(job_id)


def get_job(job_id: str) -> dict:
    res = _execute(
        lambda: supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute(),
        table="scan_jobs",
        operation="select",
    )
    if not res.data:
        raise KeyError(f"Job not found: {job_id}")
    return res.data[0]


def list_jobs(limit: int = 20, status: Optional[str] = None) -> List[dict]:
    assert_pipeline_ready()
    query = supabase.table("scan_jobs").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    res = _execute(lambda: query.execute(), table="scan_jobs", operation="select")
    return res.data or []


def queue_size() -> int:
    res = _execute(
        lambda: supabase.table("scan_jobs")
        .select("id", count="exact")
        .eq("status", JOB_QUEUED)
        .execute(),
        table="scan_jobs",
        operation="count",
    )
    return int(getattr(res, "count", 0) or len(res.data or []))


def running_jobs() -> List[dict]:
    res = _execute(
        lambda: supabase.table("scan_jobs")
        .select("id,status,worker_id,last_heartbeat_at,started_at")
        .in_("status", [JOB_RUNNING, "retrying"])
        .execute(),
        table="scan_jobs",
        operation="select",
    )
    return res.data or []


def claim_next_job(worker_id: str) -> Optional[dict]:
    assert_pipeline_ready()
    res = _execute(
        lambda: supabase.table("scan_jobs")
        .select("*")
        .eq("status", JOB_QUEUED)
        .order("created_at")
        .limit(1)
        .execute(),
        table="scan_jobs",
        operation="select",
    )
    if not res.data:
        return None

    job = res.data[0]
    job_id = job["id"]
    now = _now()

    updated = _execute(
        lambda: supabase.table("scan_jobs")
        .update(
            {
                "status": JOB_RUNNING,
                "started_at": now,
                "worker_id": worker_id,
                "last_heartbeat_at": now,
                "error_message": None,
            }
        )
        .eq("id", job_id)
        .eq("status", JOB_QUEUED)
        .execute(),
        table="scan_jobs",
        operation="update",
    )
    if not updated.data:
        # Another worker beat us to it.
        return None

    _log(job_id, "info", f"Job claimed by worker={worker_id}")
    return updated.data[0]


def update_job(job_id: str, **fields) -> dict:
    fields["updated_at"] = _now()
    res = _execute(
        lambda: supabase.table("scan_jobs").update(fields).eq("id", job_id).execute(),
        table="scan_jobs",
        operation="update",
    )
    if res.data:
        return res.data[0]
    return get_job(job_id)


def touch_heartbeat(job_id: str, worker_id: Optional[str] = None) -> None:
    """Update last_heartbeat_at to NOW so dead-job sweepers know we're alive."""
    fields = {"last_heartbeat_at": _now()}
    if worker_id:
        fields["worker_id"] = worker_id
    try:
        _execute(
            lambda: supabase.table("scan_jobs").update(fields).eq("id", job_id).execute(),
            table="scan_jobs",
            operation="update",
        )
    except StoreError as exc:
        get_logger(job_id, "heartbeat").warning("Heartbeat update failed: %s", exc)


def requeue_for_retry(job_id: str) -> dict:
    """Reset a failed/timeout job for another worker attempt."""
    job = get_job(job_id)
    retry_count = int(job.get("retry_count") or 0)
    max_retries = int(job.get("max_retries") or 3)

    if retry_count >= max_retries:
        raise StoreError(
            f"Job {job_id} has reached max_retries={max_retries}",
            table="scan_jobs",
            operation="retry",
            retryable=False,
        )

    return update_job(
        job_id,
        status=JOB_QUEUED,
        retry_count=retry_count + 1,
        worker_id=None,
        last_heartbeat_at=None,
        started_at=None,
        finished_at=None,
        error_message=None,
        progress_pct=0,
        current_step=None,
    )


def sweep_dead_jobs(stale_after_sec: int = JOB_HEARTBEAT_STALE_SEC) -> int:
    """Move running jobs with stale heartbeats to 'failed'. Returns count."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_sec)).isoformat()
    res = _execute(
        lambda: supabase.table("scan_jobs")
        .select("id,last_heartbeat_at,started_at,worker_id")
        .eq("status", JOB_RUNNING)
        .execute(),
        table="scan_jobs",
        operation="select",
    )
    stale_ids: List[str] = []
    for row in res.data or []:
        hb = row.get("last_heartbeat_at") or row.get("started_at")
        if not hb:
            continue
        if hb < cutoff:
            stale_ids.append(row["id"])

    for jid in stale_ids:
        try:
            update_job(
                jid,
                status=JOB_TIMEOUT,
                error_message="Worker heartbeat stale — job recovered by sweeper",
                finished_at=_now(),
            )
            _log(jid, "error", "Job timed out (stale heartbeat)")
        except StoreError as exc:
            get_logger(jid, "sweeper").warning("Sweep update failed: %s", exc)
    return len(stale_ids)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def get_steps(job_id: str, listing_index: int = JOB_LEVEL_INDEX) -> List[dict]:
    res = _execute(
        lambda: supabase.table("scan_steps")
        .select("*")
        .eq("job_id", job_id)
        .eq("listing_index", listing_index)
        .order("step_order")
        .execute(),
        table="scan_steps",
        operation="select",
    )
    return res.data or []


def ensure_listing_steps(job_id: str, listing_index: int, listing_url: str) -> None:
    from jobs.constants import LISTING_LEVEL_STEPS

    existing = _execute(
        lambda: supabase.table("scan_steps")
        .select("id")
        .eq("job_id", job_id)
        .eq("listing_index", listing_index)
        .limit(1)
        .execute(),
        table="scan_steps",
        operation="select",
    )
    if existing.data:
        return

    base_order = 100 + listing_index * len(LISTING_LEVEL_STEPS)
    for i, step_key in enumerate(LISTING_LEVEL_STEPS):
        _execute(
            lambda sk=step_key, ord=base_order + i: supabase.table("scan_steps")
            .insert(
                {
                    "job_id": job_id,
                    "listing_index": listing_index,
                    "listing_url": listing_url,
                    "step_key": sk,
                    "step_order": ord,
                    "status": STEP_PENDING,
                }
            )
            .execute(),
            table="scan_steps",
            operation="insert",
        )


def _find_step_query(job_id: str, step_key: str, listing_index: int):
    return (
        supabase.table("scan_steps")
        .select("*")
        .eq("job_id", job_id)
        .eq("step_key", step_key)
        .eq("listing_index", listing_index)
    )


def start_step(job_id: str, step_key: str, listing_index: int = JOB_LEVEL_INDEX) -> dict:
    res = _execute(
        lambda: _find_step_query(job_id, step_key, listing_index).limit(1).execute(),
        table="scan_steps",
        operation="select",
    )
    if not res.data:
        # Lazily insert the step if it was never seeded (e.g. listing-level
        # step on a job started before ensure_listing_steps ran).
        _execute(
            lambda: supabase.table("scan_steps")
            .insert(
                {
                    "job_id": job_id,
                    "listing_index": listing_index,
                    "step_key": step_key,
                    "step_order": 0,
                    "status": STEP_PENDING,
                }
            )
            .execute(),
            table="scan_steps",
            operation="insert",
        )
        res = _execute(
            lambda: _find_step_query(job_id, step_key, listing_index).limit(1).execute(),
            table="scan_steps",
            operation="select",
        )

    step = res.data[0]
    attempt = int(step.get("attempt") or 0) + 1
    updated = _execute(
        lambda: supabase.table("scan_steps")
        .update(
            {
                "status": STEP_RUNNING,
                "attempt": attempt,
                "started_at": _now(),
                "error_message": None,
                "error_type": None,
                "traceback": None,
            }
        )
        .eq("id", step["id"])
        .execute(),
        table="scan_steps",
        operation="update",
    )
    try:
        update_job(job_id, current_step=step_key)
    except StoreError:
        pass
    return updated.data[0] if updated.data else step


def finish_step(
    job_id: str,
    step_key: str,
    *,
    listing_index: int = JOB_LEVEL_INDEX,
    status: str = STEP_SUCCESS,
    output_data: Optional[dict] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    traceback: Optional[str] = None,
    retryable: bool = True,
    duration_ms: Optional[int] = None,
) -> dict:
    res = _execute(
        lambda: _find_step_query(job_id, step_key, listing_index).select("id").limit(1).execute(),
        table="scan_steps",
        operation="select",
    )
    if not res.data:
        raise KeyError(f"Step not found: {step_key}")

    step_id = res.data[0]["id"]
    payload = {
        "status": status,
        "finished_at": _now(),
        "output_data": safe_json(output_data) if output_data else None,
        "result": safe_json(output_data) if output_data else None,
        "error_type": error_type,
        "error_message": (error_message or "")[:2000] if error_message else None,
        "traceback": (traceback or "")[:8000] if traceback else None,
        "retryable": retryable,
        "duration_ms": duration_ms,
    }
    updated = _execute(
        lambda: supabase.table("scan_steps").update(payload).eq("id", step_id).execute(),
        table="scan_steps",
        operation="update",
    )
    return updated.data[0] if updated.data else {}


# ---------------------------------------------------------------------------
# Errors / logs
# ---------------------------------------------------------------------------
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
    try:
        _execute(
            lambda: supabase.table("scan_errors")
            .insert(
                {
                    "job_id": job_id,
                    "step_id": step_id,
                    "listing_url": listing_url,
                    "error_type": error_type,
                    "message": (message or "")[:2000],
                    "traceback": (traceback or "")[:8000] if traceback else None,
                    "retryable": retryable,
                    "attempt": attempt,
                }
            )
            .execute(),
            table="scan_errors",
            operation="insert",
        )
    except DatabaseSetupError:
        raise
    except StoreError:
        pass

    _log(job_id, "error", message, step_id=step_id, context={"error_type": error_type})


# ---------------------------------------------------------------------------
# Listing results
# ---------------------------------------------------------------------------
def upsert_listing_result(job_id: str, listing_index: int, listing_url: str, **fields) -> dict:
    existing = _execute(
        lambda: supabase.table("scan_listing_results")
        .select("id")
        .eq("job_id", job_id)
        .eq("listing_index", listing_index)
        .limit(1)
        .execute(),
        table="scan_listing_results",
        operation="select",
    )

    payload = {
        "job_id": job_id,
        "listing_index": listing_index,
        "listing_url": listing_url,
        **fields,
    }
    if "result" in payload and payload["result"] is not None:
        payload["result"] = safe_json(payload["result"])

    if existing.data:
        res = _execute(
            lambda: supabase.table("scan_listing_results")
            .update(payload)
            .eq("id", existing.data[0]["id"])
            .execute(),
            table="scan_listing_results",
            operation="update",
        )
    else:
        res = _execute(
            lambda: supabase.table("scan_listing_results").insert(payload).execute(),
            table="scan_listing_results",
            operation="insert",
        )
    return res.data[0] if res.data else payload


def get_listing_results(job_id: str) -> List[dict]:
    res = _execute(
        lambda: supabase.table("scan_listing_results")
        .select("*")
        .eq("job_id", job_id)
        .order("listing_index")
        .execute(),
        table="scan_listing_results",
        operation="select",
    )
    return res.data or []


def get_logs(job_id: str, limit: int = 100) -> List[dict]:
    res = _execute(
        lambda: supabase.table("scan_logs")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute(),
        table="scan_logs",
        operation="select",
    )
    return res.data or []


def get_errors(job_id: str, limit: int = 50) -> List[dict]:
    res = _execute(
        lambda: supabase.table("scan_errors")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute(),
        table="scan_errors",
        operation="select",
    )
    return res.data or []


# ---------------------------------------------------------------------------
# Extracted / memo persistence
# ---------------------------------------------------------------------------
def save_extracted_property(
    job_id: str,
    listing_url: str,
    property_id: Optional[str],
    extracted: dict,
    economics: Optional[dict],
    score: Optional[dict],
) -> None:
    _execute(
        lambda: supabase.table("extracted_properties")
        .insert(
            {
                "job_id": job_id,
                "listing_url": listing_url,
                "property_id": property_id,
                "extracted": safe_json(extracted),
                "economics": safe_json(economics) if economics else None,
                "score": safe_json(score) if score else None,
            }
        )
        .execute(),
        table="extracted_properties",
        operation="insert",
    )


def save_generated_memo(
    job_id: str,
    listing_url: str,
    property_id: Optional[str],
    memo_text: str,
    verdict: Optional[str],
    deal_status: Optional[str],
) -> None:
    _execute(
        lambda: supabase.table("generated_memos")
        .insert(
            {
                "job_id": job_id,
                "listing_url": listing_url,
                "property_id": property_id,
                "memo_text": memo_text,
                "verdict": verdict,
                "deal_status": deal_status,
            }
        )
        .execute(),
        table="generated_memos",
        operation="insert",
    )


# ---------------------------------------------------------------------------
# Composite response builder used by GET /jobs/{id}
# ---------------------------------------------------------------------------
def build_job_response(job_id: str) -> dict:
    job = get_job(job_id)
    steps_res = _execute(
        lambda: supabase.table("scan_steps")
        .select("*")
        .eq("job_id", job_id)
        .order("step_order")
        .execute(),
        table="scan_steps",
        operation="select",
    )
    steps = steps_res.data or []
    listings = get_listing_results(job_id)
    logs = get_logs(job_id, limit=50)
    errors = get_errors(job_id, limit=20)

    results = [r.get("result") for r in listings if r.get("result")]
    approved = [
        r
        for r in results
        if isinstance(r, dict) and r.get("deal_status") == "approved_candidate"
    ]
    manual = [
        r for r in results if isinstance(r, dict) and r.get("deal_status") == "manual_review"
    ]
    rejected = [
        r
        for r in listings
        if r.get("status") == "failed"
        or (
            isinstance(r.get("result"), dict)
            and r.get("result", {}).get("deal_status") == "rejected"
        )
    ]

    return {
        "success": True,
        "job": job,
        "steps": steps,
        "listings": listings,
        "logs": logs,
        "errors": errors,
        "summary": {
            "success": True,
            "scanned_count": job.get("listings_done", 0),
            "approved_candidates_count": job.get("approved_count", 0),
            "manual_review_count": job.get("manual_review_count", 0),
            "rejected_count": job.get("rejected_count", 0),
            "top_deals_count": len(approved) + len(manual),
            "top_deals": approved + manual,
            "approved_candidates": approved,
            "manual_review_deals": manual,
            "rejected_history": rejected,
            "all_results": results,
            "excel_export_generated": bool(job.get("excel_path")),
            "excel_export_path": job.get("excel_path"),
            "filters_used": job.get("filters") or {},
        },
    }


def pipeline_metrics() -> dict:
    """Counts by status for /health/pipeline."""
    counts: dict = {}
    for st in ("queued", "running", "retrying", "success", "failed", "cancelled", "timeout"):
        try:
            res = _execute(
                lambda s=st: supabase.table("scan_jobs")
                .select("id", count="exact")
                .eq("status", s)
                .execute(),
                table="scan_jobs",
                operation="count",
            )
            counts[st] = int(getattr(res, "count", 0) or len(res.data or []))
        except StoreError:
            counts[st] = -1
    return counts
