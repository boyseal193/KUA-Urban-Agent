"""Liveness + basic metrics (JSON)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.core.metrics import snapshot
from app.db.session import async_engine

router = APIRouter(tags=["observability"])


@router.get("/health")
async def health() -> dict:
    """Process up; DB checked in /health/ready for orchestrators."""
    return {
        "status": "ok",
        "service": get_settings().APP_NAME,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def health_ready(response: Response) -> dict:
    """PostgreSQL connectivity (async pool ping)."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as e:
        response.status_code = 503
        return {"status": "not_ready", "database": "error", "detail": str(e)}


@router.get("/metrics")
async def metrics_json() -> dict:
    """Structured counters; swap for Prometheus exposition format if needed."""
    data = snapshot()
    data["defaults"] = {"note": "Wire Datadog/Prometheus exporter for production KPIs"}
    return data
