"""Server-side refresh sessions (revocation + rotation)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession


async def get_session_by_jti(db: AsyncSession, jti: str) -> Optional[AuthSession]:
    r = await db.execute(
        select(AuthSession).where(
            AuthSession.refresh_jti == jti,
            AuthSession.revoked_at.is_(None),
        )
    )
    return r.scalar_one_or_none()


async def revoke_session(db: AsyncSession, row: AuthSession) -> None:
    row.revoked_at = datetime.now(timezone.utc)


async def delete_user_sessions(db: AsyncSession, user_id: str) -> None:
    """Bulk revoke — used on password reset flows (optional)."""
    from uuid import UUID

    r = await db.execute(
        select(AuthSession).where(AuthSession.user_id == UUID(str(user_id)))
    )
    for s in r.scalars():
        await revoke_session(db, s)
