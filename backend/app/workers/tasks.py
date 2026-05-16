"""
ARQ worker jobs — long-running scans off the request thread.

Run: `arq app.workers.settings.WorkerSettings`
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

import structlog
from redis.asyncio import Redis

from app.db.session import AsyncSessionLocal
from app.repositories.scan_repository import get_scan
from app.services.scan_service import run_idealista_scan_sync

log = structlog.get_logger(__name__)


async def run_idealista_scan_job(
    ctx: Dict[str, Any],
    scan_id: str,
    search_url: str,
    limit: int,
    generate_excel: bool,
    filters_used: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Background scan: persists results to PostgreSQL and publishes `ws:scan:{id}` events.
    """
    redis_client: Redis = ctx["redis"]
    uid = UUID(scan_id)
    async with AsyncSessionLocal() as db:
        try:
            out = await run_idealista_scan_sync(
                db,
                search_url=search_url,
                limit=limit,
                generate_excel=generate_excel,
                filters_used=filters_used or {},
                redis_client=redis_client,
                scan_id=uid,
            )
            await db.commit()
            return out
        except Exception as e:
            log.exception("worker.scan_failed", scan_id=scan_id)
            await db.rollback()
            async with AsyncSessionLocal() as db2:
                row = await get_scan(db2, uid)
                if row:
                    row.status = "failed"
                    row.error_message = str(e)
                    await db2.commit()
            raise
