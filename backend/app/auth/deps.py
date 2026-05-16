"""Reusable auth dependencies (JWT from Authorization header or HTTP-only cookie)."""
from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import safe_decode
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import get_user_by_id

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> User:
    settings = get_settings()
    token: Optional[str] = creds.credentials if creds else None
    if not token:
        token = request.cookies.get(settings.COOKIE_ACCESS_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    payload = safe_decode(settings, token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    try:
        uid = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        )
    user = await get_user_by_id(db, uid)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or missing"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
