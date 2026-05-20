#!/usr/bin/env python3
"""Railway worker entrypoint: ``python worker_main.py``.

Installs the safe LogRecord factory BEFORE any other import so that any
third-party library imported transitively (supabase, httpx, postgrest, …)
that logs at import time already has the safe-defaults factory in place.
"""

# IMPORTANT: keep this block at the very top — before any other import.
from jobs.logging_util import (  # noqa: E402
    _install_safe_log_record_factory,
    configure_logging,
)

_install_safe_log_record_factory()
configure_logging()

from jobs.worker import worker_loop  # noqa: E402

if __name__ == "__main__":
    worker_loop()
