"""K.U.A. laundry vertical FastAPI router.

Endpoints (prefix ``/laundry``):

* ``GET    /laundry/health``
* ``GET    /laundry/search-providers``        — list provider keys for the URL builder
* ``POST   /laundry/search-url``              — generate a portal search URL from filters
* ``POST   /laundry/scans``                   — launch async or inline scan
* ``GET    /laundry/scans``                   — list laundry jobs (frontend alias)
* ``GET    /laundry/scans/{id}``              — job status + steps + properties
* ``POST   /laundry/scans/{id}/resume``       — re-queue a finished/failed job
* ``GET    /laundry/jobs``                    — alias of /laundry/scans
* ``GET    /laundry/jobs/{id}``               — job row
* ``DELETE /laundry/jobs/{id}``               — cancel a job
* ``POST   /laundry/analyse``                 — synchronous one-shot underwriting
* ``GET    /laundry/properties``              — list scored properties
* ``GET    /laundry/properties/{id}``         — property + latest memo
* ``DELETE /laundry/properties/{id}``         — soft delete
* ``POST   /laundry/properties/{id}/restore``
* ``GET    /laundry/deals/top``
* ``GET    /laundry/deals/manual-review``
* ``GET    /laundry/deals/approved``
* ``GET    /laundry/deals/rejected``
* ``GET    /laundry/settings/assumptions``
* ``GET    /laundry/settings/autonomous``     — autonomous sequencer defaults
* ``PUT    /laundry/settings/autonomous``     — persist autonomous defaults
* ``POST   /laundry/properties/{id}/exports`` — single-deal Excel workbook
* ``POST   /laundry/exports/pipeline``        — pipeline Excel export by scope
* ``POST   /laundry/exports/bulk``            — bulk / selected pipeline export
* ``POST   /laundry/scans/{id}/exports``      — scan-scoped pipeline export
* ``GET    /laundry/exports``                 — export history
* ``GET    /laundry/exports/formats``
* ``GET    /laundry/exports/{id}/download``   — re-download persisted artefact
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from laundry import exports, pipeline, store, url_builder

log = logging.getLogger("kua.laundry.api")

router = APIRouter(prefix="/laundry", tags=["laundry"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ScanPayload(BaseModel):
    property_type: Optional[str] = Field(default=None, description="existing_laundromat | empty_commercial | retail | mixed_use | industrial")
    acquisition_type: Optional[str] = Field(default=None, description="buy | rent")
    search_type: Optional[str] = Field(default=None, description="automatic_scan | manual_url | area_search")

    listing_url: Optional[str] = None
    search_url: Optional[str] = None
    raw_listing_text: Optional[str] = None
    seed_text: Optional[str] = None

    listing_limit: int = Field(default=20, ge=1, le=100)
    run_in_background: bool = True
    async_mode: Optional[bool] = None

    llm_memo_polish: bool = False
    polish_with_llm: Optional[bool] = None
    use_llm_extraction: bool = True

    neighbourhood_filters: List[str] = Field(default_factory=list)
    max_size_sqm: Optional[float] = Field(default=80.0, ge=10, le=2000)
    min_size_sqm: Optional[float] = Field(default=None, ge=0, le=2000)
    max_price_eur: Optional[float] = Field(default=None, ge=0)
    max_rent_month_eur: Optional[float] = Field(default=None, ge=0)
    city: Optional[str] = "Barcelona"
    ground_floor_only: bool = True

    auto_generate_url: bool = True
    search_provider: Optional[str] = Field(default="idealista", description="idealista | fotocasa | habitaclia | google_maps | custom")
    search_provider_extras: Dict[str, str] = Field(default_factory=dict)

    scoring_overrides: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    overrides: Dict[str, Any] = Field(default_factory=dict)

    autonomous_mode: bool = True
    operation_mode: str = Field(default="balanced", description="conservative | balanced | aggressive")
    max_attempts: int = Field(default=3, ge=1, le=10)
    concurrency: int = Field(default=2, ge=1, le=8)
    timeout_level: str = Field(default="normal", description="short | normal | long")
    auto_export: bool = True

    class Config:
        extra = "ignore"

    def resolved_url(self) -> Optional[str]:
        return self.listing_url or self.search_url

    def resolved_text(self) -> Optional[str]:
        return self.raw_listing_text or self.seed_text

    def resolved_async(self) -> bool:
        if self.async_mode is not None:
            return bool(self.async_mode)
        return bool(self.run_in_background)

    def resolved_filters(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(self.filters or {})
        if self.neighbourhood_filters: merged["neighbourhood_filters"] = list(self.neighbourhood_filters)
        if self.max_size_sqm: merged["max_size_sqm"] = float(self.max_size_sqm)
        if self.min_size_sqm: merged["min_size_sqm"] = float(self.min_size_sqm)
        if self.max_price_eur: merged["max_price_eur"] = float(self.max_price_eur)
        if self.max_rent_month_eur: merged["max_rent_month_eur"] = float(self.max_rent_month_eur)
        if self.city: merged["city"] = self.city
        merged["ground_floor_only"] = bool(self.ground_floor_only)
        if self.property_type: merged["property_type"] = self.property_type
        if self.acquisition_type: merged["acquisition_type"] = self.acquisition_type
        if self.search_type: merged["search_type"] = self.search_type
        return merged

    def resolved_overrides(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(self.overrides or {})
        if self.scoring_overrides:
            merged.setdefault("scoring_weights", self.scoring_overrides)
        return merged

    def to_url_builder_payload(self) -> Dict[str, Any]:
        return {
            "acquisition_type": self.acquisition_type or "rent",
            "property_type": self.property_type or "empty_commercial",
            "city": self.city or "Barcelona",
            "neighbourhoods": list(self.neighbourhood_filters or []),
            "max_size_sqm": float(self.max_size_sqm) if self.max_size_sqm else None,
            "min_size_sqm": float(self.min_size_sqm) if self.min_size_sqm else None,
            "max_price_eur": float(self.max_price_eur) if self.max_price_eur else None,
            "max_rent_month_eur": float(self.max_rent_month_eur) if self.max_rent_month_eur else None,
            "ground_floor_only": bool(self.ground_floor_only),
            "listing_limit": int(self.listing_limit or 20),
            "extra_filters": dict(self.search_provider_extras or {}),
        }

    def autonomous_payload(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.autonomous_mode),
            "operation_mode": (self.operation_mode or "balanced").lower(),
            "max_attempts": int(self.max_attempts),
            "concurrency": int(self.concurrency),
            "timeout_level": (self.timeout_level or "normal").lower(),
            "auto_export": bool(self.auto_export),
        }


# ---------------------------------------------------------------------------
# Search URL builder
# ---------------------------------------------------------------------------
class SearchUrlPayload(BaseModel):
    acquisition_type: str = Field(default="rent", description="buy | rent")
    property_type: str = Field(default="empty_commercial",
                                description="existing_laundromat | empty_commercial | retail | mixed_use | industrial")
    city: str = "Barcelona"
    neighbourhoods: List[str] = Field(default_factory=list)
    max_size_sqm: Optional[float] = 80.0
    min_size_sqm: Optional[float] = None
    max_price_eur: Optional[float] = None
    max_rent_month_eur: Optional[float] = None
    ground_floor_only: bool = True
    listing_limit: int = 20
    provider: Optional[str] = "idealista"
    extra_filters: Dict[str, str] = Field(default_factory=dict)
    validate_listing_count: bool = True

    class Config:
        extra = "ignore"


@router.get("/search-providers")
def list_search_providers() -> Dict[str, Any]:
    return {"success": True, "providers": url_builder.list_providers()}


@router.post("/search-url")
def generate_search_url(payload: SearchUrlPayload) -> Dict[str, Any]:
    try:
        if payload.validate_listing_count:
            built = url_builder.resolve_search_url(
                payload.model_dump(), provider=payload.provider, validate=True,
            )
        else:
            built = url_builder.build_search_url(payload.model_dump(), provider=payload.provider)
    except url_builder.UnsupportedFilterError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to generate search URL from selected filters. {exc}",
        )
    return {"success": True, **built.to_dict()}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health")
def laundry_health() -> Dict[str, Any]:
    try:
        from database import supabase as sb
        sb_ok = sb is not None
    except Exception:
        sb_ok = False
    schema_ok, schema_err = store.check_laundry_schema() if sb_ok else (False, "supabase_missing")
    return {
        "success": True,
        "service": "kua-laundry",
        "version": "2.2.0",
        "supabase": "configured" if sb_ok else "missing",
        "laundry_schema": "ready" if schema_ok else "missing",
        "laundry_schema_error": None if schema_ok else schema_err,
    }


# ---------------------------------------------------------------------------
# Scans / jobs
# ---------------------------------------------------------------------------
@router.post("/scans", status_code=202)
def launch_scan(payload: ScanPayload, request: Request) -> JSONResponse:
    url = payload.resolved_url()
    text = payload.resolved_text()

    auto_generated: Optional[Dict[str, Any]] = None
    search_diagnostics: Optional[Dict[str, Any]] = None
    needs_url = (payload.search_type in ("automatic_scan", "area_search", None)) or bool(text is None)
    if not url and not text and needs_url and payload.auto_generate_url:
        try:
            built = url_builder.resolve_search_url(
                payload.to_url_builder_payload(),
                provider=payload.search_provider,
                validate=True,
            )
            url = built.url
            auto_generated = built.to_dict()
            search_diagnostics = (built.diagnostics.to_dict() if built.diagnostics else None)
            log.info(
                "Auto-generated search URL via %s (level=%s count=%s broadened=%s): %s",
                built.provider,
                (search_diagnostics or {}).get("fallback_level"),
                (search_diagnostics or {}).get("listing_count"),
                (search_diagnostics or {}).get("search_broadened"),
                url,
            )
        except url_builder.UnsupportedFilterError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to generate search URL from selected filters. {exc}",
            )
    elif needs_url and payload.search_type in ("automatic_scan", "area_search", None):
        try:
            built = url_builder.resolve_search_url(
                payload.to_url_builder_payload(),
                provider=payload.search_provider,
                validate=True,
            )
            if built.url != url:
                log.info(
                    "Replacing search URL with validated/broader URL: %s → %s",
                    url, built.url,
                )
                url = built.url
            auto_generated = auto_generated or built.to_dict()
            search_diagnostics = (built.diagnostics.to_dict() if built.diagnostics else search_diagnostics)
        except url_builder.UnsupportedFilterError:
            pass

    if not url and not text:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide either `listing_url`/`search_url` or `raw_listing_text`, "
                "or enable `auto_generate_url` so the backend builds one from the filters."
            ),
        )

    filters = payload.resolved_filters()
    overrides = payload.resolved_overrides()
    request_id = getattr(request.state, "request_id", None)
    created_by = request.headers.get("x-user-id")

    if not payload.resolved_async():
        try:
            if url and not text:
                if payload.search_type in ("automatic_scan", "area_search"):
                    result = pipeline.analyse_area(
                        search_url=url, limit=payload.listing_limit,
                        overrides=overrides, filters=filters,
                    )
                else:
                    result = pipeline.analyse_url(
                        url=url, overrides=overrides, filters=filters,
                        use_llm=payload.use_llm_extraction, persist=True,
                    )
            else:
                result = pipeline.analyse_listing(
                    raw_text=text or "", listing_url=url, source="manual_text",
                    overrides=overrides, filters=filters,
                    use_llm=payload.use_llm_extraction, persist=True,
                )
            return JSONResponse(
                status_code=200,
                content={"success": True, "async": False, "status": "completed",
                          "search_url": url, "auto_generated_url": auto_generated,
                          "result": result},
            )
        except Exception as exc:
            log.exception("Inline scan failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"inline_scan_failed: {exc}")

    job_payload = {
        "url": url, "raw_text": text,
        "filters": filters, "overrides": overrides,
        "use_llm_extraction": payload.use_llm_extraction,
        "llm_memo_polish": payload.llm_memo_polish or bool(payload.polish_with_llm),
        "listing_limit": payload.listing_limit,
        "search_type": payload.search_type or ("area_search" if filters.get("search_type") == "area_search" else "manual_url"),
        "search_provider": payload.search_provider or "idealista",
        "auto_generated_url": auto_generated,
        "search_diagnostics": search_diagnostics,
        "autonomous_mode": payload.autonomous_mode,
        "operation_mode": payload.operation_mode,
        "max_attempts": payload.max_attempts,
        "concurrency": payload.concurrency,
        "timeout_level": payload.timeout_level,
        "auto_export": payload.auto_export,
        "autonomous": payload.autonomous_payload(),
    }

    ok, job, err = store.create_scan_job(
        search_url=url or "", payload=job_payload,
        created_by=created_by, request_id=request_id,
    )
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"Could not queue laundry scan job: {err or 'unknown'}. Run the SQL migration in laundry/schema.sql.",
        )

    response: Dict[str, Any] = {
        "success": True, "async": True,
        "job_id": job["id"], "status": job["status"],
        "message": "Laundry scan queued. Poll GET /laundry/scans/{job_id}.",
        "poll_url": f"/laundry/scans/{job['id']}",
        "search_url": url,
    }
    if auto_generated:
        response["auto_generated_url"] = auto_generated
    if search_diagnostics:
        response["search_diagnostics"] = search_diagnostics
    return JSONResponse(status_code=202, content=response)


@router.post("/scan", include_in_schema=False)
def launch_scan_legacy(payload: ScanPayload, request: Request) -> JSONResponse:
    """Backward-compat alias — frontend builds older than v2 may call /laundry/scan."""
    return launch_scan(payload, request)


@router.get("/scans")
def list_scans(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    """List laundry scan jobs (matches existing frontend client)."""
    scans = store.list_laundry_jobs(limit=limit, status=status)
    return {"success": True, "scans": scans, "jobs": scans}


@router.get("/scans/{job_id}")
def get_scan(job_id: str) -> Dict[str, Any]:
    response = store.build_scan_response(job_id)
    if not response:
        raise HTTPException(status_code=404, detail="job_not_found")
    return response


@router.post("/scans/{job_id}/resume")
def resume_scan(job_id: str) -> Dict[str, Any]:
    """Re-queue a finished/failed laundry scan so the worker picks it up again."""
    job = store.get_scan_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job_not_found")
    try:
        from jobs.constants import JOB_QUEUED
    except Exception:
        JOB_QUEUED = "queued"
    existing_listings = store.get_listing_results(job_id)
    resume_from = len([r for r in existing_listings if r.get("property_id") or r.get("status")])
    store.update_job(
        job_id, status=JOB_QUEUED, error_message=None,
        started_at=None, finished_at=None,
        progress_pct=min(int((resume_from / max(job.get("listing_limit") or 1, 1)) * 100), 90),
    )
    return {
        "success": True,
        "job_id": job_id,
        "status": JOB_QUEUED,
        "resume_from_listing": resume_from,
        "message": "Job re-queued; sequencer skips already-processed listings.",
    }


@router.get("/jobs")
def list_jobs(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    return {"success": True, "jobs": store.list_laundry_jobs(limit=limit, status=status)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = store.get_scan_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job_not_found")
    return {"success": True, "job": job}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> Dict[str, Any]:
    ok = store.cancel_job(job_id)
    if not ok: raise HTTPException(status_code=500, detail="cancel_failed")
    return {"success": True, "job_id": job_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Inline analysis (no persistence by default)
# ---------------------------------------------------------------------------
class AnalysePayload(BaseModel):
    raw_text: Optional[str] = None
    listing_url: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    use_llm: bool = True
    persist: bool = False

    class Config:
        extra = "ignore"


@router.post("/analyse")
def analyse_inline(payload: AnalysePayload) -> Dict[str, Any]:
    if not payload.raw_text and not payload.listing_url:
        raise HTTPException(status_code=400, detail="Provide raw_text or listing_url.")
    if payload.listing_url and not payload.raw_text:
        return pipeline.analyse_url(
            url=payload.listing_url, overrides=payload.overrides,
            filters=payload.filters, use_llm=payload.use_llm, persist=payload.persist,
        )
    return pipeline.analyse_listing(
        raw_text=payload.raw_text or "", listing_url=payload.listing_url,
        source="inline", overrides=payload.overrides, filters=payload.filters,
        use_llm=payload.use_llm, persist=payload.persist,
    )


# ---------------------------------------------------------------------------
# Properties + deals
# ---------------------------------------------------------------------------
@router.get("/properties")
def list_properties_endpoint(deal_status: Optional[str] = None, limit: int = 100,
                              include_deleted: bool = False) -> Dict[str, Any]:
    return {"success": True,
            "properties": store.list_properties(deal_status=deal_status, limit=limit, include_deleted=include_deleted)}


@router.get("/properties/{property_id}")
def get_property_endpoint(property_id: str) -> Dict[str, Any]:
    prop = store.get_property(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="property_not_found")
    latest = prop.pop("latest_analysis", None)
    return {
        "success": True,
        "property": prop,
        "latest_analysis": latest,
    }


@router.delete("/properties/{property_id}")
def delete_property_endpoint(property_id: str, reason: str = "manual") -> Dict[str, Any]:
    if not store.soft_delete_property(property_id, reason=reason):
        raise HTTPException(status_code=500, detail="delete_failed")
    return {"success": True, "property_id": property_id, "deleted": True}


@router.post("/properties/{property_id}/restore")
def restore_property_endpoint(property_id: str) -> Dict[str, Any]:
    if not store.restore_property(property_id):
        raise HTTPException(status_code=500, detail="restore_failed")
    return {"success": True, "property_id": property_id, "restored": True}


@router.get("/deals/top")
def deals_top(limit: int = 20) -> Dict[str, Any]:
    rows = store.list_properties(limit=limit)
    return {"success": True, "deals": rows, "top_deals": rows}


@router.get("/deals/manual-review")
def deals_manual(limit: int = 50) -> Dict[str, Any]:
    rows = store.list_properties(deal_status="manual_review", limit=limit)
    return {"success": True, "deals": rows, "manual_review_deals": rows}


@router.get("/deals/approved")
def deals_approved(limit: int = 50) -> Dict[str, Any]:
    rows = store.list_properties(deal_status="approved_candidate", limit=limit)
    return {"success": True, "deals": rows, "approved_candidates": rows}


@router.get("/deals/rejected")
def deals_rejected(limit: int = 50) -> Dict[str, Any]:
    rows = store.list_properties(deal_status="rejected", limit=limit)
    return {"success": True, "deals": rows, "rejected_deals": rows}


# ---------------------------------------------------------------------------
# Settings inspection
# ---------------------------------------------------------------------------
@router.get("/settings/assumptions")
def get_assumptions() -> Dict[str, Any]:
    from laundry.assumptions import default_assumptions
    return {"success": True, "assumptions": default_assumptions().to_dict()}


class AutonomousSettingsPayload(BaseModel):
    autonomous_mode: bool = True
    operation_mode: str = "balanced"
    max_attempts: int = Field(default=3, ge=1, le=10)
    concurrency: int = Field(default=2, ge=1, le=8)
    timeout_level: str = "normal"
    auto_export: bool = True

    class Config:
        extra = "ignore"


@router.get("/settings/autonomous")
def get_autonomous_settings_endpoint() -> Dict[str, Any]:
    from laundry.sequencer import MODE_PRESETS, OPERATION_MODES, TIMEOUT_LEVELS

    settings = store.get_autonomous_settings()
    return {
        "success": True,
        "settings": settings,
        "operation_modes": list(OPERATION_MODES),
        "timeout_levels": list(TIMEOUT_LEVELS),
        "mode_presets": MODE_PRESETS,
    }


@router.put("/settings/autonomous")
def save_autonomous_settings_endpoint(payload: AutonomousSettingsPayload) -> Dict[str, Any]:
    ok, saved, err = store.save_autonomous_settings(payload.model_dump())
    if not ok:
        raise HTTPException(status_code=500, detail=f"settings_save_failed: {err or 'unknown'}")
    return {"success": True, "settings": saved}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
class ExportRequest(BaseModel):
    format: str = Field(default="excel", description="excel")

    class Config:
        extra = "ignore"


class PipelineExportRequest(BaseModel):
    scope: str = Field(
        default="entire",
        description="approved | manual_review | rejected | failed | entire",
    )
    format: str = Field(default="excel")

    class Config:
        extra = "ignore"


class BulkExportRequest(BaseModel):
    property_ids: Optional[List[str]] = None
    scope: Optional[str] = Field(
        default=None,
        description="approved | manual_review | entire when property_ids omitted",
    )
    format: str = Field(default="excel")

    class Config:
        extra = "ignore"


def _require_excel(fmt: str) -> None:
    if (fmt or "excel").lower() not in exports.EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format: {fmt!r}. Supported: {list(exports.EXPORT_FORMATS)}",
        )


def _export_json(record: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "export_id": record["id"],
        "format": record.get("format") or meta.get("format") or "excel",
        "export_type": record.get("export_type"),
        "label": record.get("label"),
        "file_path": record.get("file_path") or meta.get("file_path"),
        "filename": meta.get("filename") or os.path.basename(record.get("file_path") or ""),
        "size_bytes": record.get("size_bytes") or meta.get("size_bytes") or 0,
        "row_count": meta.get("row_count"),
        "download_url": record.get("download_url") or f"/laundry/exports/{record['id']}/download",
    }


def _persist_pipeline_export(
    *,
    properties: List[Dict[str, Any]],
    analyses: Dict[str, Dict[str, Any]],
    label: str,
    export_type: str,
    job: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    if not properties:
        raise HTTPException(status_code=404, detail="no_properties_for_export")
    meta = exports.generate_pipeline_export(
        properties, analyses, label=label, job=job,
    )
    ok, record, err = store.create_export_record(
        file_path=meta["file_path"],
        size_bytes=meta["size_bytes"],
        fmt=meta.get("format") or "excel",
        export_type=export_type,
        label=label,
        job_id=job_id,
        created_by=created_by,
    )
    if not ok or not record:
        raise HTTPException(status_code=500, detail=f"export_persist_failed: {err or 'unknown'}")
    return _export_json(record, meta)


@router.post("/properties/{property_id}/exports")
def create_property_export(
    property_id: str,
    payload: ExportRequest,
    request: Request,
) -> Dict[str, Any]:
    _require_excel(payload.format)
    prop = store.get_property(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="property_not_found")
    analysis = prop.pop("latest_analysis", None)
    job = store.get_scan_job(prop.get("job_id")) if prop.get("job_id") else None
    meta = exports.generate_single_deal_export(prop, analysis, job=job)
    ok, record, err = store.create_export_record(
        file_path=meta["file_path"],
        size_bytes=meta["size_bytes"],
        fmt=meta.get("format") or "excel",
        export_type="single_deal",
        label=prop.get("address") or property_id[:8],
        property_id=property_id,
        job_id=prop.get("job_id"),
        created_by=request.headers.get("x-user-id"),
    )
    if not ok or not record:
        raise HTTPException(status_code=500, detail=f"export_persist_failed: {err or 'unknown'}")
    return _export_json(record, meta)


@router.post("/exports/pipeline")
def export_pipeline(payload: PipelineExportRequest, request: Request) -> Dict[str, Any]:
    _require_excel(payload.format)
    deal_status, label = store.resolve_pipeline_scope(payload.scope)
    export_type = f"pipeline_{(payload.scope or 'entire').strip().lower()}"
    properties, analyses = store.list_properties_for_export(deal_status=deal_status, limit=500)
    return _persist_pipeline_export(
        properties=properties,
        analyses=analyses,
        label=label,
        export_type=export_type,
        created_by=request.headers.get("x-user-id"),
    )


@router.post("/exports/bulk")
def export_bulk(payload: BulkExportRequest, request: Request) -> Dict[str, Any]:
    _require_excel(payload.format)
    created_by = request.headers.get("x-user-id")
    if payload.property_ids:
        properties, analyses = store.list_properties_for_export(
            property_ids=list(payload.property_ids),
            limit=max(len(payload.property_ids), 1),
        )
        return _persist_pipeline_export(
            properties=properties,
            analyses=analyses,
            label=f"Selected ({len(properties)})",
            export_type="bulk_selected",
            created_by=created_by,
        )
    scope = payload.scope or "entire"
    deal_status, label = store.resolve_pipeline_scope(scope)
    export_type = f"bulk_{scope.strip().lower()}"
    properties, analyses = store.list_properties_for_export(deal_status=deal_status, limit=500)
    return _persist_pipeline_export(
        properties=properties,
        analyses=analyses,
        label=label,
        export_type=export_type,
        created_by=created_by,
    )


@router.post("/scans/{job_id}/exports")
def export_scan(job_id: str, payload: PipelineExportRequest, request: Request) -> Dict[str, Any]:
    _require_excel(payload.format)
    job = store.get_scan_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    deal_status, label = store.resolve_pipeline_scope(payload.scope)
    scan_label = f"Scan {job_id[:8]} · {label}"
    export_type = f"scan_{(payload.scope or 'entire').strip().lower()}"
    properties, analyses = store.list_properties_for_export(
        deal_status=deal_status, job_id=job_id, limit=500,
    )
    return _persist_pipeline_export(
        properties=properties,
        analyses=analyses,
        label=scan_label,
        export_type=export_type,
        job=job,
        job_id=job_id,
        created_by=request.headers.get("x-user-id"),
    )


@router.get("/exports")
def list_exports_endpoint(
    limit: int = 100,
    property_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    rows = store.list_exports(limit=limit, property_id=property_id, job_id=job_id)
    return {"success": True, "exports": rows}


@router.get("/exports/formats")
def list_export_formats() -> Dict[str, Any]:
    return {"formats": list(exports.EXPORT_FORMATS)}


@router.get("/exports/{export_id}/download")
def download_export(export_id: str) -> FileResponse:
    record = store.get_export(export_id)
    if not record:
        raise HTTPException(status_code=404, detail="export_not_found")
    path = record.get("file_path") or ""
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=410, detail="export_file_unavailable")
    filename = os.path.basename(path)
    return FileResponse(
        path=path,
        filename=filename,
        media_type=exports.MIME_XLSX,
    )
