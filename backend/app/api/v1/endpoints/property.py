"""Property detail + memo regeneration."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memo_service import memo_service
from app.auth.deps import CurrentUser
from app.core.metrics import incr
from app.db.session import get_db
from app.repositories.property_repository import (
    get_property_with_analysis,
    update_analysis_memo,
)
from app.schemas.property import (
    AnalysePayload,
    PropertyDetailResponse,
    PropertyOut,
    AnalysisOut,
)

router = APIRouter(tags=["property"])


@router.post("/property/from-url")
async def from_url(
    payload: AnalysePayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    from app.services.pipeline_service import pipeline_service

    if not payload.url:
        return {"success": False, "error": "url required"}
    return await pipeline_service.analyse_url(db, payload.url)


@router.post("/property/extract")
async def from_text(
    payload: AnalysePayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    from app.services.pipeline_service import pipeline_service

    raw = payload.text or payload.raw_text
    if not raw:
        return {"success": False, "error": "text/raw_text required"}
    return await pipeline_service.analyse_text(db, raw)


@router.get("/property/{property_id}", response_model=PropertyDetailResponse)
async def property_detail(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    latest = AnalysisOut.model_validate(analysis) if analysis else None
    return PropertyDetailResponse(
        property=PropertyOut.model_validate(prop),
        latest_analysis=latest,
    )


@router.post("/property/memo/{property_id}")
async def regenerate_memo(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    prop, analysis = await get_property_with_analysis(db, property_id)
    if not prop:
        return {"error": "Property not found"}
    if not analysis:
        return {"error": "No analysis found for this property"}

    pd = {c.name: getattr(prop, c.name) for c in prop.__table__.columns}
    pd["id"] = str(prop.id)
    memo_text = await memo_service.generate_ic_memo(
        property_data=pd,
        economics=dict(analysis.economics or {}),
        score=dict(analysis.score or {}),
    )
    await update_analysis_memo(db, analysis, memo_text)
    incr("ai_memo_generations_total")
    return {"property_id": str(property_id), "ic_memo": memo_text}
