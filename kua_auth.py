"""
K.U.A. — Optional FastAPI auth router.

This is the production-grade backend auth path the Next.js frontend can
proxy through. It is OPTIONAL: by default the Next.js side validates
credentials against env-configured operator accounts. When you want a
real user store (Supabase, Postgres, etc.), enable this module by:

  1.  pip install passlib[bcrypt] python-jose[cryptography]
  2.  Add the operators table to your DB (see SQL block at the bottom).
  3.  Wire the router in main.py:

        from kua_auth import router as auth_router
        app.include_router(auth_router)

  4.  Set the Next.js frontend env var:

        BACKEND_AUTH_URL=https://api.your-domain.com/auth/login

Once configured, the Next.js login flow will delegate to this endpoint
instead of the local operator credentials.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel

from database import supabase


router = APIRouter(prefix="/auth", tags=["auth"])


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
AUTH_SECRET = os.environ.get("AUTH_SECRET", "dev-only-insecure-change-me")
ACCESS_TTL_SECONDS = int(os.environ.get("AUTH_ACCESS_TTL_SECONDS", 43_200))


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str
    displayName: str
    clearance: str
    accessToken: str
    expiresAt: int


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _verify_password(plaintext: str, bcrypt_hash: str) -> bool:
    try:
        from passlib.hash import bcrypt
        return bcrypt.verify(plaintext, bcrypt_hash)
    except Exception:
        return False


def _sign_jwt(sub: str, name: str, clearance: str) -> tuple[str, int]:
    try:
        from jose import jwt
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="python-jose not installed. `pip install 'python-jose[cryptography]'`",
        ) from e

    exp = datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TTL_SECONDS)
    payload = {
        "sub": sub,
        "name": name,
        "clr": clearance,
        "iss": "kua.api",
        "aud": "kua.operators",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, AUTH_SECRET, algorithm="HS256")
    return token, int(exp.timestamp())


def _decode_jwt(token: str) -> dict:
    from jose import jwt, JWTError
    try:
        return jwt.decode(
            token,
            AUTH_SECRET,
            algorithms=["HS256"],
            audience="kua.operators",
            issuer="kua.api",
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail=str(e))


def current_operator(authorization: Optional[str] = Header(default=None)) -> dict:
    """Inject this as a dependency on any protected route."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return _decode_jwt(token)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Validate operator credentials and return a signed JWT."""
    rows = (
        supabase.table("operators")
        .select("*")
        .eq("username", req.username)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    op = rows[0]
    if not _verify_password(req.password, op["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, exp = _sign_jwt(
        sub=op["username"],
        name=op.get("display_name") or op["username"],
        clearance=op.get("clearance") or "tier-1",
    )

    return LoginResponse(
        username=op["username"],
        displayName=op.get("display_name") or op["username"],
        clearance=op.get("clearance") or "tier-1",
        accessToken=token,
        expiresAt=exp,
    )


@router.get("/me")
def me(op: dict = Depends(current_operator)):
    """Return the currently authenticated operator."""
    return {
        "username": op.get("sub"),
        "displayName": op.get("name"),
        "clearance": op.get("clr"),
        "expiresAt": op.get("exp"),
    }


# -----------------------------------------------------------------------------
# Supabase / Postgres bootstrap (run once)
# -----------------------------------------------------------------------------
"""
-- Operators table
create table if not exists operators (
    id              uuid primary key default gen_random_uuid(),
    username        text unique not null,
    password_hash   text not null,
    display_name    text,
    clearance       text default 'tier-1',
    created_at      timestamptz default now()
);

-- Seed a first operator (hash a password with passlib first):
--   python -c "from passlib.hash import bcrypt; print(bcrypt.hash('YourStrongPass'))"
insert into operators (username, password_hash, display_name, clearance)
values ('operator', '<bcrypt-hash-here>', 'Acquisitions Operator', 'tier-1')
on conflict (username) do nothing;
"""
