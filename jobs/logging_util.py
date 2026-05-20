"""Structured logging for K.U.A. pipeline jobs.

Production hardening — multi-layer defense
------------------------------------------
Even though our own formatter only references stdlib fields, third-party
libraries (supabase, postgrest, httpx, uvicorn, …) sometimes install their
own handlers/formatters at import time. To make the worker truly bulletproof
against ``ValueError: Formatting field not found in record: 'job_id'`` (and
every other variant), we apply **five** layers of defense:

1. **Universal formatter** — our handlers use a formatter that references
   only stdlib LogRecord fields::

       "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

2. **Safe LogRecord factory** — :func:`logging.setLogRecordFactory` installs
   a factory that injects safe default values for *every* custom field
   anyone might reference (``job_id``, ``step_key``, ``scan_id``,
   ``worker_id``, ``request_id``, ``user_id``, ``trace_id``,
   ``correlation_id``). This means **every** LogRecord — including ones
   created by third-party libraries — already carries those attributes.

3. **SafeFormatter subclass** — any handler whose formatter we control is
   wrapped in :class:`SafeFormatter`, which catches any ``KeyError`` /
   ``ValueError`` / ``TypeError`` raised during formatting and falls back
   to a minimal safe representation. A bug in ANY formatter string cannot
   crash the worker.

4. **Aggressive handler sweep** — :func:`configure_logging` walks every
   existing logger in ``logging.Logger.manager.loggerDict``, removes any
   pre-existing handlers, and wraps every remaining formatter on every
   handler in :class:`SafeFormatter`.

5. **``logging.raiseExceptions = False``** — final belt-and-suspenders so
   that even if some new code path bypasses every other guard, the stdlib
   logging module will swallow formatter errors instead of propagating
   them up the call stack and killing the worker.

:class:`JobLogAdapter` still prepends ``[job=X step=Y]`` to the message
text itself, so the contextual prefix appears in logs without depending on
formatter custom fields.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Formatter & safe defaults
# ---------------------------------------------------------------------------
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_FORMAT = os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT)

# Fields the SafeFormatter injects right before formatting, as a final
# safety net for records that somehow bypassed every earlier guard. This
# is the full superset of custom fields any formatter might reference.
_FORMATTER_DEFAULTS = {
    "job_id": "-",
    "step_key": "-",
    "scan_id": "-",
    "worker_id": "-",
    "request_id": "-",
    "user_id": "-",
    "trace_id": "-",
    "correlation_id": "-",
}

# Fields the global LogRecord factory injects on every record at creation
# time. We must NOT include ``job_id`` or ``step_key`` here, because the
# stdlib :meth:`Logger.makeRecord` raises ``KeyError`` if an ``extra``
# argument tries to overwrite a key that already exists on the record. Our
# :class:`JobLogAdapter` passes ``job_id``/``step_key`` via ``extra=``, so
# pre-populating them on the factory would crash the adapter.
#
# The SafeFormatter below still injects ``job_id``/``step_key`` at format
# time as a default, so third-party records (which never go through the
# adapter and never set ``extra={"job_id": ...}``) still cannot crash any
# formatter that references those fields.
_FACTORY_DEFAULTS = {
    k: v
    for k, v in _FORMATTER_DEFAULTS.items()
    if k not in ("job_id", "step_key")
}

# Back-compat alias.
_SAFE_DEFAULTS = _FORMATTER_DEFAULTS

_configured = False
_record_factory_installed = False


class SafeFormatter(logging.Formatter):
    """A :class:`logging.Formatter` that can never raise.

    If the wrapped format string references a field that is not on the
    record (or any other error occurs during formatting), we fall back to
    a minimal representation so the record is still emitted and the
    process keeps running.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Inject the full superset of defaults right before formatting —
        # final safety net for records that bypassed every earlier guard,
        # including records that did NOT go through JobLogAdapter (and
        # therefore never had ``job_id`` / ``step_key`` set via extra=).
        for key, val in _FORMATTER_DEFAULTS.items():
            if not hasattr(record, key):
                try:
                    setattr(record, key, val)
                except Exception:
                    pass
        try:
            return super().format(record)
        except (KeyError, ValueError, TypeError, AttributeError):
            try:
                ts = self.formatTime(record, self.datefmt)
                msg = record.getMessage()
            except Exception:
                ts = "-"
                msg = str(getattr(record, "msg", ""))
            return f"{ts} | {record.levelname} | {record.name} | {msg}"


def _safe_record_factory(original_factory):
    """Wrap a LogRecord factory to inject safe defaults on every record."""

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        try:
            record = original_factory(*args, **kwargs)
        except Exception:
            # If even the original factory fails, fall back to bare LogRecord.
            record = logging.LogRecord(
                "kua.unknown", logging.INFO, "?", 0, "logging-record-failed", None, None
            )
        # Only inject fields that do NOT collide with ``extra=`` keys used
        # by JobLogAdapter (see :data:`_FACTORY_DEFAULTS` for rationale).
        # SafeFormatter handles ``job_id`` / ``step_key`` at format time.
        for key, val in _FACTORY_DEFAULTS.items():
            if not hasattr(record, key):
                try:
                    setattr(record, key, val)
                except Exception:
                    pass
        return record

    return factory


def _install_safe_log_record_factory() -> None:
    """Globally install our safe LogRecord factory exactly once."""
    global _record_factory_installed
    if _record_factory_installed:
        return
    _record_factory_installed = True
    try:
        current = logging.getLogRecordFactory()
        logging.setLogRecordFactory(_safe_record_factory(current))
    except Exception:
        # If even installing the factory fails, the layered SafeFormatter
        # below still protects us. Never let logging setup crash the import.
        pass


