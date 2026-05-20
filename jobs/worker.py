"""Background worker — polls Supabase for queued scan jobs.

Production-grade resilience guarantees
--------------------------------------
1. The worker loop NEVER exits because of a logging error. Every log call is
   wrapped in :func:`_safe_log` and the underlying stdlib logger is configured
   with ``logging.raiseExceptions = False`` in :mod:`jobs.logging_util`.
2. A failure inside :func:`run_job` is caught, the job is marked ``failed``
   in Supabase (belt-and-suspenders — the orchestrator also does this), and
   the loop continues with the next queued job.
3. Transient Supabase failures (claim/sweep/update) trigger a short sleep and
   another poll, never a process exit.
4. Even a catastrophic exception at the loop level (e.g. KeyError, AttributeError
   raised above the per-job ``try/except``) is caught by an outer watchdog
   that sleeps and restarts the inner loop. Only SIGINT / SIGTERM stop the
   process.
5. Heartbeats are emitted on a dedicated daemon thread and dead-job sweeps
   run on startup AND periodically, so stale jobs from a previous crash are
   always recovered.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import time
import uuid
from typing import Any, Callable

from jobs.constants import (
    JOB_FAILED,
    JOB_HEARTBEAT_STALE_SEC,
    WORKER_HEARTBEAT_INTERVAL_SEC,
    WORKER_POLL_INTERVAL_SEC,
)
from jobs.db_health import check_missing_tables
from jobs.errors import DatabaseSetupError, StoreError
from jobs.logging_util import configure_logging, get_logger
from jobs import store
from jobs.orchestrator import run_job

_running = True


# ---------------------------------------------------------------------------
# Defensive logging helpers
# ---------------------------------------------------------------------------
def _safe_log(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Invoke a logger method without ever letting it propagate an exception.

    Final fallback is a plain :func:`print` to stderr, which itself is wrapped
    in a try/except so even a broken stderr cannot crash the worker.
    """
    try:
        fn(*args, **kwargs)
        return
    except Exception:
        pass
    try:
        sys.stderr.write(f"[worker] log-emit-failed args={args!r}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _safe_mark_failed(job_id: str, exc: BaseException) -> None:
    """Mark a job as failed in Supabase. Swallows every exception."""
    try:
        store.update_job(
            job_id,
            status=JOB_FAILED,
            error_message=str(exc)[:1000],
            finished_at=store._now(),
        )
    except Exception:
        pass
    try:
        store.record_error(
            job_id,
            error_type=type(exc).__name__,
            message=str(exc)[:1000],
            retryable=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------
def _handle_signal(signum, _frame):
    global _running
    _safe_log(get_logger("-", "worker").info, "Shutdown signal received (%s)", signum)
    _running = False


def _make_worker_id() -> str:
    host = socket.gethostname()
    pid = os.getpid()
    return os.getenv("WORKER_ID") or f"{host}-{pid}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Heartbeat thread
# ---------------------------------------------------------------------------
def _heartbeat_thread(job_id_ref: dict, worker_id: str) -> threading.Thread:
    def loop():
        while _running:
            jid = job_id_ref.get("id")
            if jid:
                try:
                    store.touch_heartbeat(jid, worker_id)
                except Exception:
                    pass
            try:
                time.sleep(WORKER_HEARTBEAT_INTERVAL_SEC)
            except Exception:
                pass

    t = threading.Thread(target=loop, name="kua-heartbeat", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Inner loop (one iteration = one poll/claim/process cycle)
# ---------------------------------------------------------------------------
def _inner_worker_loop(poll_interval: float, worker_id: str, log, job_id_ref: dict) -> None:
    """The main poll/claim/process cycle.

    Any exception here is caught by the outer :func:`worker_loop` watchdog,
    which sleeps briefly and re-enters the loop. The function itself only
    returns when ``_running`` flips to ``False``.
    """
    last_sweep = time.monotonic()

    while _running:
        # Periodic dead-job sweep (every 60s).
        if time.monotonic() - last_sweep > 60:
            try:
                store.sweep_dead_jobs(JOB_HEARTBEAT_STALE_SEC)
            except Exception as exc:
                _safe_log(log.warning, "Periodic sweep failed: %s", exc)
            last_sweep = time.monotonic()

        try:
            job = store.claim_next_job(worker_id)
        except DatabaseSetupError as exc:
            _safe_log(log.error, "Database setup incomplete: %s. Sleeping 30s.", exc)
            time.sleep(30)
            continue
        except StoreError as exc:
            _safe_log(log.warning, "claim_next_job transient failure: %s", exc)
            time.sleep(poll_interval)
            continue
        except Exception as exc:
            _safe_log(log.exception, "Unexpected error claiming job: %s", exc)
            time.sleep(poll_interval)
            continue

        if not job:
            time.sleep(poll_interval)
            continue

        job_id = job.get("id")
        if not job_id:
            _safe_log(log.warning, "Claim returned job with no id: %r", job)
            time.sleep(poll_interval)
            continue

        job_id_ref["id"] = job_id
        wlog = get_logger(job_id, "worker")
        _safe_log(
            wlog.info,
            "Processing job type=%s url=%s",
            job.get("job_type"),
            job.get("search_url"),
        )

        try:
            run_job(job_id)
            _safe_log(wlog.info, "Job finished")
        except Exception as exc:
            _safe_log(wlog.exception, "Job processing failed: %s", exc)
            # Belt-and-suspenders: orchestrator already marks failed on its
            # own error path, but mark again here in case that branch was
            # somehow skipped (e.g. crash before reaching the except clause).
            _safe_mark_failed(job_id, exc)
        finally:
            job_id_ref["id"] = None


# ---------------------------------------------------------------------------
# Outer loop with watchdog
# ---------------------------------------------------------------------------
def worker_loop(poll_interval: float = WORKER_POLL_INTERVAL_SEC) -> None:
    """Main worker entrypoint.

    Outer watchdog: any exception that escapes :func:`_inner_worker_loop`
    (which should be impossible given the per-iteration try/excepts, but we
    are paranoid) triggers a 10s sleep and a restart of the inner loop.
    Only SIGINT / SIGTERM (which flip ``_running`` to ``False``) stop the
    process.
    """
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    log = get_logger("-", "worker")

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception as exc:
        # Some hosts (e.g. when running inside a non-main thread) reject
        # signal registration. Worker still runs; the host will SIGKILL.
        _safe_log(log.warning, "Could not install signal handlers: %s", exc)

    worker_id = _make_worker_id()
    _safe_log(
        log.info,
        "K.U.A. scan worker starting id=%s poll=%ss",
        worker_id,
        poll_interval,
    )

    # Wait for pipeline schema before doing anything else.
    while _running:
        try:
            missing = check_missing_tables(force=True)
            if not missing:
                break
            _safe_log(
                log.error,
                "Database setup incomplete — missing tables: %s. Sleeping 30s and retrying.",
                ", ".join(missing),
            )
        except Exception as exc:
            _safe_log(log.error, "Could not reach Supabase: %s. Sleeping 30s.", exc)
        time.sleep(30)

    if not _running:
        _safe_log(log.info, "Worker stopped before any job ran (id=%s)", worker_id)
        return

    # Sweep stuck jobs left behind by a previous crash / restart.
    try:
        recovered = store.sweep_dead_jobs(JOB_HEARTBEAT_STALE_SEC)
        if recovered:
            _safe_log(log.warning, "Recovered %s stale job(s) on startup", recovered)
    except Exception as exc:
        _safe_log(log.warning, "Startup sweep failed: %s", exc)

    job_id_ref: dict = {"id": None}
    _heartbeat_thread(job_id_ref, worker_id)

    # Outer watchdog: restart the inner loop on catastrophic failures.
    while _running:
        try:
            _inner_worker_loop(poll_interval, worker_id, log, job_id_ref)
            # Inner loop only returns cleanly when _running flips to False.
            break
        except KeyboardInterrupt:
            break
        except SystemExit:
            break
        except BaseException as exc:
            _safe_log(
                log.exception,
                "Worker inner loop crashed unexpectedly; restarting in 10s: %s",
                exc,
            )
            try:
                time.sleep(10)
            except Exception:
                pass

    _safe_log(log.info, "Worker stopped (id=%s)", worker_id)


if __name__ == "__main__":
    worker_loop()
