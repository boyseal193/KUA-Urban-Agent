"""Operator auth — login, refresh, logout, /me."""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.limiter import limiter
from app.core.metrics import incr
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenPairResponse, UserPublic
from app.services.auth_service import get_auth_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_AUTH_BRUTE = get_settings().RATE_LIMIT_AUTH


def _cookie_kwargs(settings, max_age: int | None) -> dict:
    same = settings.COOKIE_SAMESITE.lower()
    if same not in ("lax", "strict", "none"):
        same = "lax"
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": same,
        "domain": settings.COOKIE_DOMAIN,
        "path": "/",
        "max_age": max_age,
    }


@router.post("/login", response_model=TokenPairResponse)
@limiter.limit(_AUTH_BRUTE)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPairResponse:
    settings = get_settings()
    auth = get_auth_service(settings)
    try:
        user = await auth.authenticate(db, body.username, body.password)
    except AppError as e:
        incr("auth_failures_total")
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

    access, refresh, _sess = await auth.issue_tokens(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    response.set_cookie(
        settings.COOKIE_ACCESS_NAME,
        access,
        **_cookie_kwargs(settings, settings.JWT_ACCESS_EXPIRE_MINUTES * 60),
    )
    response.set_cookie(
        settings.COOKIE_REFRESH_NAME,
        refresh,
        **_cookie_kwargs(settings, settings.JWT_REFRESH_EXPIRE_DAYS * 86400),
    )

    log.info("auth.login_ok", username=user.username)
    return TokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPairResponse:
    settings = get_settings()
    raw = request.cookies.get(settings.COOKIE_REFRESH_NAME)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh")
    auth = get_auth_service(settings)
    try:
        access, refresh = await auth.rotate_refresh(
            db,
            raw,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

    response.set_cookie(
        settings.COOKIE_ACCESS_NAME,
        access,
        **_cookie_kwargs(settings, settings.JWT_ACCESS_EXPIRE_MINUTES * 60),
    )
    response.set_cookie(
        settings.COOKIE_REFRESH_NAME,
        refresh,
        **_cookie_kwargs(settings, settings.JWT_REFRESH_EXPIRE_DAYS * 86400),
    )
    return TokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    settings = get_settings()
    raw = request.cookies.get(settings.COOKIE_REFRESH_NAME)
    if raw:
        await get_auth_service(settings).logout_refresh(db, raw)
    response.delete_cookie(
        settings.COOKIE_ACCESS_NAME, path="/", domain=settings.COOKIE_DOMAIN
    )
    response.delete_cookie(
        settings.COOKIE_REFRESH_NAME, path="/", domain=settings.COOKIE_DOMAIN
    )


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)
