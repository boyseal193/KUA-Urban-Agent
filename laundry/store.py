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
import math
import re
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from database import supabase
from laundry import normalization

log = logging.getLogger("kua.laundry.store")

T = TypeVar("T")

try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except Exception:  # pragma: no cover
    PostgrestAPIError = Exception  # type: ignore


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
        return json.loads(json.dumps(payload, default=str, allow_nan=False))
    except (TypeError, ValueError):
        return None


def _finite_float(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _safe_int(v, default: int = 0) -> int:
    if v is None or isinstance(v, bool):
        return default
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _execute_write(
    fn: Callable[[], T],
    *,
    table: str,
    operation: str,
    context: Optional[Dict[str, Any]] = None,
) -> T:
    """Run a Supabase write and log full details on failure (never swallow)."""
    try:
        return fn()
    except PostgrestAPIError as exc:
        detail = getattr(exc, "message", None) or str(exc)
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("hint") or str(detail)
        log.error(
            "Supabase %s failed on %s: %s | context=%s",
            operation,
            table,
            detail,
            context or {},
            exc_info=True,
        )
        raise RuntimeError(f"{table}.{operation}_failed: {detail}") from exc
    except Exception as exc:
        log.error(
            "Supabase %s crashed on %s: %s | context=%s\n%s",
            operation,
            table,
            exc,
            context or {},
            traceback.format_exc(),
        )
        raise


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
def check_laundry_schema() -> Tuple[bool, Optional[str]]:
    """Verify laundry tables are reachable before persisting underwriting output."""
    if supabase is None:
        return False, "supabase_client_not_initialised"
    for table in ("laundry_properties", "laundry_analyses"):
        try:
            supabase.table(table).select("id").limit(1).execute()
        except Exception as exc:
            msg = f"{table} unavailable: {exc}"
            log.error("check_laundry_schema: %s", msg)
            return False, msg
    return True, None


def upsert_property(*, extracted: Dict[str, Any], economics: Dict[str, Any],
                     scoring: Dict[str, Any], location: Dict[str, Any],
                     dedupe_key: str, listing_url: Optional[str],
                     source: str = "scan", job_id: Optional[str] = None) -> Tuple[bool, Optional[Dict], Optional[str]]:
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    if not dedupe_key:
        return False, None, "missing_dedupe_key"

    ok_schema, schema_err = check_laundry_schema()
    if not ok_schema:
        return False, None, schema_err

    ctx = {
        "job_id": job_id,
        "listing_url": listing_url,
        "dedupe_key": dedupe_key[:12],
        "table": "laundry_properties",
    }
    log.info("property.insert start job_id=%s url=%s dedupe=%s", job_id, listing_url, dedupe_key[:12])

    try:
        existing = _execute_write(
            lambda: (
                supabase.table("laundry_properties")
                .select("id, score, deal_status, created_at, dedupe_key, job_id")
                .eq("dedupe_key", dedupe_key)
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            ),
            table="laundry_properties",
            operation="select_dedupe",
            context=ctx,
        )
        row = _row_from_inputs(
            extracted=extracted, economics=economics, scoring=scoring,
            location=location, listing_url=listing_url, source=source,
            job_id=job_id, dedupe_key=dedupe_key,
        )

        if existing.data:
            property_id = existing.data[0]["id"]
            update_payload = dict(row)
            update_payload.pop("id", None)
            update_payload.pop("created_at", None)
            update_payload["updated_at"] = _now()
            log.info("property.update job_id=%s property_id=%s url=%s", job_id, property_id, listing_url)
            res = _execute_write(
                lambda: (
                    supabase.table("laundry_properties")
                    .update(update_payload)
                    .eq("id", property_id)
                    .select("id, job_id, listing_url, deal_status, score")
                    .execute()
                ),
                table="laundry_properties",
                operation="update",
                context={**ctx, "property_id": property_id, "payload_keys": sorted(update_payload.keys())},
            )
            if not res.data:
                return False, None, f"property_update_returned_no_rows property_id={property_id}"
            log.info(
                "property.update OK job_id=%s property_id=%s deal_status=%s score=%s",
                job_id, property_id, res.data[0].get("deal_status"), res.data[0].get("score"),
            )
            return True, {"id": property_id, "duplicate": True}, None

        property_id = str(uuid.uuid4())
        row["id"] = property_id
        row["created_at"] = _now()
        log.info("property.insert job_id=%s property_id=%s url=%s", job_id, property_id, listing_url)
        res = _execute_write(
            lambda: supabase.table("laundry_properties").insert(row).select(
                "id, job_id, listing_url, deal_status, score"
            ).execute(),
            table="laundry_properties",
            operation="insert",
            context={**ctx, "property_id": property_id, "payload_keys": sorted(row.keys())},
        )
        if not res.data:
            return False, None, f"property_insert_returned_no_rows property_id={property_id}"
        log.info(
            "property.insert OK job_id=%s property_id=%s deal_status=%s score=%s",
            job_id, property_id, res.data[0].get("deal_status"), res.data[0].get("score"),
        )
        return True, {"id": property_id, "duplicate": False}, None
    except RuntimeError as exc:
        return False, None, str(exc)
    except Exception as exc:
        log.exception(
            "upsert_property failed job_id=%s url=%s dedupe=%s",
            job_id, listing_url, dedupe_key[:12],
        )
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
        "lat": _finite_float(location.get("lat")),
        "lng": _finite_float(location.get("lng")),
        "property_type": extracted.get("property_type"),
        "acquisition_type": extracted.get("acquisition_type") or economics.get("acquisition_type"),
        "floor_area_m2": _finite_float(economics.get("floor_area_m2") or extracted.get("floor_area_m2")),
        "asking_price": _finite_float(extracted.get("asking_price")),
        "asking_rent_month": _finite_float(extracted.get("asking_rent_month")),
        "washer_count": _safe_int(economics.get("washer_count"), 0) if economics.get("washer_count") is not None else None,
        "dryer_count": _safe_int(economics.get("dryer_count"), 0) if economics.get("dryer_count") is not None else None,
        "expected_revenue_eur": _finite_float(economics.get("expected_revenue_eur")),
        "ebitda_eur": _finite_float(economics.get("ebitda_eur")),
        "operating_margin": _finite_float(economics.get("operating_margin")),
        "payback_years": _finite_float(economics.get("payback_years")),
        "score": _safe_int(scoring.get("score", 0), 0),
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
    if not property_id:
        return False, None, "missing_property_id"

    analysis_id = str(uuid.uuid4())
    payload = {
        "id": analysis_id,
        "property_id": property_id,
        "extracted": _json_safe(extracted),
        "economics": _json_safe(economics),
        "scoring": _json_safe(scoring),
        "location": _json_safe(location),
        "due_diligence": _json_safe(due_diligence),
        "memo_md": memo_md or "",
        "assumptions_version": assumptions_version,
        "created_at": _now(),
    }
    ctx = {"property_id": property_id, "analysis_id": analysis_id, "table": "laundry_analyses"}
    log.info("analysis.insert start property_id=%s analysis_id=%s", property_id, analysis_id)
    try:
        res = _execute_write(
            lambda: supabase.table("laundry_analyses").insert(payload).select("id, property_id").execute(),
            table="laundry_analyses",
            operation="insert",
            context=ctx,
        )
        if not res.data:
            return False, None, f"analysis_insert_returned_no_rows property_id={property_id}"
        log.info(
            "analysis.insert OK property_id=%s analysis_id=%s memo_len=%s",
            property_id, analysis_id, len(memo_md or ""),
        )
        return True, analysis_id, None
    except RuntimeError as exc:
        return False, None, str(exc)
    except Exception as exc:
        log.exception(
            "insert_analysis failed property_id=%s analysis_id=%s: %s",
            property_id, analysis_id, exc,
        )
        return False, None, str(exc)


def create_partial_property(
    *,
    listing_url: str,
    job_id: Optional[str],
    extracted: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    source: str = "url_scan",
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Persist a minimal property row when detail scrape/extraction fails."""
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    if not listing_url:
        return False, None, "missing_listing_url"

    ok_schema, schema_err = check_laundry_schema()
    if not ok_schema:
        return False, None, schema_err

    extracted = dict(extracted or {})
    dedupe_key = normalization.make_dedupe_key(
        listing_url=listing_url,
        address=extracted.get("address"),
        city=extracted.get("city"),
        floor_area_m2=extracted.get("floor_area_m2"),
    )
    ctx = {
        "job_id": job_id,
        "listing_url": listing_url,
        "dedupe_key": dedupe_key[:12],
        "table": "laundry_properties",
        "deal_status": "extraction_failed",
    }
    verdict = (error or "Listing detail could not be extracted")[:500]
    row = {
        "source": source,
        "job_id": job_id,
        "listing_url": listing_url,
        "dedupe_key": dedupe_key,
        "address": extracted.get("address"),
        "city": extracted.get("city") or "Barcelona",
        "neighbourhood": extracted.get("neighbourhood"),
        "property_type": extracted.get("property_type"),
        "acquisition_type": extracted.get("acquisition_type"),
        "floor_area_m2": _finite_float(extracted.get("floor_area_m2")),
        "asking_price": _finite_float(extracted.get("asking_price")),
        "asking_rent_month": _finite_float(extracted.get("asking_rent_month")),
        "score": 0,
        "verdict": verdict,
        "classification": "extraction_failed",
        "deal_status": "extraction_failed",
        "raw_extracted": _json_safe({**extracted, "description": extracted.get("description")}),
    }

    try:
        existing = _execute_write(
            lambda: (
                supabase.table("laundry_properties")
                .select("id, job_id, listing_url, deal_status")
                .eq("dedupe_key", dedupe_key)
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            ),
            table="laundry_properties",
            operation="select_dedupe",
            context=ctx,
        )
        if existing.data:
            property_id = existing.data[0]["id"]
            update_payload = dict(row)
            update_payload["updated_at"] = _now()
            log.info(
                "partial_property.update job_id=%s property_id=%s url=%s",
                job_id, property_id, listing_url,
            )
            res = _execute_write(
                lambda: (
                    supabase.table("laundry_properties")
                    .update(update_payload)
                    .eq("id", property_id)
                    .select("id, job_id, listing_url, deal_status")
                    .execute()
                ),
                table="laundry_properties",
                operation="update",
                context={**ctx, "property_id": property_id},
            )
            if not res.data:
                return False, None, f"partial_property_update_empty property_id={property_id}"
            return True, {"id": property_id, "duplicate": True}, None

        property_id = str(uuid.uuid4())
        row["id"] = property_id
        row["created_at"] = _now()
        log.info(
            "partial_property.insert job_id=%s property_id=%s url=%s dedupe=%s",
            job_id, property_id, listing_url, dedupe_key[:12],
        )
        res = _execute_write(
            lambda: supabase.table("laundry_properties").insert(row).select(
                "id, job_id, listing_url, deal_status"
            ).execute(),
            table="laundry_properties",
            operation="insert",
            context={**ctx, "property_id": property_id},
        )
        if not res.data:
            return False, None, f"partial_property_insert_empty property_id={property_id}"
        return True, {"id": property_id, "duplicate": False}, None
    except RuntimeError as exc:
        return False, None, str(exc)
    except Exception as exc:
        log.exception(
            "create_partial_property failed job_id=%s url=%s: %s",
            job_id, listing_url, exc,
        )
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def list_properties(*, deal_status: Optional[str] = None, limit: int = 100,
                     include_deleted: bool = False, enrich: bool = True) -> List[Dict[str, Any]]:
    if supabase is None:
        return []
    try:
        q = supabase.table("laundry_properties").select("*").order("score", desc=True).limit(limit)
        if deal_status:
            q = q.eq("deal_status", deal_status)
        if not include_deleted:
            q = q.is_("deleted_at", "null")
        res = q.execute()
        props = [normalize_property_row(r) for r in (res.data or []) if normalize_property_row(r)]
        if enrich and props:
            analyses = _latest_analyses_for_properties([p["id"] for p in props if p.get("id")])
            props = [_attach_pipeline_snapshot(p, analyses.get(p["id"])) for p in props]
        return props
    except Exception as exc:
        log.warning("list_properties failed: %s", exc)
        return []


def _attach_pipeline_snapshot(
    prop: Dict[str, Any],
    ana: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge latest analysis economics / scoring onto a property card for pipeline UI."""
    if not ana:
        dd_empty = prop.get("risk_flags") or []
        prop["risk_count"] = len(dd_empty) if isinstance(dd_empty, list) else 0
        prop["warning_count"] = 0
        prop["dd_items_count"] = 0
        return prop

    scoring = ana.get("scoring") or ana.get("score") or {}
    dd = ana.get("due_diligence") or {}
    economics = ana.get("economics") or {}
    location = ana.get("location") or {}
    auto = scoring.get("auto_scores") or {}
    sub = auto.get("sub_components") or {}

    risks = dd.get("red_flags") or dd.get("risks") or []
    weaknesses = dd.get("weaknesses") or []
    checklist = dd.get("due_diligence_checklist") or dd.get("checklist") or []
    if not isinstance(risks, list):
        risks = [str(risks)] if risks else []
    if not isinstance(weaknesses, list):
        weaknesses = [str(weaknesses)] if weaknesses else []
    if not isinstance(checklist, list):
        checklist = [str(checklist)] if checklist else []

    locker_rev = sum(
        float(economics.get(k) or 0)
        for k in ("amazon_locker_eur_year", "inpost_locker_eur_year", "locker_revenue_eur")
    )
    vending_rev = sum(
        float(economics.get(k) or 0)
        for k in (
            "detergent_vending_eur_year",
            "snack_vending_eur_year",
            "drink_vending_eur_year",
            "vending_revenue_eur",
        )
    )
    upside = economics.get("secondary_revenue_eur") or economics.get("ancillary_revenue_eur")
    if upside is None and (locker_rev or vending_rev):
        upside = locker_rev + vending_rev

    memo_md = ana.get("memo_md") or ana.get("ic_memo") or ""
    ai_summary = _memo_summary(memo_md) or prop.get("verdict")

    prop["analysis_id"] = ana.get("id")
    prop["memo_preview"] = memo_md[:480] if memo_md else prop.get("memo_preview")
    prop["has_memo"] = bool(memo_md)
    prop["risk_flags"] = risks
    prop["expected_revenue_eur"] = prop.get("expected_revenue_eur") or economics.get("expected_revenue_eur")
    prop["ebitda_eur"] = prop.get("ebitda_eur") or economics.get("ebitda_eur")
    prop["operating_margin"] = prop.get("operating_margin") or economics.get("operating_margin")
    prop["payback_years"] = prop.get("payback_years") or economics.get("payback_years")
    prop["total_investment_eur"] = economics.get("total_investment_eur")
    prop["yield_pct"] = economics.get("yield_pct") or economics.get("irr_estimate_pct")
    prop["locker_revenue_eur"] = locker_rev or None
    prop["vending_revenue_eur"] = vending_rev or None
    prop["upside_potential_eur"] = upside
    prop["demand_score"] = sub.get("demand_signal") or location.get("destination_intensity")
    prop["competition_score"] = auto.get("competition_score") or sub.get("competition")
    prop["risk_count"] = len(risks)
    prop["warning_count"] = len(weaknesses)
    prop["dd_items_count"] = len(checklist)
    prop["critical_issues"] = risks[:3]
    prop["ai_summary"] = ai_summary
    if not prop.get("confidence_band"):
        conf = scoring.get("confidence") or {}
        prop["confidence_band"] = conf.get("band")
    return prop


def _memo_summary(memo_md: str, *, max_sentences: int = 3) -> str:
    if not memo_md:
        return ""
    text = memo_md.replace("#", " ").replace("*", " ").replace("`", " ")
    text = " ".join(text.split())
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not parts:
        return text[:280]
    return " ".join(parts[:max_sentences])[:320]


def normalize_property_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Map DB columns to the frontend LaundryProperty contract."""
    if not row:
        return None
    out = dict(row)
    if out.get("lat") is not None:
        out["latitude"] = out["lat"]
    if out.get("lng") is not None:
        out["longitude"] = out["lng"]
    out.setdefault("status", out.get("deal_status") or "unknown")
    raw = out.get("raw_extracted")
    if isinstance(raw, dict):
        if not out.get("description") and raw.get("description"):
            out["description"] = raw.get("description")
        if not out.get("address") and raw.get("address"):
            out["address"] = raw.get("address")
        if not out.get("title") and raw.get("title"):
            out["title"] = raw.get("title")
    scoring = out.pop("scoring", None) if isinstance(out.get("scoring"), dict) else None
    if scoring and not out.get("confidence_band"):
        conf = scoring.get("confidence") or {}
        out["confidence_band"] = conf.get("band")
    return out


def normalize_analysis_row(ana: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Map laundry_analyses row to the frontend LaundryAnalysis contract."""
    if not ana:
        return None
    scoring = ana.get("scoring") or {}
    return {
        "id": ana.get("id"),
        "property_id": ana.get("property_id"),
        "input": ana.get("extracted") or {},
        "location": ana.get("location") or {},
        "economics": ana.get("economics") or {},
        "score": scoring,
        "due_diligence": ana.get("due_diligence") or {},
        "assumptions_used": {"version": ana.get("assumptions_version")},
        "verdict": scoring.get("verdict"),
        "classification": scoring.get("classification"),
        "ic_memo": ana.get("memo_md"),
        "created_at": ana.get("created_at"),
    }


def normalize_job_row(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Lift scan-form fields from payload JSON onto the job object for the UI."""
    if not job:
        return None
    out = dict(job)
    payload = out.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    filters = out.get("filters") or payload.get("filters") or {}
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except Exception:
            filters = {}
    out["search_type"] = (
        out.get("search_type")
        or payload.get("search_type")
        or (filters.get("search_type") if isinstance(filters, dict) else None)
    )
    out["property_type"] = out.get("property_type") or (
        filters.get("property_type") if isinstance(filters, dict) else None
    )
    out["acquisition_type"] = out.get("acquisition_type") or (
        filters.get("acquisition_type") if isinstance(filters, dict) else None
    )
    if out.get("listing_limit") is None:
        out["listing_limit"] = payload.get("listing_limit") or out.get("listing_limit")
    return out


def get_property(property_id: str) -> Optional[Dict[str, Any]]:
    if supabase is None or not property_id:
        return None
    try:
        res = (
            supabase.table("laundry_properties")
            .select("*")
            .eq("id", property_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        prop = normalize_property_row(res.data[0])
        ana = (
            supabase.table("laundry_analyses")
            .select("*")
            .eq("property_id", property_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if prop is not None:
            prop["latest_analysis"] = normalize_analysis_row((ana.data or [None])[0])
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
    if supabase is None or not job_id:
        return None
    try:
        res = supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute()
        if not res.data:
            return None
        job = normalize_job_row(res.data[0])
        job["properties"] = list_job_properties(job_id)
        return job
    except Exception as exc:
        log.warning("get_scan_job failed: %s", exc)
        return None


def get_listing_results(job_id: str) -> List[Dict[str, Any]]:
    """Return scan_listing_results rows for a laundry job."""
    if supabase is None or not job_id:
        return []
    try:
        res = (
            supabase.table("scan_listing_results")
            .select("*")
            .eq("job_id", job_id)
            .is_("deleted_at", "null")
            .order("listing_index")
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.warning("get_listing_results failed: %s", exc)
        return []


def list_job_properties(job_id: str) -> List[Dict[str, Any]]:
    """Full property rows for a scan job, enriched with latest analysis snippets."""
    if supabase is None or not job_id:
        return []
    try:
        res = (
            supabase.table("laundry_properties")
            .select("*")
            .eq("job_id", job_id)
            .is_("deleted_at", "null")
            .order("score", desc=True)
            .limit(200)
            .execute()
        )
        rows = list(res.data or [])

        if not rows:
            listing_rows = get_listing_results(job_id)
            property_ids = [
                r["property_id"] for r in listing_rows
                if r.get("property_id")
                and r.get("status") in ("success", "extraction_failed", "failed")
            ]
            if property_ids:
                log.info(
                    "list_job_properties fallback via scan_listing_results job_id=%s ids=%s",
                    job_id, property_ids,
                )
                res = (
                    supabase.table("laundry_properties")
                    .select("*")
                    .in_("id", property_ids)
                    .is_("deleted_at", "null")
                    .order("score", desc=True)
                    .execute()
                )
                rows = list(res.data or [])

        if not rows:
            return []
        prop_ids = [r["id"] for r in rows if r.get("id")]
        analyses_by_prop: Dict[str, Dict[str, Any]] = {}
        if prop_ids:
            ana_res = (
                supabase.table("laundry_analyses")
                .select("id, property_id, memo_md, scoring, due_diligence, economics, location, created_at")
                .in_("property_id", prop_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for ana in ana_res.data or []:
                pid = ana.get("property_id")
                if pid and pid not in analyses_by_prop:
                    analyses_by_prop[pid] = ana
        enriched: List[Dict[str, Any]] = []
        for row in rows:
            prop = normalize_property_row(row)
            if not prop:
                continue
            ana = analyses_by_prop.get(prop["id"])
            if ana:
                prop = _attach_pipeline_snapshot(prop, ana)
            enriched.append(prop)
        return enriched
    except Exception as exc:
        log.warning("list_job_properties failed: %s", exc)
        return []


def get_job_memos(job_id: str) -> List[Dict[str, Any]]:
    """Memo references for every property produced by a scan job."""
    props = list_job_properties(job_id)
    memos: List[Dict[str, Any]] = []
    for prop in props:
        if not prop.get("has_memo"):
            continue
        memos.append({
            "property_id": prop.get("id"),
            "analysis_id": prop.get("analysis_id"),
            "address": prop.get("address"),
            "listing_url": prop.get("listing_url"),
            "deal_status": prop.get("deal_status"),
            "score": prop.get("score"),
            "memo_preview": prop.get("memo_preview"),
        })
    return memos


def listing_row_to_property_card(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Synthesize a property card from scan_listing_results when DB row is missing."""
    if not row:
        return None
    result = row.get("result") or {}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            result = {}
    if not isinstance(result, dict):
        result = {}
    property_id = row.get("property_id") or result.get("property_id")
    if not property_id:
        return None
    deal_status = row.get("deal_status") or result.get("deal_status") or row.get("status")
    return {
        "id": property_id,
        "job_id": row.get("job_id"),
        "listing_url": row.get("listing_url"),
        "address": row.get("address") or result.get("address"),
        "city": row.get("city") or result.get("city") or "Barcelona",
        "neighbourhood": row.get("neighbourhood") or result.get("neighbourhood"),
        "title": row.get("title") or result.get("title"),
        "description": row.get("description") or result.get("description"),
        "floor_area_m2": result.get("floor_area_m2"),
        "asking_price": result.get("asking_price"),
        "asking_rent_month": result.get("asking_rent_month"),
        "score": row.get("score") or result.get("score") or 0,
        "verdict": result.get("verdict") or row.get("error_message"),
        "deal_status": deal_status,
        "status": deal_status or "unknown",
        "extraction_error": row.get("error_message"),
    }


def merge_scan_properties(
    properties: List[Dict[str, Any]],
    listings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Ensure every persisted listing result appears as a pipeline card."""
    by_id = {p["id"]: p for p in properties if p.get("id")}
    merged = list(properties)
    for row in listings:
        pid = row.get("property_id")
        if not pid or pid in by_id:
            continue
        card = listing_row_to_property_card(row)
        if card:
            merged.append(normalize_property_row(card) or card)
            by_id[pid] = card
    merged.sort(key=lambda p: (p.get("deal_status") == "extraction_failed", -(p.get("score") or 0)))
    return merged


def build_scan_summary(
    job: Dict[str, Any],
    listings: List[Dict[str, Any]],
    properties: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate scan counters + deal buckets for the frontend."""
    persisted_rows = [r for r in listings if r.get("property_id")]
    scored_rows = [r for r in listings if r.get("status") == "success" and r.get("property_id")]
    extraction_failed_rows = [
        r for r in listings
        if r.get("status") == "extraction_failed" or r.get("deal_status") == "extraction_failed"
    ]
    failed_rows = [r for r in listings if r.get("status") == "failed" and not r.get("property_id")]
    skipped_rows = [r for r in listings if r.get("status") == "skipped"]
    approved = [p for p in properties if p.get("deal_status") == "approved_candidate"]
    manual = [p for p in properties if p.get("deal_status") == "manual_review"]
    rejected = [p for p in properties if p.get("deal_status") == "rejected"]
    extraction_failed_props = [p for p in properties if p.get("deal_status") == "extraction_failed"]
    persisted_count = len(persisted_rows) or len(properties)
    return {
        "scanned_count": job.get("listings_done") or len(listings),
        "listings_total": job.get("listings_total") or len(listings),
        "listings_done": job.get("listings_done") or 0,
        "listings_failed": job.get("listings_failed") or len(failed_rows),
        "extraction_failed_count": len(extraction_failed_rows) or len(extraction_failed_props),
        "approved_count": job.get("approved_count") or len(approved),
        "manual_review_count": job.get("manual_review_count") or len(manual),
        "rejected_count": job.get("rejected_count") or len(rejected),
        "skipped_count": len(skipped_rows),
        "persisted_count": persisted_count,
        "property_count": len(properties),
        "listing_result_count": len(listings),
        "approved_candidates": approved,
        "manual_review_deals": manual,
        "rejected_deals": rejected,
        "extraction_failed_deals": extraction_failed_props,
        "results_missing": (
            (job.get("listings_done") or 0) > 0
            and len(listings) == 0
            and len(properties) == 0
        ),
        "summary_property_mismatch": (
            (job.get("listings_done") or 0) > 0
            and persisted_count == 0
        ),
    }


def build_scan_response(job_id: str) -> Optional[Dict[str, Any]]:
    """Full scan detail payload for GET /laundry/scans/{id}."""
    job = get_scan_job(job_id)
    if not job:
        return None
    steps = list_pipeline_steps(job_id)
    listings = get_listing_results(job_id)
    properties = job.get("properties") or list_job_properties(job_id)
    properties = merge_scan_properties(properties, listings)
    memos = get_job_memos(job_id)
    summary = build_scan_summary(job, listings, properties)

    payload = job.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    search_diagnostics = payload.get("search_diagnostics") if isinstance(payload, dict) else None
    discover_step = next((s for s in steps if s.get("step_key") == JOB_STEP_DISCOVER), None)
    if discover_step:
        out = (
            discover_step.get("output_data")
            or discover_step.get("result")
            or discover_step.get("output")
            or {}
        )
        if isinstance(out, dict) and out.get("search_diagnostics"):
            search_diagnostics = out["search_diagnostics"]

    return {
        "success": True,
        "job": job,
        "steps": steps,
        "listings": listings,
        "properties": properties,
        "memos": memos,
        "summary": summary,
        "search_diagnostics": search_diagnostics,
    }


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
    if supabase is None:
        return []
    try:
        q = (
            supabase.table("scan_jobs")
            .select("*")
            .eq("job_type", LAUNDRY_JOB_TYPE)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if status:
            q = q.eq("status", status)
        res = q.execute()
        return [normalize_job_row(j) for j in (res.data or []) if j]
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
                           error_message: Optional[str] = None,
                           address: Optional[str] = None,
                           city: Optional[str] = None,
                           neighbourhood: Optional[str] = None,
                           title: Optional[str] = None,
                           description: Optional[str] = None) -> bool:
    if supabase is None:
        log.warning("record_listing_result skipped — supabase unavailable job_id=%s", job_id)
        return False

    merged_result = {
        **(result or {}),
        "property_id": property_id,
        "deal_status": deal_status,
        "score": score,
        "address": address or (result or {}).get("address"),
        "city": city or (result or {}).get("city"),
        "neighbourhood": neighbourhood or (result or {}).get("neighbourhood"),
        "title": title or (result or {}).get("title"),
        "description": description or (result or {}).get("description"),
    }
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "listing_index": listing_index,
        "listing_url": listing_url,
        "status": status,
        "result": _json_safe(merged_result),
        "property_id": property_id,
        "deal_status": deal_status,
        "score": score,
        "error_message": (error_message or "")[:2000] if error_message else None,
        "updated_at": _now(),
    }
    if address is not None:
        payload["address"] = address
    if city is not None:
        payload["city"] = city
    if neighbourhood is not None:
        payload["neighbourhood"] = neighbourhood
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description

    def _write(data: Dict[str, Any]) -> None:
        existing = (
            supabase.table("scan_listing_results")
            .select("id")
            .eq("job_id", job_id)
            .eq("listing_index", listing_index)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase.table("scan_listing_results").update(data).eq("id", existing.data[0]["id"]).execute()
        else:
            data["created_at"] = _now()
            supabase.table("scan_listing_results").insert(data).execute()

    try:
        _write(payload)
        log.info(
            "record_listing_result OK job_id=%s idx=%s property_id=%s url=%s status=%s "
            "address=%s city=%s",
            job_id, listing_index, property_id, listing_url, status, address, city,
        )
        if property_id:
            log.info(
                "property_id saved job_id=%s idx=%s property_id=%s listing_url=%s",
                job_id, listing_index, property_id, listing_url,
            )
        return True
    except Exception as exc:
        # Optional top-level columns may be missing on older DBs — retry without them.
        msg = str(exc).lower()
        if any(k in msg for k in ("address", "city", "neighbourhood", "title", "description", "column")):
            for key in ("address", "city", "neighbourhood", "title", "description"):
                payload.pop(key, None)
            try:
                _write(payload)
                log.info(
                    "record_listing_result OK (json only) job_id=%s idx=%s property_id=%s",
                    job_id, listing_index, property_id,
                )
                return True
            except Exception as retry_exc:
                log.warning(
                    "record_listing_result failed job_id=%s idx=%s property_id=%s: %s",
                    job_id, listing_index, property_id, retry_exc,
                )
                return False
        log.warning(
            "record_listing_result failed job_id=%s idx=%s property_id=%s: %s",
            job_id, listing_index, property_id, exc,
        )
        return False


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


# ---------------------------------------------------------------------------
# Exports (laundry_exports ledger + property queries for workbooks)
# ---------------------------------------------------------------------------
PIPELINE_EXPORT_SCOPES = {
    "approved": "approved_candidate",
    "manual_review": "manual_review",
    "rejected": "rejected",
    "failed": "extraction_failed",
}


def normalize_export_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    export_id = row.get("id")
    return {
        "id": export_id,
        "format": row.get("format") or "excel",
        "export_type": row.get("export_type") or row.get("format") or "excel",
        "label": row.get("label"),
        "file_path": row.get("file_path") or "",
        "size_bytes": int(row.get("size_bytes") or 0),
        "created_at": row.get("created_at"),
        "property_id": row.get("property_id"),
        "job_id": row.get("job_id"),
        "created_by": row.get("created_by"),
        "download_url": f"/laundry/exports/{export_id}/download" if export_id else None,
    }


def create_export_record(
    *,
    file_path: str,
    size_bytes: int,
    fmt: str = "excel",
    export_type: Optional[str] = None,
    label: Optional[str] = None,
    property_id: Optional[str] = None,
    job_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    if supabase is None:
        return False, None, "supabase_client_not_initialised"
    if not file_path:
        return False, None, "file_path_required"
    try:
        payload: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "format": fmt or "excel",
            "export_type": export_type or fmt or "excel",
            "label": label,
            "file_path": file_path,
            "size_bytes": int(size_bytes or 0),
            "created_at": _now(),
        }
        if property_id:
            payload["property_id"] = property_id
        if job_id:
            payload["job_id"] = job_id
        if created_by:
            payload["created_by"] = created_by
        res = supabase.table("laundry_exports").insert(payload).execute()
        row = (res.data or [None])[0]
        if not row:
            return False, None, "insert_failed"
        return True, normalize_export_row(row), None
    except Exception as exc:
        log.warning("create_export_record failed: %s", exc)
        return False, None, str(exc)


def get_export(export_id: str) -> Optional[Dict[str, Any]]:
    if supabase is None or not export_id:
        return None
    try:
        res = (
            supabase.table("laundry_exports")
            .select("*")
            .eq("id", export_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return normalize_export_row(res.data[0])
    except Exception as exc:
        log.warning("get_export failed: %s", exc)
        return None


def list_exports(
    *,
    limit: int = 100,
    property_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if supabase is None:
        return []
    try:
        q = (
            supabase.table("laundry_exports")
            .select("*")
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if property_id:
            q = q.eq("property_id", property_id)
        if job_id:
            q = q.eq("job_id", job_id)
        res = q.execute()
        return [normalize_export_row(r) for r in (res.data or []) if normalize_export_row(r)]
    except Exception as exc:
        log.warning("list_exports failed: %s", exc)
        return []


def _latest_analyses_for_properties(property_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    analyses_by_prop: Dict[str, Dict[str, Any]] = {}
    if supabase is None or not property_ids:
        return analyses_by_prop
    try:
        ana_res = (
            supabase.table("laundry_analyses")
            .select("*")
            .in_("property_id", property_ids)
            .order("created_at", desc=True)
            .execute()
        )
        for ana in ana_res.data or []:
            pid = ana.get("property_id")
            if pid and pid not in analyses_by_prop:
                analyses_by_prop[pid] = normalize_analysis_row(ana) or {}
    except Exception as exc:
        log.warning("_latest_analyses_for_properties failed: %s", exc)
    return analyses_by_prop


def list_properties_for_export(
    *,
    deal_status: Optional[str] = None,
    job_id: Optional[str] = None,
    property_ids: Optional[List[str]] = None,
    limit: int = 500,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Return property rows plus latest analysis map for export builders."""
    if supabase is None:
        return [], {}
    try:
        q = (
            supabase.table("laundry_properties")
            .select("*")
            .is_("deleted_at", "null")
            .order("score", desc=True)
            .limit(limit)
        )
        if deal_status:
            q = q.eq("deal_status", deal_status)
        if job_id:
            q = q.eq("job_id", job_id)
        if property_ids:
            q = q.in_("id", property_ids)
        res = q.execute()
        props = [normalize_property_row(r) for r in (res.data or []) if normalize_property_row(r)]
        analyses = _latest_analyses_for_properties([p["id"] for p in props if p.get("id")])
        return props, analyses
    except Exception as exc:
        log.warning("list_properties_for_export failed: %s", exc)
        return [], {}


def resolve_pipeline_scope(scope: str) -> Tuple[Optional[str], str]:
    """Map UI scope key to deal_status filter and human label."""
    key = (scope or "entire").strip().lower()
    if key in ("entire", "all", "pipeline", "entire_pipeline"):
        return None, "Entire Pipeline"
    if key in PIPELINE_EXPORT_SCOPES:
        label = key.replace("_", " ").title()
        return PIPELINE_EXPORT_SCOPES[key], label
    return None, key.replace("_", " ").title()
