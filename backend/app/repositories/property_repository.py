"""Properties + analyses."""
from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Analysis, Property


def _active(query):
    """Append a ``deleted_at IS NULL`` filter when the model exposes it.

    The legacy ``Property`` model may pre-date the soft-delete migration, so
    we guard with ``hasattr`` to keep this repo backward compatible.
    """
    if hasattr(Property, "deleted_at"):
        return query.where(Property.deleted_at.is_(None))
    return query


def _active_analysis(query):
    if hasattr(Analysis, "deleted_at"):
        return query.where(Analysis.deleted_at.is_(None))
    return query


async def get_property(
    db: AsyncSession, property_id: UUID, *, include_deleted: bool = False
) -> Optional[Property]:
    q = select(Property).where(Property.id == property_id)
    if not include_deleted:
        q = _active(q)
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def get_latest_analysis(
    db: AsyncSession, property_id: UUID, *, include_deleted: bool = False
) -> Optional[Analysis]:
    q = (
        select(Analysis)
        .where(Analysis.property_id == property_id)
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    if not include_deleted:
        q = _active_analysis(q)
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def get_property_with_analysis(
    db: AsyncSession, property_id: UUID, *, include_deleted: bool = False
) -> Tuple[Optional[Property], Optional[Analysis]]:
    prop = await get_property(db, property_id, include_deleted=include_deleted)
    if not prop:
        return None, None
    analysis = await get_latest_analysis(
        db, property_id, include_deleted=include_deleted
    )
    return prop, analysis


async def list_properties_by_deal_status(
    db: AsyncSession,
    deal_status: str,
    *,
    limit: int = 10,
) -> List[Property]:
    q = select(Property).where(Property.deal_status == deal_status)
    q = _active(q)
    q = q.order_by(Property.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return list(r.scalars())


async def list_properties_multi_status(
    db: AsyncSession,
    statuses: List[str],
    *,
    order_by_score: bool = False,
    limit: int = 10,
) -> List[Property]:
    q = select(Property).where(Property.deal_status.in_(statuses))
    q = _active(q)
    if order_by_score:
        q = q.order_by(Property.score.desc().nulls_last())
    else:
        q = q.order_by(Property.created_at.desc())
    q = q.limit(limit)
    r = await db.execute(q)
    return list(r.scalars())


async def update_analysis_memo(
    db: AsyncSession, analysis: Analysis, memo_text: str
) -> Analysis:
    analysis.ic_memo = memo_text
    return analysis
