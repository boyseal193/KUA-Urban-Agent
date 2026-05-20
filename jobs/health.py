"""Health checks for K.U.A. platform dependencies."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import requests


def check_supabase() -> Dict[str, Any]:
    started = time.monotonic()
    try:
        from database import supabase
        res = supabase.table("scan_jobs").select("id").limit(1).execute()
        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "sample": bool(res.data is not None),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_openai() -> Dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"ok": False, "error": "OPENAI_API_KEY not set"}
    return {"ok": True, "configured": True}


def check_anthropic() -> Dict[str, Any]:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set"}
    return {"ok": True, "configured": True}


def check_scraper() -> Dict[str, Any]:
    key = os.getenv("BRIGHTDATA_API_KEY")
    if not key:
        return {"ok": False, "error": "BRIGHTDATA_API_KEY not set"}
    return {"ok": True, "configured": True}


def check_backend_reachable(url: str) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        r = requests.get(url.rstrip("/") + "/", timeout=10)
        return {
            "ok": r.status_code < 500,
            "status": r.status_code,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def full_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "kua-backend",
        "checks": {
            "supabase": check_supabase(),
            "openai": check_openai(),
            "anthropic": check_anthropic(),
            "scraper": check_scraper(),
        },
    }
