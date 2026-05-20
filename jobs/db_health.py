"""Database schema health checks for the async scan pipeline."""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

from database import supabase

REQUIRED_TABLES: Tuple[str, ...] = (
    "scan_jobs",
    "scan_steps",
    "scan_logs",
    "scan_errors",
    "scan_listing_results",
    "generated_memos",
    "extracted_properties",
)

_CACHE_TTL_SEC = 30.0
_cache: Optional[Tuple[float, Dict[str, object]]] = None

_MISSING_TABLE_RE = re.compile(
    r"Could not find the table 'public\.([a-z_]+)'",
    re.IGNORECASE,
)


def _is_missing_table_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == "PGRST205":
        return True
    msg = str(exc).lower()
    return "could not find the table" in msg or "pgrst205" in msg


def _table_from_error(exc: Exception) -> Optional[str]:
    msg = str(exc)
    m = _MISSING_TABLE_RE.search(msg)
    if m:
        return m.group(1)
    if hasattr(exc, "message") and isinstance(exc.message, dict):
        inner = exc.message.get("message", "")
        m = _MISSING_TABLE_RE.search(str(inner))
        if m:
            return m.group(1)
    return None


def check_missing_tables(*, force: bool = False) -> List[str]:
    """Probe each required table with a zero-row select."""
    global _cache
    now = time.time()

    if not force and _cache is not None:
        ts, payload = _cache
        if now - ts < _CACHE_TTL_SEC:
            return list(payload.get("missing_tables") or [])

    missing: List[str] = []
    for table in REQUIRED_TABLES:
        try:
            supabase.table(table).select("id").limit(1).execute()
        except Exception as exc:
            if _is_missing_table_error(exc):
                missing.append(table)
            else:
                # Table exists but query failed for another reason — treat as present.
                pass

    _cache = (now, {"missing_tables": missing, "ready": len(missing) == 0})
    return missing


def database_health(*, force: bool = False) -> Dict[str, object]:
    missing = check_missing_tables(force=force)
    return {
        "success": len(missing) == 0,
        "missing_tables": missing,
        "required_tables": list(REQUIRED_TABLES),
        "message": (
            "All pipeline tables present"
            if not missing
            else f"Missing tables: {', '.join(missing)}"
        ),
    }


def assert_pipeline_ready(*, force: bool = False) -> None:
    from jobs.errors import DatabaseSetupError

    missing = check_missing_tables(force=force)
    if missing:
        raise DatabaseSetupError(missing)
