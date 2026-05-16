"""Properties + analyses."""
from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Analysis, Property


async def get_property(db: AsyncSession, property_id: UUID) -> Optional[Property]:
    r = await db.execute(select(Property).where(Property.id == property_id))
    return r.scalar_one_or_none()


async def get_latest_analysis(
    db: AsyncSession, property_id: UUID
) -> Optional[Analysis]:
    r = await db.execute(
        select(Analysis)
        .where(Analysis.property_id == property_id)
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def get_property_with_analysis(
    db: AsyncSession, property_id: UUID
) -> Tuple[Optional[Property], Optional[Analysis]]:
    prop = await get_property(db, property_id)
    if not prop:
        return None, None
    analysis = await get_latest_analysis(db, property_id)
    return prop, analysis


async def list_properties_by_deal_status(
    db: AsyncSession,
    deal_status: str,
    *,
    limit: int = 10,
) -> List[Property]:
    r = await db.execute(
        select(Property)
        .where(Property.deal_status == deal_status)
        .order_by(Property.created_at.desc())
        .limit(limit)
    )
    return list(r.scalars())


async def list_properties_multi_status(
    db: AsyncSession,
    statuses: List[str],
    *,
    order_by_score: bool = False,
    limit: int = 10,
) -> List[Property]:
    q = select(Property).where(Property.deal_status.in_(statuses))
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
