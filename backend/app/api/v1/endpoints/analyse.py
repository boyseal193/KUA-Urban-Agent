"""Single-property extraction + underwriting (legacy `/analyse`)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db.session import get_db
from app.schemas.property import AnalysePayload
from app.services.pipeline_service import pipeline_service

router = APIRouter(tags=["analyse"])


@router.post("/analyse")
async def analyse(
    body: AnalysePayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
):
    if not body.url and not (body.text or body.raw_text):
        return {"success": False, "error": "Provide either url or text/raw_text"}

    if body.url:
        return await pipeline_service.analyse_url(db, body.url)

    return await pipeline_service.analyse_text(db, body.text or body.raw_text or "")