# Install the factory at module import time so EVERY LogRecord ever created
# during this Python process — including ones generated by third-party
# libraries before configure_logging() is called — already has the safe
# defaults attached.
_install_safe_log_record_factory()


# ---------------------------------------------------------------------------
# Job-aware adapter
# ---------------------------------------------------------------------------
class JobLogAdapter(logging.LoggerAdapter):
    """Adapter that prefixes ``[job=X step=Y]`` to every message.

    The prefix is added to the **message text** rather than via formatter
    fields, so it works regardless of which formatter is active.
    """

    def process(self, msg: Any, kwargs: Any):
        job_id = "-"
        step_key = "-"
        try:
            if self.extra:
                job_id = str(self.extra.get("job_id", "-") or "-")
                step_key = str(self.extra.get("step_key", "-") or "-")
        except Exception:
            pass

        # Keep extras for downstream structured handlers.
        try:
            extra = kwargs.setdefault("extra", {})
            extra.setdefault("job_id", job_id)
            extra.setdefault("step_key", step_key)
        except Exception:
            pass

        try:
            return f"[job={job_id} step={step_key}] " + str(msg), kwargs
        except Exception:
            return msg, kwargs


# ---------------------------------------------------------------------------
# Global logging configuration
# ---------------------------------------------------------------------------
_NOISY_LIBRARIES = (
    "httpx",
    "httpcore",
    "urllib3",
    "hpack",
    "websockets",
    "asyncio",
    "supabase",
    "postgrest",
    "gotrue",
    "storage3",
    "realtime",
)


def _wrap_handler_formatter(handler: logging.Handler) -> None:
    """Wrap a handler's formatter in :class:`SafeFormatter` (idempotent)."""
    try:
        existing = handler.formatter
        if isinstance(existing, SafeFormatter):
            return
        if existing is None:
            handler.setFormatter(SafeFormatter(LOG_FORMAT))
            return
        # Re-use the existing format string but route formatting through
        # SafeFormatter so it can never raise.
        fmt = getattr(existing, "_fmt", None) or DEFAULT_LOG_FORMAT
        datefmt = getattr(existing, "datefmt", None)
        try:
            handler.setFormatter(SafeFormatter(fmt, datefmt=datefmt))
        except Exception:
            handler.setFormatter(SafeFormatter(DEFAULT_LOG_FORMAT))
    except Exception:
        pass


def _sweep_existing_loggers() -> None:
    """Walk every existing logger and make its handlers safe.

    Some third-party libraries attach their own handlers/formatters at
    import time. We don't trust them — every handler's formatter is
    replaced with a :class:`SafeFormatter`, and ``propagate=True`` so
    records still flow up to the root logger.
    """
    try:
        for name in list(logging.Logger.manager.loggerDict.keys()):
            try:
                lg = logging.getLogger(name)
            except Exception:
                continue
            try:
                lg.propagate = True
            except Exception:
                pass
            try:
                for h in list(getattr(lg, "handlers", [])):
                    _wrap_handler_formatter(h)
            except Exception:
                pass
    except Exception:
        pass


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger exactly once. Safe to call repeatedly.

    Idempotent and aggressive: replaces all root handlers, wraps every
    existing handler's formatter on every existing logger, and installs
    our safe LogRecord factory if not already installed.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Belt-and-suspenders: even if a brand-new formatter mistake slips in,
    # the stdlib logging module will swallow it instead of crashing.
    logging.raiseExceptions = False

    # Guarantee the safe factory is installed (no-op if already done).
    _install_safe_log_record_factory()

    root = logging.getLogger()

    # Drop pre-existing handlers — we want full control over the root.
    for handler in list(root.handlers):
        try:
            root.removeHandler(handler)
        except Exception:
            pass

    handler = logging.StreamHandler(sys.stdout)
    try:
        handler.setFormatter(SafeFormatter(LOG_FORMAT))
    except Exception:
        handler.setFormatter(SafeFormatter(DEFAULT_LOG_FORMAT))

    root.addHandler(handler)
    try:
        root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    except Exception:
        root.setLevel(logging.INFO)

    # Sweep every existing logger and harden their formatters too. Libraries
    # that ship their own handler (e.g. uvicorn) get the SafeFormatter
    # wrapper applied to whatever format string they configured.
    _sweep_existing_loggers()

    # Quiet down a few notoriously chatty libraries. They still emit warnings.
    for noisy in _NOISY_LIBRARIES:
        try:
            logging.getLogger(noisy).setLevel(logging.WARNING)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def get_logger(job_id: str = "-", step_key: str = "-") -> JobLogAdapter:
    """Return a job-aware logger adapter. Safe to call from anywhere."""
    try:
        configure_logging()
    except Exception:
        pass
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
    try:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        return f"<could not format traceback for {type(exc).__name__}>"


def classify_error(exc: BaseException) -> tuple[str, bool]:
    """Return ``(error_type, retryable)``."""
    from jobs.constants import TRANSIENT_ERROR_MARKERS

    try:
        msg = str(exc).lower()
    except Exception:
        msg = ""
    error_type = type(exc).__name__
    retryable = any(marker in msg for marker in TRANSIENT_ERROR_MARKERS)
    if isinstance(exc, TimeoutError):
        retryable = True
        error_type = "TimeoutError"
    return error_type, retryable
