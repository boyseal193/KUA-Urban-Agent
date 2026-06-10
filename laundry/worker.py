"""Laundry async scan worker.

Called by ``jobs.orchestrator.run_job`` whenever the storage worker loop
picks up a ``scan_jobs`` row with ``job_type='laundry_scan'``.

All scan orchestration is delegated to ``laundry.sequencer.AutonomousSequencer``
which runs the full acquisition workflow (URL generation, discovery broadening,
dedupe, per-listing retries, scoring, memo, Excel export, resume).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from jobs import store as job_store

from laundry.sequencer import AutonomousConfig, AutonomousSequencer

log = logging.getLogger("kua.laundry.worker")


def _safe_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def run_laundry_scan(job_id: str) -> Dict[str, Any]:
    started_worker = os.getenv("WORKER_ID") or f"laundry-worker-{os.getpid()}"

    try:
        job = job_store.get_job(job_id)
    except Exception as exc:
        log.exception("Could not load job %s: %s", job_id, exc)
        return {"success": False, "error": f"job_load_failed: {exc}", "job_id": job_id}

    payload = _safe_payload(job)
    config = AutonomousConfig.from_payload(payload)

    log.info(
        "laundry.scan delegate job_id=%s autonomous=%s mode=%s concurrency=%s",
        job_id,
        config.enabled,
        config.operation_mode,
        config.concurrency,
    )

    sequencer = AutonomousSequencer(
        job_id=job_id,
        job=job,
        payload=payload,
        config=config,
        worker_id=started_worker,
    )
    return sequencer.run()
