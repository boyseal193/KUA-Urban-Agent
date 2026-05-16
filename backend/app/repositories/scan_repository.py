"""Scan + history rows."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scan import Scan, ScanHistory


async def create_scan(
    db: AsyncSession,
    *,
    search_url: str,
    filters: Dict[str, Any],
    created_by_user_id: Optional[UUID] = None,
) -> Scan:
    s = Scan(
        search_url=search_url,
        filters=filters,
        status="pending",
        scanned_count=0,
        created_by_user_id=created_by_user_id,
    )
    db.add(s)
    await db.flush()
    return s


async def get_scan(db: AsyncSession, scan_id: UUID) -> Optional[Scan]:
    r = await db.execute(select(Scan).where(Scan.id == scan_id))
    return r.scalar_one_or_none()


async def load_scan_with_items(db: AsyncSession, scan_id: UUID) -> Optional[Scan]:
    r = await db.execute(
        select(Scan)
        .options(selectinload(Scan.items))
        .where(Scan.id == scan_id)
    )
    return r.scalar_one_or_none()


async def add_scan_history_item(
    db: AsyncSession,
    *,
    scan_id: UUID,
    url: str,
    order_index: int,
    status: str,
    payload: Dict[str, Any],
) -> ScanHistory:
    h = ScanHistory(
        scan_id=scan_id,
        url=url,
        order_index=order_index,
        status=status,
        payload=payload,
    )
    db.add(h)
    await db.flush()
    return h
