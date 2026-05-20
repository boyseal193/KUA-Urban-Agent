"""Structured logging for K.U.A. pipeline jobs.

Production-safe design
----------------------
* The root formatter only uses fields that ALWAYS exist on a LogRecord:
  ``%(asctime)s | %(levelname)s | %(name)s | %(message)s``
  This means a log line emitted by a third-party library (uvicorn, httpx,
  postgrest, supabase, urllib3, ...) can never crash the worker by missing
  a custom field like ``%(job_id)s``.

* :class:`JobLogAdapter` prepends ``[job=X step=Y]`` to the message text
  itself, so we keep the contextual prefix without depending on custom
  formatter fields. The same context is still attached to the LogRecord
  via ``extra=`` so downstream handlers (Datadog, JSON shippers, etc.)
  can still read it.

* :class:`_SafeDefaultsFilter` injects safe defaults for any custom field
  a future operator might add to ``LOG_FORMAT`` via env override. This is
  belt-and-suspenders: even if someone reintroduces ``%(job_id)s`` later,
  the worker still does not crash.

* ``logging.raiseExceptions = False`` guarantees that even if a brand new
  formatter mistake slips in, Python's logging module will swallow the
  error instead of propagating it up the call stack and killing the
  worker loop.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

# Universal, crash-proof formatter. Only references fields guaranteed by
# the stdlib LogRecord. Override with $LOG_FORMAT only if you know what
# you're doing — and even then the SafeDefaultsFilter below protects us.
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_FORMAT = os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT)

# Fields that legacy/future formatters might reference. We pre-populate
# every LogRecord with these defaults so formatting can never KeyError.
_SAFE_DEFAULTS = {
    "job_id": "-",
    "step_key": "-",
    "scan_id": "-",
    "worker_id": "-",
    "request_id": "-",
}

_configured = False


class _SafeDefaultsFilter(logging.Filter):
    """Inject default values for any custom extras a formatter may reference.

    This is defense-in-depth. Our default formatter does not reference any
    of these fields, but if someone overrides ``$LOG_FORMAT`` (or attaches
    a custom handler with an unsafe formatter), this filter guarantees the
    fields are always present on every LogRecord.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key, val in _SAFE_DEFAULTS.items():
            if not hasattr(record, key):
                setattr(record, key, val)
        return True


class JobLogAdapter(logging.LoggerAdapter):
    """Logger adapter that prefixes ``[job=X step=Y]`` to every message.

    The prefix is added to the **message text** (not via formatter fields),
    so it works regardless of which formatter the root logger ends up with.
    The job/step context is also attached to the LogRecord via ``extra=`` so
    structured log shippers can read it programmatically.
    """

    def process(self, msg: Any, kwargs: Any):
        job_id = (self.extra or {}).get("job_id", "-") if self.extra else "-"
        step_key = (self.extra or {}).get("step_key", "-") if self.extra else "-"

        # Keep extras for downstream structured handlers.
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("job_id", job_id)
        extra.setdefault("step_key", step_key)

        # Prepend a human-readable prefix to the message text itself.
        # Preserve %-formatting placeholders in `msg` (e.g. "%s") so the
        # caller's args still interpolate correctly downstream.
        try:
            prefix = f"[job={job_id} step={step_key}] "
            return prefix + str(msg), kwargs
        except Exception:
            # As a last resort, never let prefix generation break logging.
            return msg, kwargs


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger exactly once. Safe to call repeatedly.

    Idempotent: subsequent calls are no-ops. Replaces any pre-existing
    handlers so a library that attached an unsafe handler at import time
    cannot crash us later.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Never let a logging formatter mistake propagate into the host process.
    logging.raiseExceptions = False

    root = logging.getLogger()

    # Drop any handlers attached by libraries at import time so we control
    # the formatter for every record that flows through the root logger.
    for handler in list(root.handlers):
        try:
            root.removeHandler(handler)
        except Exception:
            pass

    handler = logging.StreamHandler(sys.stdout)
    try:
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
    except Exception:
        # If an operator passed an invalid $LOG_FORMAT, fall back silently.
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    handler.addFilter(_SafeDefaultsFilter())

    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    # Quiet down a few notoriously chatty libraries so production logs stay
    # readable. They still emit warnings/errors.
    for noisy in ("httpx", "httpcore", "urllib3", "hpack", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(job_id: str = "-", step_key: str = "-") -> JobLogAdapter:
    """Return a job-aware logger adapter. Safe to call from anywhere."""
    configure_logging()
    base = logging.getLogger("kua.jobs")
    return JobLogAdapter(base, {"job_id": str(job_id or "-"), "step_key": str(step_key or "-")})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json(data: Any) -> Any:
    try:
        json.dumps(data, default=str)
        return data
    except Exception:
        return {"repr": repr(data)}


def format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def classify_error(exc: BaseException) -> tuple[str, bool]:
    """Return ``(error_type, retryable)``."""
    from jobs.constants import TRANSIENT_ERROR_MARKERS

    msg = str(exc).lower()
    error_type = type(exc).__name__
    retryable = any(marker in msg for marker in TRANSIENT_ERROR_MARKERS)
    if isinstance(exc, TimeoutError):
        retryable = True
        error_type = "TimeoutError"
    return error_type, retryable
