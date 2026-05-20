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


def check_auth() -> Dict[str, Any]:
    """Auth subsystem is just env-driven; surface configuration status."""
    import json

    raw_users = os.getenv("AUTH_USERS")
    if raw_users:
        try:
            parsed = json.loads(raw_users)
            count = len(parsed) if isinstance(parsed, list) else 0
        except Exception:
            return {"ok": False, "error": "AUTH_USERS is not valid JSON"}
    else:
        count = 1  # AUTH_USERNAME / AUTH_PASSWORD fallback
    return {"ok": count > 0, "users": count}


def pipeline_health() -> Dict[str, Any]:
    """Queue + worker freshness snapshot."""
    from jobs import store

    db = database_health()
    if not db.get("success"):
        return {
            "ok": False,
            "database": db,
            "queue": {},
            "workers": {"fresh": False, "reason": "database setup incomplete"},
        }

    counts = store.pipeline_metrics()
    running = store.running_jobs()
    fresh = True
    stale_count = 0
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
    for r in running:
        hb = r.get("last_heartbeat_at") or r.get("started_at")
        if not hb or hb < cutoff:
            stale_count += 1
            fresh = False

    return {
        "ok": fresh,
        "database": db,
        "queue": counts,
        "running": len(running),
        "stale_workers": stale_count,
        "workers": {"fresh": fresh},
    }


def full_health() -> Dict[str, Any]:
    db = database_health(force=True)
    checks = {
        "database": db,
        "openai": check_openai(),
        "anthropic": check_anthropic(),
        "scraper": check_scraper(),
        "auth": check_auth(),
    }
    all_ok = bool(db.get("success")) and all(
        c.get("ok") for k, c in checks.items() if k != "database"
    )
    return {
        "ok": all_ok,
        "service": "kua-backend",
        "checks": checks,
    }
