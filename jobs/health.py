"""Health checks for K.U.A. platform dependencies."""

from __future__ import annotations

import os
from typing import Any, Dict

from jobs.db_health import database_health


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


def full_health() -> Dict[str, Any]:
    db = database_health(force=True)
    checks = {
        "database": db,
        "openai": check_openai(),
        "anthropic": check_anthropic(),
        "scraper": check_scraper(),
    }
    all_ok = db.get("success") and all(c.get("ok") for c in checks.values() if c is not db)
    return {
        "ok": all_ok,
        "service": "kua-backend",
        "checks": checks,
    }
