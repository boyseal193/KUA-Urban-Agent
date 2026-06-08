"""Supabase REST persistence layer for the laundry vertical.

Independent tables (no overlap with the storage pipeline):

* ``laundry_properties``   — one row per scanned property
* ``laundry_analyses``     — versioned underwriting outputs per property

Async job state is intentionally **shared** with the storage pipeline via the
existing ``scan_jobs`` table (with ``job_type='laundry_scan'``). This lets us
reuse the production worker loop, heartbeats, retry, and cancel UX without
duplicating infrastructure.

All Supabase calls are wrapped so a transient PostgREST failure or a missing
table never explodes the API request. Callers receive ``(ok, data, error)``.
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
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(client_available: bool = True) -> Tuple[bool, Optional[str]]:
    if supabase is None or not client_available:
        return False, "supabase_client_not_initialised"
    return True, None


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
LAUNDRY_JOB_TYPE = "laundry_scan"


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
        return True, {"id": job_id, "status": JOB_QUEUED}, None
    except Exception as exc:
        log.exception("create_scan_job failed: %s", exc)
        return False, None, str(exc)


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


def update_job_progress(job_id: str, **fields: Any) -> None:
    if supabase is None or not job_id: return
    payload = {k: v for k, v in fields.items() if v is not None}
    if not payload: return
    try:
        supabase.table("scan_jobs").update(payload).eq("id", job_id).execute()
    except Exception as exc:  # never block worker on telemetry
        log.warning("update_job_progress failed: %s", exc)
