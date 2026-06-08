"""FastAPI router for the laundry vertical — every route is under ``/laundry``."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

import structlog
from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.metrics import incr
from app.db.session import get_db
from app.laundry.ai.due_diligence import build_due_diligence
from app.laundry.ai.memo import generate_ic_memo
from app.laundry.assumptions import default_assumptions, merge_overrides
from app.laundry.economics import calculate_economics
from app.laundry.exports.builders import EXPORT_FORMATS, build_export
from app.laundry.api.schemas import (
    AnalyseInlinePayload,
    AnalysisOut,
    BulkRescoreRequest,
    ExportRequest,
    PropertyDetailResponse,
    PropertyOut,
    ScanJobOut,
    ScanLaunchPayload,
    SettingsPayload,
)
from app.laundry.models import LaundryAnalysis, LaundryProperty
from app.laundry.repository import (
    add_export,
    audit,
    create_scan_job,
    duplicate_clusters,
    get_property,
    get_property_with_analysis,
    get_scan_job,
    get_settings as get_laundry_settings,
    kpi_counters,
    list_deleted_properties,
    list_exports,
    list_properties,
    list_scan_jobs,
    list_scan_steps,
    purge_test_data,
    restore_property,
    save_memo,
    soft_delete_property,
    upsert_settings,
)
from app.laundry.scoring import score_property
from app.laundry.services.location_service import gather_location_intel
from app.laundry.services.pipeline import pipeline_service
from app.workers.settings import WorkerSettings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/laundry", tags=["laundry"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialise(obj) -> Dict[str, Any]:
    """ORM → JSON-safe dict (handles UUID, datetime, decimal)."""
    from datetime import datetime as _dt
    from uuid import UUID as _UUID

    out: Dict[str, Any] = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, _UUID):
            v = str(v)
        elif isinstance(v, _dt):
            v = v.isoformat()
        out[c.name] = v
    return out


# ---------------------------------------------------------------------------
# Dashboard / pipeline / KPIs
# ---------------------------------------------------------------------------


@router.get("/kpis")
async def laundry_kpis(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
) -> Dict[str, Any]:
    counters = await kpi_counters(db)
    return {"success": True, "kpis": counters}


@router.get("/deals/top")
async def top_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 25,
):
    rows = await list_properties(
        db,
        deal_statuses=["approved_candidate", "manual_review"],
        order_by_score=True,
        limit=limit,
    )
    return {"top_deals": [_serialise(r) for r in rows]}


@router.get("/deals/approved")
async def approved_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 50,
):
    rows = await list_properties(db, deal_status="approved_candidate", limit=limit)
    return {"approved_candidates": [_serialise(r) for r in rows]}


@router.get("/deals/manual-review")
async def manual_review_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 50,
):
    rows = await list_properties(db, deal_status="manual_review", limit=limit)
    return {"manual_review_deals": [_serialise(r) for r in rows]}


@router.get("/deals/rejected")
async def rejected_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 50,
):
    rows = await list_properties(db, deal_status="rejected", limit=limit)
    return {"rejected_deals": [_serialise(r) for r in rows]}


@router.get("/deals/all")
async def all_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 100,
    offset: int = 0,
):
    rows = await list_properties(db, limit=limit, offset=offset)
    return {"deals": [_serialise(r) for r in rows]}


@router.get("/map/markers")
async def map_markers(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 500,
):
    rows = await list_properties(db, limit=limit)
    return {
        "markers": [
            {
                "id": str(r.id),
                "lat": r.latitude,
                "lng": r.longitude,
                "score": r.score,
                "deal_status": r.deal_status,
                "address": r.address,
                "city": r.city,
                "verdict": r.verdict,
            }
            for r in rows
            if r.latitude is not None and r.longitude is not None
        ]
    }


# ---------------------------------------------------------------------------
# Property detail / memo
# ---------------------------------------------------------------------------


@router.get("/properties/{property_id}", response_model=PropertyDetailResponse)
async def property_detail(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyDetailResponse(
        property=PropertyOut.model_validate(prop),
        latest_analysis=AnalysisOut.model_validate(analysis) if analysis else None,
    )


@router.delete("/properties/{property_id}")
async def delete_property(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    reason: Optional[str] = None,
):
    prop = await soft_delete_property(db, property_id, reason=reason)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    await audit(
        db,
        actor_user_id=user.id,
        action="delete",
        entity_type="laundry_property",
        entity_id=str(property_id),
        payload={"reason": reason},
    )
    return {"success": True, "property": _serialise(prop), "already_deleted": prop.deleted_at is not None}


@router.post("/properties/{property_id}/restore")
async def restore_property_endpoint(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    prop = await restore_property(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    await audit(
        db,
        actor_user_id=user.id,
        action="restore",
        entity_type="laundry_property",
        entity_id=str(property_id),
        payload={},
    )
    return {"success": True, "property": _serialise(prop)}


@router.get("/properties/deleted")
async def list_deleted(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 100,
):
    rows = await list_deleted_properties(db, limit=limit)
    return {"success": True, "properties": [_serialise(r) for r in rows]}


@router.get("/properties/duplicates")
async def get_duplicates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 50,
):
    clusters = await duplicate_clusters(db, limit=limit)
    return {"success": True, "clusters": clusters, "count": len(clusters)}


@router.post("/properties/{property_id}/memo")
async def regenerate_memo(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop or not analysis:
        raise HTTPException(status_code=404, detail="Property/analysis not found")

    due_diligence = build_due_diligence(
        property_data=_serialise(prop),
        economics=dict(analysis.economics or {}),
        score_result=dict(analysis.score or {}),
        location=dict(analysis.location or {}),
    )
    memo_md = generate_ic_memo(
        property_data=_serialise(prop),
        economics=dict(analysis.economics or {}),
        score=dict(analysis.score or {}),
        due_diligence=due_diligence,
    )
    analysis.ic_memo = memo_md
    analysis.due_diligence = due_diligence
    await db.flush()
    await save_memo(db, property_id=property_id, analysis_id=analysis.id, markdown=memo_md)
    await audit(
        db,
        actor_user_id=user.id,
        action="rebuild_memo",
        entity_type="laundry_analysis",
        entity_id=str(analysis.id),
        payload={},
    )
    incr("laundry_memos_regenerated_total")
    return {"success": True, "property_id": str(property_id), "ic_memo": memo_md}


@router.post("/properties/{property_id}/rescore")
async def rescore_property(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop or not analysis:
        raise HTTPException(status_code=404, detail="Property/analysis not found")

    economics = calculate_economics(dict(analysis.input or {}), overrides=dict(analysis.assumptions_used or {}))
    score = score_property(
        {"extracted": dict(analysis.input or {}), "location": dict(analysis.location or {}), "economics": economics},
        overrides=dict(analysis.assumptions_used or {}),
    )
    prop.score = score.get("score")
    prop.verdict = score.get("verdict")
    prop.classification = score.get("classification")
    prop.deal_status = score.get("deal_status", prop.deal_status)
    analysis.economics = economics
    analysis.score = score
    analysis.verdict = score.get("verdict")
    analysis.classification = score.get("classification")
    await db.flush()
    await audit(
        db,
        actor_user_id=user.id,
        action="rescore",
        entity_type="laundry_property",
        entity_id=str(property_id),
        payload={"new_score": score.get("score")},
    )
    return {"success": True, "property_id": str(property_id), "score": score, "economics": economics}


# ---------------------------------------------------------------------------
# Inline analyse (URL / text) — synchronous mini path
# ---------------------------------------------------------------------------


@router.post("/analyse")
async def analyse_inline(
    payload: AnalyseInlinePayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    filters = dict(getattr(payload, "filters", None) or {})
    if payload.url:
        result = await pipeline_service.analyse_url(
            db,
            payload.url,
            overrides=payload.overrides,
            filters=filters,
            user_id=user.id,
            polish_with_llm=payload.polish_with_llm,
        )
    elif payload.text:
        result = await pipeline_service.analyse_text(
            db,
            payload.text,
            overrides=payload.overrides,
            filters=filters,
            user_id=user.id,
        )
    else:
        raise HTTPException(status_code=400, detail="Provide url or text")
    incr("laundry_inline_analyse_total")
    return result


# ---------------------------------------------------------------------------
# Scan jobs
# ---------------------------------------------------------------------------


@router.post("/scans")
async def launch_scan(
    payload: ScanLaunchPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    if payload.search_type == "manual_url" and not payload.listing_url:
        raise HTTPException(status_code=400, detail="manual_url scans require listing_url")
    if payload.search_type == "area_search" and not payload.listing_url:
        raise HTTPException(status_code=400, detail="area_search scans require listing_url")
    if (
        payload.search_type == "automatic_scan"
        and not payload.listing_url
        and not (payload.overrides.get("seed_urls") or payload.filters.get("seed_urls"))
    ):
        raise HTTPException(
            status_code=400,
            detail="automatic_scan needs a seed listing_url or overrides.seed_urls list",
        )

    job = await create_scan_job(
        db,
        user_id=user.id,
        search_type=payload.search_type,
        property_type=payload.property_type,
        acquisition_type=payload.acquisition_type,
        search_url=payload.listing_url,
        seed_text=payload.raw_listing_text,
        filters=payload.filters,
        overrides=payload.overrides,
        listing_limit=payload.listing_limit,
        job_type="laundry_scan",
    )
    await db.commit()

    if payload.run_in_background:
        pool = await create_pool(WorkerSettings.redis_settings)
        try:
            await pool.enqueue_job(
                "run_laundry_scan_job",
                str(job.id),
                payload.overrides,
            )
        finally:
            await pool.close()
        incr("laundry_scans_started_total")
        log.info(
            "laundry.scan_queued",
            job_id=str(job.id),
            search_type=payload.search_type,
            property_type=payload.property_type,
            acquisition_type=payload.acquisition_type,
            listing_limit=payload.listing_limit,
            neighbourhood_filters=payload.neighbourhood_filters,
            max_size_sqm=payload.max_size_sqm,
        )
        return {
            "success": True,
            "async": True,
            "job_id": str(job.id),
            "status": "queued",
            "websocket_url": f"/ws/laundry/{job.id}",
        }

    # Inline execution (small jobs only)
    from app.laundry.services.scan_service import run_laundry_scan

    out = await run_laundry_scan(db, job_id=job.id, overrides=payload.overrides)
    incr("laundry_scans_started_total")
    return {
        "success": True,
        "async": False,
        "job_id": str(job.id),
        "status": "completed" if out.get("success") else "failed",
        "result": out,
    }


# Back-compat alias for the original singular path. Deployed UIs that were
# pinned to ``/laundry/scan`` keep working without any redirect cost.
@router.post("/scan", include_in_schema=False)
async def launch_scan_legacy(
    payload: ScanLaunchPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    return await launch_scan(payload, db, user)


@router.get("/scans")
async def list_scans(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 50,
):
    rows = await list_scan_jobs(db, limit=limit)
    return {
        "scans": [
            ScanJobOut.model_validate(r).model_dump(mode="json") for r in rows
        ]
    }


@router.get("/scans/{job_id}")
async def get_scan(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    job = await get_scan_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")
    steps = await list_scan_steps(db, job_id)
    return {
        "success": True,
        "job": ScanJobOut.model_validate(job).model_dump(mode="json"),
        "steps": [
            {
                "id": str(s.id),
                "step_key": s.step_key,
                "status": s.status,
                "step_order": s.step_order,
                "listing_index": s.listing_index,
                "listing_url": s.listing_url,
                "error_type": s.error_type,
                "error_message": s.error_message,
                "duration_ms": s.duration_ms,
                "payload": s.payload,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in steps
        ],
    }


@router.post("/scans/{job_id}/resume")
async def resume_scan(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    """Re-queue a failed / cancelled scan job."""
    job = await get_scan_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")
    job.status = "pending"
    job.error_message = None
    await db.commit()
    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        await pool.enqueue_job("run_laundry_scan_job", str(job.id), job.overrides or {})
    finally:
        await pool.close()
    return {"success": True, "job_id": str(job.id), "status": "queued"}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@router.post("/properties/{property_id}/exports")
async def create_property_export(
    property_id: UUID,
    payload: ExportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop or not analysis:
        raise HTTPException(status_code=404, detail="Property/analysis not found")
    meta = build_export(
        fmt=payload.format,
        prop=_serialise(prop),
        analysis={
            "input": analysis.input,
            "location": analysis.location,
            "economics": analysis.economics,
            "score": analysis.score,
            "due_diligence": analysis.due_diligence,
            "assumptions_used": analysis.assumptions_used,
            "ic_memo": analysis.ic_memo,
        },
    )
    record = await add_export(
        db,
        fmt=meta["format"],
        file_path=meta["file_path"],
        size_bytes=meta["size_bytes"],
        user_id=user.id,
        property_id=property_id,
    )
    await audit(
        db,
        actor_user_id=user.id,
        action="export",
        entity_type="laundry_property",
        entity_id=str(property_id),
        payload={"format": payload.format, "file": meta["filename"]},
    )
    return {
        "success": True,
        "export_id": str(record.id),
        **meta,
        "download_url": f"/laundry/exports/{record.id}/download",
    }


@router.get("/exports")
async def list_exports_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 100,
):
    rows = await list_exports(db, limit=limit)
    return {
        "success": True,
        "exports": [
            {
                "id": str(r.id),
                "format": r.format,
                "file_path": r.file_path,
                "size_bytes": r.size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "property_id": str(r.property_id) if r.property_id else None,
                "job_id": str(r.job_id) if r.job_id else None,
                "download_url": f"/laundry/exports/{r.id}/download",
            }
            for r in rows
        ],
    }


@router.get("/exports/formats")
async def list_export_formats(_user: CurrentUser):
    return {"formats": list(EXPORT_FORMATS)}


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    from sqlalchemy import select
    from app.laundry.models import LaundryExport

    r = await db.execute(select(LaundryExport).where(LaundryExport.id == export_id))
    record = r.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")
    if not os.path.exists(record.file_path):
        raise HTTPException(status_code=410, detail="Export file no longer available on disk")
    return FileResponse(
        path=record.file_path,
        filename=os.path.basename(record.file_path),
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@router.get("/admin/stats")
async def admin_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    counters = await kpi_counters(db)
    return {"success": True, "stats": counters}


@router.post("/admin/cleanup/test-data")
async def purge_test_data_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    n = await purge_test_data(db)
    await audit(
        db,
        actor_user_id=user.id,
        action="purge_test_data",
        entity_type="laundry_property",
        entity_id=None,
        payload={"deleted": n},
    )
    return {"success": True, "deleted": n}


@router.post("/admin/bulk-rescore")
async def bulk_rescore(
    payload: BulkRescoreRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    rows = await list_properties(db, deal_statuses=payload.deal_statuses, limit=payload.limit)
    rescored: List[str] = []
    for prop in rows:
        prop_id = prop.id
        prop, analysis = await get_property_with_analysis(db, prop_id)
        if not analysis:
            continue
        economics = calculate_economics(dict(analysis.input or {}), overrides=dict(analysis.assumptions_used or {}))
        score = score_property(
            {
                "extracted": dict(analysis.input or {}),
                "location": dict(analysis.location or {}),
                "economics": economics,
            },
            overrides=dict(analysis.assumptions_used or {}),
        )
        prop.score = score.get("score")
        prop.verdict = score.get("verdict")
        prop.classification = score.get("classification")
        prop.deal_status = score.get("deal_status", prop.deal_status)
        analysis.economics = economics
        analysis.score = score
        analysis.verdict = score.get("verdict")
        analysis.classification = score.get("classification")
        rescored.append(str(prop_id))
    await db.flush()
    await audit(
        db,
        actor_user_id=user.id,
        action="bulk_rescore",
        entity_type="laundry_property",
        entity_id=None,
        payload={"count": len(rescored)},
    )
    return {"success": True, "rescored": rescored, "count": len(rescored)}


# ---------------------------------------------------------------------------
# Settings (assumption overrides)
# ---------------------------------------------------------------------------


@router.get("/settings")
async def read_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    record = await get_laundry_settings(db)
    return {
        "success": True,
        "defaults": default_assumptions().to_dict(),
        "overrides": record.overrides if record else {},
        "notes": record.notes if record else None,
        "effective": merge_overrides(default_assumptions(), record.overrides if record else None).to_dict(),
    }


@router.put("/settings")
async def update_settings(
    payload: SettingsPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    record = await upsert_settings(db, overrides=payload.overrides, notes=payload.notes)
    await audit(
        db,
        actor_user_id=user.id,
        action="settings_update",
        entity_type="laundry_settings",
        entity_id=str(record.id),
        payload={"overrides_keys": list(payload.overrides.keys())},
    )
    return {
        "success": True,
        "overrides": record.overrides,
        "notes": record.notes,
        "effective": merge_overrides(default_assumptions(), record.overrides).to_dict(),
    }


# ---------------------------------------------------------------------------
# Lightweight location lookup (used by the manual analyse UI)
# ---------------------------------------------------------------------------


@router.get("/location/preview")
async def preview_location(
    _user: CurrentUser,
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    neighbourhood: Optional[str] = None,
    city: Optional[str] = None,
):
    intel = await gather_location_intel(lat=lat, lng=lng, neighbourhood=neighbourhood, city=city)
    return {"success": True, "location": intel, "ts": datetime.now(timezone.utc).isoformat()}
