"""User persistence."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    r = await db.execute(select(User).where(User.username == username))
    return r.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    r = await db.execute(select(User).where(User.id == user_id))
    return r.scalar_one_or_none()


async def upsert_operator_template(
    db: AsyncSession,
    *,
    username: str,
    password_hash: str,
    display_name: str,
    clearance: str,
) -> User:
    u = await get_user_by_username(db, username)
    if u:
        u.password_hash = password_hash
        u.display_name = display_name
        u.clearance = clearance
        u.is_active = True
        return u
    u = User(
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        clearance=clearance,
    )
    db.add(u)
    await db.flush()
    return u
