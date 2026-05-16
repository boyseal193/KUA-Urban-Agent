"""Idealista batch scans + auto-filter presets (legacy paths)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.metrics import incr
from app.db.session import get_db
from app.repositories.scan_repository import create_scan, get_scan
from app.schemas.scan import (
    ScanIdealistaAutoPayload,
    ScanIdealistaPayload,
    ScanJobStarted,
    ScanStatusOut,
)
from app.services.scan_service import run_idealista_scan_sync
from app.workers.settings import WorkerSettings
from app.workers.tasks import run_idealista_scan_job

router = APIRouter(tags=["scan"])


async def _execute_scan(
    payload: ScanIdealistaPayload,
    db: AsyncSession,
    user: CurrentUser,
):
    if payload.async_mode:
        scan = await create_scan(
            db,
            search_url=payload.search_url,
            filters=payload.filters_used or {},
            created_by_user_id=user.id,
        )
        await db.commit()
        pool = await create_pool(WorkerSettings.redis_settings)
        try:
            await pool.enqueue_job(
                run_idealista_scan_job,
                str(scan.id),
                payload.search_url,
                payload.limit,
                payload.generate_excel,
                payload.filters_used or {},
            )
        finally:
            await pool.close()
        incr("scans_started_total")
        return ScanJobStarted(scan_id=scan.id, websocket_url=f"/ws/live/{scan.id}")

    return await run_idealista_scan_sync(
        db,
        search_url=payload.search_url,
        limit=payload.limit,
        generate_excel=payload.generate_excel,
        filters_used=payload.filters_used or {},
        user_id=user.id,
        ws_manager=None,
        redis_client=None,
        scan_id=None,
    )


@router.post("/scan/idealista")
async def scan_idealista(
    payload: ScanIdealistaPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    """
    Scrape an Idealista search results page and analyse each listing.

    Set ``async_mode`` to enqueue an ARQ job and stream progress over
    ``/ws/live/{scan_id}`` (use ``NEXT_PUBLIC_WS_URL`` on the frontend).
    """
    return await _execute_scan(payload, db, user)


@router.post("/scan/idealista/auto")
async def scan_idealista_auto(
    payload: ScanIdealistaAutoPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    filter_parts = [
        f"con-precio-hasta_{payload.max_price}",
        f"metros-cuadrados-mas-de_{payload.min_m2}",
        f"metros-cuadrados-menos-de_{payload.max_m2}",
    ]
    filter_parts.extend(payload.property_types)
    if payload.ground_floor_only:
        filter_parts.append("en-planta-calle")
    if payload.sale_only:
        filter_parts.append("venta-solo-inmueble")
    filters_string = ",".join(filter_parts)
    search_url = (
        f"https://www.idealista.com/en/venta-locales/"
        f"{payload.city_slug}/{filters_string}/"
    )
    filters_used = {
        "city_slug": payload.city_slug,
        "max_price": payload.max_price,
        "min_m2": payload.min_m2,
        "max_m2": payload.max_m2,
        "property_types": payload.property_types,
        "ground_floor_only": payload.ground_floor_only,
        "sale_only": payload.sale_only,
        "limit": payload.limit,
    }
    inner = ScanIdealistaPayload(
        search_url=search_url,
        limit=payload.limit,
        generate_excel=payload.generate_excel,
        filters_used=filters_used,
        async_mode=payload.async_mode,
    )
    return await _execute_scan(inner, db, user)


@router.get("/scan/{scan_id}/status")
async def scan_status(
    scan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    row = await get_scan(db, scan_id)
    if not row:
        return {"success": False, "error": "scan not found"}
    return {"success": True, "scan": ScanStatusOut.model_validate(row)}
