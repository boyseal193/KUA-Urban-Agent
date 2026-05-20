"""Background worker — polls Supabase for queued scan jobs."""

from __future__ import annotations

import os
import signal
import sys
import time

from jobs.constants import WORKER_POLL_INTERVAL_SEC
from jobs.logging_util import configure_logging, get_logger
from jobs import store
from jobs.orchestrator import run_job

_running = True


def _handle_signal(signum, frame):
    global _running
    get_logger("-", "worker").info("Shutdown signal received (%s)", signum)
    _running = False


def worker_loop(poll_interval: float = WORKER_POLL_INTERVAL_SEC) -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    log = get_logger("-", "worker")
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("K.U.A. scan worker started (poll=%ss)", poll_interval)

    while _running:
        job = store.claim_next_job()
        if not job:
            time.sleep(poll_interval)
            continue

        job_id = job["id"]
        wlog = get_logger(job_id, "worker")
        wlog.info("Processing job type=%s url=%s", job.get("job_type"), job.get("search_url"))
        try:
            run_job(job_id)
            wlog.info("Job finished successfully")
        except Exception as exc:
            wlog.exception("Job processing failed: %s", exc)

    log.info("Worker stopped")


if __name__ == "__main__":
    worker_loop()
