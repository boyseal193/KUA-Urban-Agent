"""ARQ settings for an optional laundry-only worker process.

Operators can either:

* Run the **shared worker** (``arq app.workers.settings.WorkerSettings``) — the
  laundry job is registered there too.
* Run a **dedicated laundry worker** (``arq app.laundry.workers.settings.WorkerSettings``)
  if they want noisy-neighbour isolation on Railway.
"""
from __future__ import annotations

from app.laundry.workers.tasks import run_laundry_scan_job
from app.workers.settings import _redis_settings


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [run_laundry_scan_job]
    max_tries = 3
    job_timeout = 3_600
