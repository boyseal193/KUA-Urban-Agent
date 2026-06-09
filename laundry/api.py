"""K.U.A. laundry vertical FastAPI router.

Endpoints (prefix ``/laundry``):

* ``GET    /laundry/health``
* ``POST   /laundry/scans``            — launch async or inline scan
* ``GET    /laundry/scans/{id}``       — job status snapshot
* ``GET    /laundry/jobs``             — list laundry jobs
* ``GET    /laundry/jobs/{id}``        — job detail (alias of scans/{id})
* ``DELETE /laundry/jobs/{id}``        — cancel a job
* ``POST   /laundry/analyse``          — synchronous one-shot underwriting
* ``GET    /laundry/properties``       — list scored properties
* ``GET    /laundry/properties/{id}``  — property + latest memo
* ``DELETE /laundry/properties/{id}``  — soft delete
* ``POST   /laundry/properties/{id}/restore``
* ``GET    /laundry/deals/top``
* ``GET    /laundry/deals/manual-review``
* ``GET    /laundry/deals/approved``
* ``GET    /laundry/deals/rejected``
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from laundry import pipeline, store, url_builder

log = logging.getLogger("kua.laundry.api")

router = APIRouter(prefix="/laundry", tags=["laundry"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ScanPayload(BaseModel):
    property_type: Optional[str] = Field(default=None, description="existing_laundromat | empty_commercial | retail | mixed_use")
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
        """Slice the scan payload into the shape expected by laundry.url_builder."""
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

    class Config:
        extra = "ignore"


@router.get("/search-providers")
def list_search_providers() -> Dict[str, Any]:
    return {"success": True, "providers": url_builder.list_providers()}


@router.post("/search-url")
def generate_search_url(payload: SearchUrlPayload) -> Dict[str, Any]:
    """Build a provider search URL from the operator's filters.

    Returns 400 with a helpful `detail` if the filter combination cannot be
    translated into a URL for the chosen provider.
    """
    try:
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
    return {
        "success": True,
        "service": "kua-laundry",
        "version": "2.0.0",
        "supabase": "configured" if sb_ok else "missing",
    }


# ---------------------------------------------------------------------------
# Scans / jobs
# ---------------------------------------------------------------------------
@router.post("/scans", status_code=202)
def launch_scan(payload: ScanPayload, request: Request) -> JSONResponse:
    url = payload.resolved_url()
    text = payload.resolved_text()

    auto_generated: Optional[Dict[str, Any]] = None
    needs_url = (payload.search_type in ("automatic_scan", "area_search", None)) or bool(text is None)
    if not url and not text and needs_url and payload.auto_generate_url:
        try:
            built = url_builder.build_search_url(
                payload.to_url_builder_payload(), provider=payload.search_provider,
            )
            url = built.url
            auto_generated = built.to_dict()
            log.info("Auto-generated search URL via %s: %s", built.provider, url)
        except url_builder.UnsupportedFilterError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to generate search URL from selected filters. {exc}",
            )

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
                content={"success": True, "async": False, "status": "completed", "result": result},
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
        "search_type": payload.search_type or ("area_search" if filters.get("search_type") == "area_search" else None),
        "auto_generated_url": auto_generated,
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
        "message": "Laundry scan queued. Poll GET /laundry/jobs/{job_id}.",
        "poll_url": f"/laundry/jobs/{job['id']}",
        "search_url": url,
    }
    if auto_generated:
        response["auto_generated_url"] = auto_generated
    return JSONResponse(status_code=202, content=response)


@router.post("/scan", include_in_schema=False)
def launch_scan_legacy(payload: ScanPayload, request: Request) -> JSONResponse:
    """Backward-compat alias — frontend builds older than v2 may call /laundry/scan."""
    return launch_scan(payload, request)


@router.get("/scans")
def list_scans(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    """List laundry scan jobs (alias of /laundry/jobs, matches existing frontend client)."""
    scans = store.list_laundry_jobs(limit=limit, status=status)
    return {"success": True, "scans": scans, "jobs": scans}


@router.get("/scans/{job_id}")
def get_scan(job_id: str) -> Dict[str, Any]:
    job = store.get_scan_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job_not_found")
    return {"success": True, "job": job, "steps": [], "properties": job.get("properties", [])}


@router.post("/scans/{job_id}/resume")
def resume_scan(job_id: str) -> Dict[str, Any]:
    """Re-queue a finished/failed laundry scan."""
    job = store.get_scan_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="job_not_found")
    try:
        from jobs.constants import JOB_QUEUED
    except Exception:
        JOB_QUEUED = "queued"
    store.update_job_progress(job_id, status=JOB_QUEUED, error_message=None,
                                started_at=None, finished_at=None, progress_pct=0)
    return {"success": True, "job_id": job_id, "status": JOB_QUEUED}


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
    if not prop: raise HTTPException(status_code=404, detail="property_not_found")
    return {"success": True, "property": prop}


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
    return {"deals": store.list_properties(limit=limit)}


@router.get("/deals/manual-review")
def deals_manual(limit: int = 50) -> Dict[str, Any]:
    return {"deals": store.list_properties(deal_status="manual_review", limit=limit)}


@router.get("/deals/approved")
def deals_approved(limit: int = 50) -> Dict[str, Any]:
    return {"deals": store.list_properties(deal_status="approved_candidate", limit=limit)}


@router.get("/deals/rejected")
def deals_rejected(limit: int = 50) -> Dict[str, Any]:
    return {"deals": store.list_properties(deal_status="rejected", limit=limit)}


# ---------------------------------------------------------------------------
# Settings inspection
# ---------------------------------------------------------------------------
@router.get("/settings/assumptions")
def get_assumptions() -> Dict[str, Any]:
    from laundry.assumptions import default_assumptions
    return {"success": True, "assumptions": default_assumptions().to_dict()}
