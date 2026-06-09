"""Supabase REST persistence layer for the laundry vertical.

Independent tables (no overlap with the storage pipeline):

* ``laundry_properties``   — one row per scanned property
* ``laundry_analyses``     — versioned underwriting outputs per property

Async job state and per-step / per-listing telemetry are intentionally
**shared** with the storage pipeline via the existing tables (with
``job_type='laundry_scan'`` discriminating the rows). This lets us reuse the
production worker loop, heartbeats, retry, cancel UX and the per-step UI
without duplicating infrastructure.

All Supabase calls are wrapped so a transient PostgREST failure or a missing
table never explodes the API request or the worker loop. Telemetry helpers
silently swallow errors; only fatal data-write helpers bubble the error up.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import supabase

log = logging.getLogger("kua.laundry.store")


# ---------------------------------------------------------------------------
# Constants — laundry-side status strings (kept separate from storage to make
# the wire contract obvious to the frontend).
# ---------------------------------------------------------------------------
LAUNDRY_JOB_TYPE = "laundry_scan"

# Pipeline step keys, written into the shared `scan_steps` table.
JOB_STEP_INGEST = "laundry_ingest_inputs"
JOB_STEP_DISCOVER = "laundry_discover_urls"
JOB_STEP_UNDERWRITE = "laundry_underwrite_listings"
JOB_STEP_SUMMARY = "laundry_summarize"
LISTING_STEP_PROCESS = "laundry_process_listing"

PIPELINE_STEPS: Tuple[str, ...] = (
    JOB_STEP_INGEST,
    JOB_STEP_DISCOVER,
    JOB_STEP_UNDERWRITE,
    JOB_STEP_SUMMARY,
)

STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_SUCCESS = "success"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"

JOB_LEVEL_INDEX = -1  # matches jobs.store.JOB_LEVEL_INDEX (UNIQUE constraint)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(payload):
    try:
        return json.loads(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
def upsert_property(*, extracted: Dict[str, Any], economics: Dict[str, Any],
                     scoring: Dict[str, Any], location: Dict[str, Any],
                     dedupe_key: str, listing_url: Optional[str],
                     source: str = "scan", job_id: Optional[str] = None) -> Tuple[bool, Optional[Dict], Optional[str]]:
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    try:
        existing = (
            supabase.table("laundry_properties")
            .select("id, score, deal_status, created_at, dedupe_key")
            .eq("dedupe_key", dedupe_key)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if existing.data:
            property_id = existing.data[0]["id"]
            update_payload = _row_from_inputs(
                extracted=extracted, economics=economics, scoring=scoring,
                location=location, listing_url=listing_url, source=source,
                job_id=job_id, dedupe_key=dedupe_key,
            )
            update_payload.pop("id", None)
            update_payload.pop("created_at", None)
            update_payload["updated_at"] = _now()
            supabase.table("laundry_properties").update(update_payload).eq("id", property_id).execute()
            return True, {"id": property_id, "duplicate": True}, None

        property_id = str(uuid.uuid4())
        row = _row_from_inputs(
            extracted=extracted, economics=economics, scoring=scoring,
            location=location, listing_url=listing_url, source=source,
            job_id=job_id, dedupe_key=dedupe_key,
        )
        row["id"] = property_id
        row["created_at"] = _now()
        supabase.table("laundry_properties").insert(row).execute()
        return True, {"id": property_id, "duplicate": False}, None
    except Exception as exc:
        log.exception("upsert_property failed: %s", exc)
        return False, None, str(exc)


def _row_from_inputs(*, extracted, economics, scoring, location, listing_url,
                     source, job_id, dedupe_key) -> Dict[str, Any]:
    return {
        "source": source,
        "job_id": job_id,
        "listing_url": listing_url,
        "dedupe_key": dedupe_key,
        "address": extracted.get("address"),
        "city": extracted.get("city") or location.get("city") or "Barcelona",
        "neighbourhood": extracted.get("neighbourhood") or location.get("neighbourhood"),
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "property_type": extracted.get("property_type"),
        "acquisition_type": extracted.get("acquisition_type") or economics.get("acquisition_type"),
        "floor_area_m2": economics.get("floor_area_m2") or extracted.get("floor_area_m2"),
        "asking_price": extracted.get("asking_price"),
        "asking_rent_month": extracted.get("asking_rent_month"),
        "washer_count": economics.get("washer_count"),
        "dryer_count": economics.get("dryer_count"),
        "expected_revenue_eur": economics.get("expected_revenue_eur"),
        "ebitda_eur": economics.get("ebitda_eur"),
        "operating_margin": economics.get("operating_margin"),
        "payback_years": economics.get("payback_years"),
        "score": scoring.get("score", 0),
        "verdict": scoring.get("verdict"),
        "classification": scoring.get("classification"),
        "deal_status": scoring.get("deal_status", "rejected"),
        "in_preferred_market": bool(location.get("in_preferred_market")),
        "matched_neighbourhood": location.get("matched_preferred_neighbourhood"),
        "raw_extracted": _json_safe(extracted),
    }


def insert_analysis(*, property_id: str, extracted, economics, scoring,
                     location, due_diligence, memo_md: str,
                     assumptions_version: str) -> Tuple[bool, Optional[str], Optional[str]]:
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    try:
        analysis_id = str(uuid.uuid4())
        supabase.table("laundry_analyses").insert({
            "id": analysis_id,
            "property_id": property_id,
            "extracted": _json_safe(extracted),
            "economics": _json_safe(economics),
            "scoring": _json_safe(scoring),
            "location": _json_safe(location),
            "due_diligence": _json_safe(due_diligence),
            "memo_md": memo_md,
            "assumptions_version": assumptions_version,
            "created_at": _now(),
        }).execute()
        return True, analysis_id, None
    except Exception as exc:
        log.exception("insert_analysis failed: %s", exc)
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def list_properties(*, deal_status: Optional[str] = None, limit: int = 100,
                     include_deleted: bool = False) -> List[Dict[str, Any]]:
    if supabase is None: return []
    try:
        q = supabase.table("laundry_properties").select("*").order("score", desc=True).limit(limit)
        if deal_status: q = q.eq("deal_status", deal_status)
        if not include_deleted: q = q.is_("deleted_at", "null")
        res = q.execute()
        return res.data or []
    except Exception as exc:
        log.warning("list_properties failed: %s", exc)
        return []


def get_property(property_id: str) -> Optional[Dict[str, Any]]:
    if supabase is None or not property_id: return None
    try:
        res = (
            supabase.table("laundry_properties")
            .select("*")
            .eq("id", property_id)
            .limit(1)
            .execute()
        )
        if not res.data: return None
        prop = res.data[0]
        ana = (
            supabase.table("laundry_analyses")
            .select("*")
            .eq("property_id", property_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        prop["latest_analysis"] = (ana.data or [None])[0]
        return prop
    except Exception as exc:
        log.warning("get_property failed: %s", exc)
        return None


def soft_delete_property(property_id: str, *, reason: str = "manual") -> bool:
    if supabase is None: return False
    try:
        supabase.table("laundry_properties").update({
            "deleted_at": _now(),
            "deletion_reason": reason,
        }).eq("id", property_id).execute()
        return True
    except Exception as exc:
        log.warning("soft_delete_property failed: %s", exc)
        return False


def restore_property(property_id: str) -> bool:
    if supabase is None: return False
    try:
        supabase.table("laundry_properties").update({
            "deleted_at": None, "deletion_reason": None,
        }).eq("id", property_id).execute()
        return True
    except Exception as exc:
        log.warning("restore_property failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Async jobs (shared scan_jobs table, scoped by job_type prefix)
# ---------------------------------------------------------------------------
def create_scan_job(*, search_url: str, payload: Dict[str, Any],
                     created_by: Optional[str] = None,
                     request_id: Optional[str] = None) -> Tuple[bool, Optional[Dict], Optional[str]]:
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    try:
        from jobs.constants import JOB_QUEUED
    except Exception:
        JOB_QUEUED = "queued"

    job_id = str(uuid.uuid4())
    try:
        row = {
            "id": job_id,
            "job_type": LAUNDRY_JOB_TYPE,
            "status": JOB_QUEUED,
            "created_by": created_by,
            "search_url": search_url or "",
            "filters": _json_safe(payload.get("filters") or {}),
            "payload": _json_safe(payload),
            "listing_limit": int(payload.get("listing_limit") or 10),
            "generate_excel": bool(payload.get("generate_excel", False)),
            "request_id": request_id or job_id,
        }
        supabase.table("scan_jobs").insert(row).execute()
    except Exception as exc:
        log.exception("create_scan_job failed: %s", exc)
        return False, None, str(exc)

    # Seed job-level pipeline steps so the UI shows the pipeline immediately
    # instead of "Waiting for first step…". A failure here is non-fatal — the
    # worker will lazily insert any missing step via jobs.store.start_step.
    try:
        for order, step_key in enumerate(PIPELINE_STEPS):
            supabase.table("scan_steps").insert({
                "job_id": job_id,
                "listing_index": JOB_LEVEL_INDEX,
                "step_key": step_key,
                "step_order": order,
                "status": STEP_PENDING,
            }).execute()
    except Exception as exc:
        log.warning("seed_pipeline_steps failed (non-fatal): %s", exc)

    return True, {"id": job_id, "status": JOB_QUEUED}, None


def get_scan_job(job_id: str) -> Optional[Dict[str, Any]]:
    if supabase is None or not job_id: return None
    try:
        res = supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute()
        if not res.data: return None
        job = res.data[0]
        try:
            props = (
                supabase.table("laundry_properties")
                .select("id, address, city, neighbourhood, score, verdict, classification, "
                         "deal_status, floor_area_m2, ebitda_eur, payback_years, listing_url, "
                         "in_preferred_market, matched_neighbourhood, created_at")
                .eq("job_id", job_id)
                .is_("deleted_at", "null")
                .order("score", desc=True)
                .limit(200)
                .execute()
            )
            job["properties"] = props.data or []
        except Exception as exc:
            log.warning("get_scan_job: properties lookup failed: %s", exc)
            job["properties"] = []
        return job
    except Exception as exc:
        log.warning("get_scan_job failed: %s", exc)
        return None


def list_pipeline_steps(job_id: str) -> List[Dict[str, Any]]:
    """Return every scan_steps row for a job, ordered for UI rendering.

    Job-level steps come first (listing_index = -1), then per-listing steps
    grouped by listing_index. Safe to call even if the table is empty.
    """
    if supabase is None or not job_id: return []
    try:
        res = (
            supabase.table("scan_steps")
            .select("*")
            .eq("job_id", job_id)
            .order("listing_index")
            .order("step_order")
            .limit(2000)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.warning("list_pipeline_steps failed: %s", exc)
        return []


def list_laundry_jobs(*, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    if supabase is None: return []
    try:
        q = (
            supabase.table("scan_jobs")
            .select("*")
            .eq("job_type", LAUNDRY_JOB_TYPE)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if status: q = q.eq("status", status)
        res = q.execute()
        return res.data or []
    except Exception as exc:
        log.warning("list_laundry_jobs failed: %s", exc)
        return []


def cancel_job(job_id: str) -> bool:
    if supabase is None or not job_id: return False
    try:
        supabase.table("scan_jobs").update({
            "status": "cancelled",
            "finished_at": _now(),
            "error_message": "Cancelled by operator",
        }).eq("id", job_id).execute()
        return True
    except Exception as exc:
        log.warning("cancel_job failed: %s", exc)
        return False


def update_job(job_id: str, **fields: Any) -> None:
    """Update arbitrary columns on scan_jobs. Drops keys whose value is the
    sentinel ``_OMIT`` so callers can express ``listings_done=count, error=None``
    without ambiguity. None values are ALLOWED and written through."""
    if supabase is None or not job_id: return
    if not fields: return
    fields = {k: v for k, v in fields.items() if v is not _OMIT}
    if not fields: return
    fields.setdefault("updated_at", _now())
    try:
        supabase.table("scan_jobs").update(fields).eq("id", job_id).execute()
    except Exception as exc:  # never block worker on telemetry
        log.warning("update_job failed: %s", exc)


_OMIT = object()


# Backwards-compat alias used by older callers.
def update_job_progress(job_id: str, **fields: Any) -> None:
    update_job(job_id, **fields)


def is_job_cancelled(job_id: str) -> bool:
    if supabase is None or not job_id: return False
    try:
        res = (
            supabase.table("scan_jobs").select("status").eq("id", job_id).limit(1).execute()
        )
        if not res.data: return False
        return str(res.data[0].get("status") or "").lower() == "cancelled"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Per-step + per-listing telemetry (writes to shared scan_steps /
# scan_listing_results tables; identical schema as the storage pipeline).
# ---------------------------------------------------------------------------
def _find_or_seed_step(job_id: str, step_key: str, listing_index: int,
                        listing_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        res = (
            supabase.table("scan_steps")
            .select("*")
            .eq("job_id", job_id)
            .eq("step_key", step_key)
            .eq("listing_index", listing_index)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
        row = {
            "job_id": job_id,
            "listing_index": listing_index,
            "step_key": step_key,
            "step_order": listing_index if listing_index >= 0 else 0,
            "status": STEP_PENDING,
            "listing_url": listing_url,
        }
        ins = supabase.table("scan_steps").insert(row).execute()
        if ins.data and ins.data[0].get("id"):
            return ins.data[0]
        # Insert returned nothing useful — re-select so we have the row's id.
        reread = (
            supabase.table("scan_steps")
            .select("*")
            .eq("job_id", job_id)
            .eq("step_key", step_key)
            .eq("listing_index", listing_index)
            .limit(1)
            .execute()
        )
        return reread.data[0] if reread.data else None
    except Exception as exc:
        log.warning("_find_or_seed_step failed: %s", exc)
        return None


def start_step(job_id: str, step_key: str, *, listing_index: int = JOB_LEVEL_INDEX,
                listing_url: Optional[str] = None) -> None:
    if supabase is None: return
    step = _find_or_seed_step(job_id, step_key, listing_index, listing_url)
    if not step: return
    try:
        supabase.table("scan_steps").update({
            "status": STEP_RUNNING,
            "started_at": _now(),
            "error_type": None,
            "error_message": None,
            "listing_url": listing_url or step.get("listing_url"),
        }).eq("id", step["id"]).execute()
        update_job(job_id, current_step=step_key)
    except Exception as exc:
        log.warning("start_step failed: %s", exc)


def finish_step(job_id: str, step_key: str, *, listing_index: int = JOB_LEVEL_INDEX,
                 status: str = STEP_SUCCESS, error_type: Optional[str] = None,
                 error_message: Optional[str] = None,
                 output: Optional[Dict[str, Any]] = None,
                 duration_ms: Optional[int] = None) -> None:
    if supabase is None: return
    step = _find_or_seed_step(job_id, step_key, listing_index)
    if not step: return
    try:
        supabase.table("scan_steps").update({
            "status": status,
            "finished_at": _now(),
            "error_type": error_type,
            "error_message": (error_message or "")[:2000] if error_message else None,
            "output_data": _json_safe(output) if output else None,
            "result": _json_safe(output) if output else None,
            "duration_ms": duration_ms,
        }).eq("id", step["id"]).execute()
    except Exception as exc:
        log.warning("finish_step failed: %s", exc)


def record_listing_result(job_id: str, listing_index: int, *,
                           listing_url: Optional[str] = None,
                           status: str = "success",
                           result: Optional[Dict[str, Any]] = None,
                           property_id: Optional[str] = None,
                           deal_status: Optional[str] = None,
                           score: Optional[int] = None,
                           error_message: Optional[str] = None) -> None:
    if supabase is None: return
    payload = {
        "job_id": job_id,
        "listing_index": listing_index,
        "listing_url": listing_url,
        "status": status,
        "result": _json_safe({
            **(result or {}),
            "property_id": property_id,
            "deal_status": deal_status,
            "score": score,
        }),
        "property_id": property_id,
        "deal_status": deal_status,
        "score": score,
        "error_message": (error_message or "")[:2000] if error_message else None,
        "updated_at": _now(),
    }
    try:
        existing = (
            supabase.table("scan_listing_results")
            .select("id")
            .eq("job_id", job_id)
            .eq("listing_index", listing_index)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase.table("scan_listing_results").update(payload).eq("id", existing.data[0]["id"]).execute()
        else:
            payload["created_at"] = _now()
            supabase.table("scan_listing_results").insert(payload).execute()
    except Exception as exc:
        log.warning("record_listing_result failed: %s", exc)


def set_job_counters(job_id: str, *, listings_total: Optional[int] = None,
                       listings_done: Optional[int] = None,
                       listings_failed: Optional[int] = None,
                       approved_count: Optional[int] = None,
                       manual_review_count: Optional[int] = None,
                       rejected_count: Optional[int] = None,
                       progress_pct: Optional[int] = None) -> None:
    fields: Dict[str, Any] = {}
    if listings_total is not None: fields["listings_total"] = listings_total
    if listings_done is not None: fields["listings_done"] = listings_done
    if listings_failed is not None: fields["listings_failed"] = listings_failed
    if approved_count is not None: fields["approved_count"] = approved_count
    if manual_review_count is not None: fields["manual_review_count"] = manual_review_count
    if rejected_count is not None: fields["rejected_count"] = rejected_count
    if progress_pct is not None: fields["progress_pct"] = progress_pct
    if fields:
        update_job(job_id, **fields)
