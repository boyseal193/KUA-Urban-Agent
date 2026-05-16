"""Deal list endpoints (Supabase-compatible JSON shape)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db.session import get_db
from app.repositories.property_repository import (
    list_properties_by_deal_status,
    list_properties_multi_status,
)

router = APIRouter(tags=["deals"])


@router.get("/deals/top")
async def get_top_deals(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 10,
):
    rows = await list_properties_multi_status(
        db,
        ["approved_candidate", "manual_review"],
        order_by_score=True,
        limit=limit,
    )
    return {"top_deals": [_prop_dict(r) for r in rows]}


@router.get("/deals/manual-review")
async def get_manual_review(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 10,
):
    rows = await list_properties_by_deal_status(db, "manual_review", limit=limit)
    return {"manual_review_deals": [_prop_dict(r) for r in rows]}


@router.get("/deals/approved")
async def get_approved(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 10,
):
    rows = await list_properties_by_deal_status(db, "approved_candidate", limit=limit)
    return {"approved_candidates": [_prop_dict(r) for r in rows]}


@router.get("/deals/status/{deal_status}")
async def get_by_status(
    deal_status: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 10,
):
    rows = await list_properties_by_deal_status(db, deal_status, limit=limit)
    return {"deals": [_prop_dict(r) for r in rows]}


@router.get("/deals/rejected")
async def get_rejected(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = 10,
):
    rows = await list_properties_by_deal_status(db, "rejected", limit=limit)
    return {"rejected_deals": [_prop_dict(r) for r in rows]}


def _prop_dict(r) -> dict:
    """ORM → JSON-serialisable dict (UUID + datetime safe)."""
    from uuid import UUID
    from datetime import datetime

    out = {}
    for c in r.__table__.columns:
        v = getattr(r, c.name)
        if isinstance(v, UUID):
            v = str(v)
        elif isinstance(v, datetime):
            v = v.isoformat()
        out[c.name] = v
    return out
