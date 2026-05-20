"""Structured logging for K.U.A. pipeline jobs."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | job=%(job_id)s | step=%(step_key)s | %(message)s"
)


class JobLogAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: Any):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("job_id", self.extra.get("job_id", "-"))
        extra.setdefault("step_key", self.extra.get("step_key", "-"))
        return msg, kwargs


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(job_id: str = "-", step_key: str = "-") -> JobLogAdapter:
    configure_logging()
    base = logging.getLogger("kua.jobs")
    return JobLogAdapter(base, {"job_id": job_id, "step_key": step_key})


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
    """Return (error_type, retryable)."""
    from jobs.constants import TRANSIENT_ERROR_MARKERS

    msg = str(exc).lower()
    error_type = type(exc).__name__
    retryable = any(marker in msg for marker in TRANSIENT_ERROR_MARKERS)
    if isinstance(exc, TimeoutError):
        retryable = True
        error_type = "TimeoutError"
    return error_type, retryable
