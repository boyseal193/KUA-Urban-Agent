"""In-process counters (replace with Prometheus client if required)."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict

_lock = threading.Lock()
_counters: Dict[str, int] = {
    "http_requests_total": 0,
    "http_errors_total": 0,
    "auth_failures_total": 0,
    "scans_started_total": 0,
    "ai_memo_generations_total": 0,
}
_start_time = time.time()


def incr(name: str, delta: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + delta


def snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "uptime_seconds": round(time.time() - _start_time, 3),
            "counters": dict(_counters),
        }
