"""Acquisition notes."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


async def list_notes_for_property(
    db: AsyncSession, property_id: UUID, *, limit: int = 100
) -> List[Note]:
    r = await db.execute(
        select(Note)
        .where(Note.property_id == property_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    return list(r.scalars())


async def create_note(
    db: AsyncSession,
    *,
    property_id: UUID,
    user_id: Optional[UUID],
    body: str,
) -> Note:
    n = Note(property_id=property_id, user_id=user_id, body=body)
    db.add(n)
    await db.flush()
    return n
