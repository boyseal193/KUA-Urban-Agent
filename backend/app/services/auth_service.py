"""Operator authentication — JWT pair, refresh rotation, session persistence."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.user import User
from app.repositories.auth_session_repository import get_session_by_jti, revoke_session
from app.repositories.user_repository import get_user_by_username

log = structlog.get_logger(__name__)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def authenticate(
        self, db: AsyncSession, username: str, password: str
    ) -> User:
        user = await get_user_by_username(db, username)
        if not user or not user.is_active:
            raise UnauthorizedError("Invalid credentials")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid credentials")
        return user

    async def issue_tokens(
        self,
        db: AsyncSession,
        user: User,
        *,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> Tuple[str, str, AuthSession]:
        access = create_access_token(
            self._settings,
            subject=str(user.id),
            extra_claims={"username": user.username, "clr": user.clearance},
        )
        refresh, jti, exp = create_refresh_token(self._settings, subject=str(user.id))

        sess = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            refresh_jti=jti,
            refresh_hash=_hash_refresh_token(refresh),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=exp,
        )
        db.add(sess)
        await db.flush()
        return access, refresh, sess

    async def rotate_refresh(
        self,
        db: AsyncSession,
        raw_refresh: str,
        *,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> Tuple[str, str]:
        try:
            payload = decode_token(self._settings, raw_refresh)
        except Exception:
            raise UnauthorizedError("Invalid refresh token") from None
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")
        jti = payload.get("jti")
        if not jti:
            raise UnauthorizedError("Invalid refresh token")
        row = await get_session_by_jti(db, jti)
        if not row:
            raise UnauthorizedError("Session expired or revoked")
        if _hash_refresh_token(raw_refresh) != row.refresh_hash:
            log.warning("auth.refresh_hash_mismatch", session_id=row.id)
            raise UnauthorizedError("Invalid refresh token")
        if row.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Session expired")

        from app.repositories.user_repository import get_user_by_id
        from uuid import UUID

        user = await get_user_by_id(db, UUID(payload["sub"]))
        if not user or not user.is_active:
            raise UnauthorizedError("Invalid user")

        await revoke_session(db, row)

        access = create_access_token(
            self._settings,
            subject=str(user.id),
            extra_claims={"username": user.username, "clr": user.clearance},
        )
        refresh, new_jti, exp = create_refresh_token(self._settings, subject=str(user.id))
        new_row = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            refresh_jti=new_jti,
            refresh_hash=_hash_refresh_token(refresh),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=exp,
        )
        db.add(new_row)
        await db.flush()
        return access, refresh

    async def logout_refresh(self, db: AsyncSession, raw_refresh: str) -> None:
        try:
            payload = decode_token(self._settings, raw_refresh)
        except Exception:
            return
        if payload.get("type") != "refresh":
            return
        jti = payload.get("jti")
        if not jti:
            return
        row = await get_session_by_jti(db, jti)
        if row and _hash_refresh_token(raw_refresh) == row.refresh_hash:
            await revoke_session(db, row)


def get_auth_service(settings: Settings) -> AuthService:
    return AuthService(settings)
