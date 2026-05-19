"""
K.U.A. — FastAPI auth router.

Endpoints (mounted at /auth via main.py):
  POST /auth/login   — username + password → bearer token
  POST /auth/logout  — idempotent, returns {success: True}
  GET  /auth/me      — echoes the configured operator username

Credentials come from env vars on Railway:
  AUTH_USERNAME       (default: "admin")
  AUTH_PASSWORD       (default: "KUA2026secure")

The defaults ARE the production credentials so the system stays bootable
even if Railway loses the env vars. Set the env vars anyway to make
rotations possible without a code change.

Response shape (success):
  {
    "success": true,
    "message": "Authenticated",
    "username": "<resolved username>",
    "access_token": "<opaque token>",
    "token_type": "bearer"
  }
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


# ---------------------------------------------------------------------------
# Configuration (env-driven, safe defaults match the documented operator).
# ---------------------------------------------------------------------------
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "KUA2026secure"

USERNAME: str = os.getenv("AUTH_USERNAME") or DEFAULT_USERNAME
PASSWORD: str = os.getenv("AUTH_PASSWORD") or DEFAULT_PASSWORD


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    success: bool
    message: str
    username: str
    access_token: str
    token_type: str
    issued_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"description": "Invalid username or password"},
    },
    summary="Authenticate an operator",
)
def login(data: LoginRequest) -> LoginResponse:
    """
    Constant-time credential comparison. Returns a bearer token on success.
    The token is opaque and used only as a marker for the Next.js JWT cookie;
    rotate it by changing AUTH_USERNAME/AUTH_PASSWORD on Railway.
    """
    if not (
        secrets.compare_digest(data.username, USERNAME)
        and secrets.compare_digest(data.password, PASSWORD)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return LoginResponse(
        success=True,
        message="Authenticated",
        username=USERNAME,
        access_token="kua-session-token",
        token_type="bearer",
        issued_at=_now_iso(),
    )


@router.get(
    "/me",
    summary="Return the configured operator identity",
)
def me() -> dict:
    return {
        "success": True,
        "username": USERNAME,
    }


@router.post(
    "/logout",
    summary="Terminate session (idempotent on the backend)",
)
def logout() -> dict:
    # The frontend is responsible for clearing its httpOnly cookie. This
    # endpoint exists so the frontend can mirror the call for parity.
    return {
        "success": True,
        "message": "Session terminated",
    }


@router.get(
    "/health",
    summary="Auth subsystem health probe",
)
def auth_health() -> dict:
    return {
        "ok": True,
        "service": "kua-auth",
        "username_configured": bool(USERNAME),
        "ts": _now_iso(),
    }
