"""
Background jobs for the laundry vertical.

The function is registered both inside the existing ARQ worker
(:mod:`app.workers.settings`) and in :mod:`app.laundry.workers.settings` for
operators that prefer to run a dedicated laundry-only worker process.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

import structlog
from redis.asyncio import Redis

from app.db.session import AsyncSessionLocal
from app.laundry.repository import get_scan_job, update_scan_job_progress
from app.laundry.services.scan_service import run_laundry_scan

log = structlog.get_logger(__name__)


async def run_laundry_scan_job(
    ctx: Dict[str, Any],
    job_id: str,
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    redis_client: Redis = ctx["redis"]
    uid = UUID(job_id)
    async with AsyncSessionLocal() as db:
        try:
            out = await run_laundry_scan(
                db,
                job_id=uid,
                overrides=overrides or {},
                redis_client=redis_client,
            )
            await db.commit()
            return out
        except Exception as exc:
            log.exception("laundry.worker_failed", job_id=job_id)
            await db.rollback()
            async with AsyncSessionLocal() as db2:
                job = await get_scan_job(db2, uid)
                if job:
                    await update_scan_job_progress(
                        db2, job, status="failed", error_message=str(exc)
                    )
                    await db2.commit()
            raise
