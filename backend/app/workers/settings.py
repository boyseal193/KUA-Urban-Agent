"""ARQ worker process configuration."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.workers.tasks import run_idealista_scan_job

# Laundry job lives in the second vertical and must coexist with storage.
from app.laundry.workers.tasks import run_laundry_scan_job


def _redis_settings() -> RedisSettings:
    raw = get_settings().REDIS_URL
    u = urlparse(raw)
    host = u.hostname or "localhost"
    port = u.port or 6379
    db = 0
    if u.path and u.path != "/":
        try:
            db = int(u.path.strip("/"))
        except ValueError:
            db = 0
    password = unquote(u.password) if u.password else None
    return RedisSettings(host=host, port=port, database=db, password=password)


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [run_idealista_scan_job, run_laundry_scan_job]
    max_tries = 3
    job_timeout = 3_600  # 1h — large Idealista batches
