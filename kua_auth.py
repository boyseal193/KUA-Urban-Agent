"""K.U.A. backend auth router.

Multi-user support:
  * AUTH_USERS env var (JSON array) is the preferred mechanism:
        AUTH_USERS='[{"username":"admin","password":"...","display_name":"Admin","clearance":"tier-1"}]'
  * Falls back to AUTH_USERNAME / AUTH_PASSWORD for single-user setups.

Endpoints:
  POST /auth/login   → { success, username, display_name, clearance, access_token, token_type }
  GET  /auth/me      → echoes presence
  POST /auth/logout  → no-op (cookies live on the frontend)
  GET  /auth/health  → { ok, users, source }
"""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


def _normalise_user(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    username = str(raw.get("username") or "").strip()
    password = str(raw.get("password") or "")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
        "display_name": str(raw.get("display_name") or raw.get("displayName") or username).strip(),
        "clearance": str(raw.get("clearance") or "operator").strip(),
    }


def _users_from_env() -> tuple[List[Dict[str, str]], str]:
    raw_users = os.getenv("AUTH_USERS")
    if raw_users:
        try:
            parsed = json.loads(raw_users)
            if isinstance(parsed, list):
                cleaned: List[Dict[str, str]] = []
                for item in parsed:
                    norm = _normalise_user(item)
                    if norm:
                        cleaned.append(norm)
                if cleaned:
                    return cleaned, "AUTH_USERS"
        except Exception:
            # Fall through to the single-user fallback.
            pass

    single = _normalise_user(
        {
            "username": os.getenv("AUTH_USERNAME", "admin"),
            "password": os.getenv("AUTH_PASSWORD", "KUA2026secure"),
            "display_name": os.getenv("AUTH_DISPLAY_NAME", "Acquisitions Operator"),
            "clearance": os.getenv("AUTH_CLEARANCE", "tier-1"),
        }
    )
    return ([single] if single else []), "AUTH_USERNAME/AUTH_PASSWORD"


def get_users() -> List[Dict[str, str]]:
    users, _ = _users_from_env()
    return users


def make_token(username: str) -> str:
    return f"kua-{username}-{int(time.time())}-{secrets.token_hex(16)}"


@router.post("/login")
def login(data: LoginRequest):
    users = get_users()
    if not users:
        raise HTTPException(
            status_code=500,
            detail="Auth not configured (set AUTH_USERS or AUTH_USERNAME/AUTH_PASSWORD).",
        )

    for user in users:
        if secrets.compare_digest(data.username, user["username"]) and secrets.compare_digest(
            data.password, user["password"]
        ):
            return {
                "success": True,
                "message": "Authenticated",
                "username": user["username"],
                "display_name": user.get("display_name", user["username"]),
                "displayName": user.get("display_name", user["username"]),
                "clearance": user.get("clearance", "operator"),
                "access_token": make_token(user["username"]),
                "token_type": "bearer",
            }

    raise HTTPException(status_code=401, detail="Invalid username or password")


@router.get("/me")
def me():
    return {"success": True, "message": "Authenticated"}


@router.post("/logout")
def logout():
    return {"success": True, "message": "Logged out"}


@router.get("/health")
def auth_health():
    users, source = _users_from_env()
    return {
        "ok": len(users) > 0,
        "users": len(users),
        "source": source,
    }
