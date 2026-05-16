"""Password hashing (bcrypt) and JWT creation / validation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(
    settings: Settings,
    *,
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(settings: Settings, *, subject: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "sub": subject,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, exp


def decode_token(settings: Settings, token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


def safe_decode(settings: Settings, token: str) -> Optional[Dict[str, Any]]:
    try:
        return decode_token(settings, token)
    except JWTError:
        return None
