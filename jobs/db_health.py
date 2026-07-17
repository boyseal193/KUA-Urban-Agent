"""Database schema health checks for the async scan pipeline.

Verifies that EVERY column the K.U.A. backend writes to actually exists in
Supabase — not just the tables. The previous version only checked tables,
which is why production was failing one column at a time
(missing created_by → missing filters → missing finished_at → ...).

The expected schema (EXPECTED_SCHEMA below) is the single source of truth
and must stay in sync with `jobs/store.py`.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

from database import supabase

log = logging.getLogger("kua.db_health")

# ---------------------------------------------------------------------------
# Canonical expected schema — every column the backend reads/writes.
#
# Keep this in lock-step with jobs/store.py + jobs/schema.sql. The audit
# was performed exhaustively from `supabase.table("X").insert/update(...)`
# call sites. Removing a column here disables the corresponding check;
# adding a column requires a matching ALTER in schema.sql.
# ---------------------------------------------------------------------------
EXPECTED_SCHEMA: Dict[str, List[str]] = {
    "scan_jobs": [
        "id",
        "job_type",
        "status",
        "created_by",
        "search_url",
        "filters",
        "payload",
        "listing_limit",
        "generate_excel",
        "progress_pct",
        "current_step",
        "listings_total",
        "listings_done",
        "listings_failed",
        "approved_count",
        "manual_review_count",
        "rejected_count",
        "result_summary",
        "result",
        "excel_path",
        "error_message",
        "retry_count",
        "max_retries",
        "request_id",
        "worker_id",
        "last_heartbeat_at",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ],
    "scan_steps": [
        "id",
        "job_id",
        "listing_index",
        "listing_url",
        "step_key",
        "step_order",
        "status",
        "attempt",
        "max_attempts",
        "payload",
        "input_data",
        "output_data",
        "result",
        "error_type",
        "error_message",
        "traceback",
        "retryable",
        "duration_ms",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ],
    "scan_logs": [
        "id",
        "job_id",
        "step_id",
        "level",
        "message",
        "context",
        "payload",
        "created_at",
    ],
    "scan_errors": [
        "id",
        "job_id",
        "step_id",
        "listing_url",
        "error_type",
        "message",
        "traceback",
        "payload",
        "retryable",
        "attempt",
        "created_at",
    ],
    "scan_listing_results": [
        "id",
        "job_id",
        "listing_index",
        "listing_url",
        "status",
        "property_id",
        "deal_status",
        "score",
        "verdict",
        "result",
        "payload",
        "error_message",
        "created_at",
        "updated_at",
    ],
    "extracted_properties": [
        "id",
        "job_id",
        "listing_url",
        "property_id",
        "extracted",
        "economics",
        "score",
        "result",
        "payload",
        "created_at",
    ],
    "generated_memos": [
        "id",
        "job_id",
        "property_id",
        "listing_url",
        "memo_text",
        "verdict",
        "deal_status",
        "payload",
        "created_at",
    ],
}

REQUIRED_TABLES: Tuple[str, ...] = tuple(EXPECTED_SCHEMA.keys())

# A healthy schema does not change at runtime, so once every column is present
# we can trust that snapshot for a long time. When the schema is INCOMPLETE we
# re-probe far more often so an operator running schema.sql sees the fix quickly.
_CACHE_TTL_OK_SEC = 300.0   # 5 min — schema verified healthy
_CACHE_TTL_BAD_SEC = 15.0   # 15 s — schema incomplete, watch for repair
_cache: Optional[Tuple[float, Dict[str, object]]] = None

_MISSING_TABLE_RE = re.compile(
    r"Could not find the table 'public\.([a-z_]+)'",
    re.IGNORECASE,
)
_MISSING_COLUMN_RE = re.compile(
    r"column ['\"]?(?:public\.)?([a-z_]+)\.([a-z_]+)['\"]? does not exist",
    re.IGNORECASE,
)
_MISSING_COLUMN_PGRST_RE = re.compile(
    r"column ['\"]?([a-z_]+)['\"]? does not exist",
    re.IGNORECASE,
)


def _error_text(exc: Exception) -> str:
    text = str(exc)
    if hasattr(exc, "message"):
        msg = getattr(exc, "message", None)
        if isinstance(msg, dict):
            text = f"{text} {msg.get('message', '')} {msg.get('details', '')} {msg.get('hint', '')}"
        elif isinstance(msg, str):
            text = f"{text} {msg}"
    if hasattr(exc, "details"):
        text = f"{text} {getattr(exc, 'details', '')}"
    if hasattr(exc, "hint"):
        text = f"{text} {getattr(exc, 'hint', '')}"
    return text


def _is_missing_table_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == "PGRST205":
        return True
    text = _error_text(exc).lower()
    return "could not find the table" in text or "pgrst205" in text


def _is_missing_column_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == "42703" or code == "PGRST204":
        return True
    text = _error_text(exc).lower()
    return (
        "does not exist" in text
        and ("column" in text or "field" in text)
    ) or "42703" in text or "pgrst204" in text


def _column_from_error(exc: Exception) -> Optional[str]:
    text = _error_text(exc)
    m = _MISSING_COLUMN_RE.search(text)
    if m:
        return m.group(2)
    m = _MISSING_COLUMN_PGRST_RE.search(text)
    if m:
        return m.group(1)
    return None


def _table_exists(table: str) -> bool:
    try:
        supabase.table(table).select("id").limit(1).execute()
        return True
    except Exception as exc:
        if _is_missing_table_error(exc):
            return False
        # Any other error means the table exists (we just can't query it).
        return True


def _column_exists(table: str, column: str) -> bool:
    try:
        supabase.table(table).select(column).limit(0).execute()
        return True
    except Exception as exc:
        if _is_missing_column_error(exc):
            missing = _column_from_error(exc)
            if missing and missing.lower() != column.lower():
                # PostgREST sometimes reports a different column when several
                # are missing in one query — fall back to assuming this one is
                # missing only when the message clearly names it.
                return True
            return False
        # Table missing or transient error — treat as present so we don't
        # double-report (table-level check already covers that).
        return True


def _probe_table(table: str, expected_cols: List[str]) -> Tuple[bool, List[str]]:
    """Verify a table and ALL its expected columns in a single round trip.

    Returns ``(table_exists, missing_columns)``.

    PostgREST resolves every requested column server-side, so
    ``select("col_a,col_b,...")`` succeeds only when every column exists. This
    replaces the previous behaviour of one network round trip PER COLUMN
    (~105 serial requests across all tables ≈ 30 s on Railway→Supabase) with
    one round trip per table (7 total). The expensive per-column fallback runs
    only for a table that actually reports a missing column, which happens once
    during initial setup rather than on every request.
    """
    projection = ",".join(expected_cols)
    try:
        supabase.table(table).select(projection).limit(1).execute()
        return True, []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return False, []
        if _is_missing_column_error(exc):
            # One or more columns missing — identify exactly which, per column.
            missing = [c for c in expected_cols if not _column_exists(table, c)]
            return True, missing
        # Transient/permission error: assume present so we never false-alarm
        # (a genuinely broken table surfaces when the real query runs).
        log.debug("schema probe for %s inconclusive: %s", table, exc)
        return True, []


def check_schema(*, force: bool = False) -> Dict[str, object]:
    """Return a full snapshot: which tables and columns are missing.

    Happy path issues exactly one Supabase round trip per table (7 total) and
    caches the healthy result for several minutes, so this is safe to call from
    write paths and the worker loop without adding meaningful latency.
    """
    global _cache
    now = time.time()

    if not force and _cache is not None:
        ts, payload = _cache
        ttl = _CACHE_TTL_OK_SEC if payload.get("success") else _CACHE_TTL_BAD_SEC
        if now - ts < ttl:
            return dict(payload)  # type: ignore[arg-type]

    started = time.perf_counter()
    missing_tables: List[str] = []
    missing_columns: Dict[str, List[str]] = {}

    for table, expected_cols in EXPECTED_SCHEMA.items():
        exists, missing_for_table = _probe_table(table, expected_cols)
        if not exists:
            missing_tables.append(table)
            continue
        if missing_for_table:
            missing_columns[table] = missing_for_table

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    success = not missing_tables and not missing_columns
    if elapsed_ms >= 3000.0:
        log.warning("check_schema completed in %.0fms (probed %d tables)", elapsed_ms, len(EXPECTED_SCHEMA))
    else:
        log.info("check_schema completed in %.0fms (success=%s)", elapsed_ms, success)

    snapshot = {
        "success": success,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "required_tables": list(REQUIRED_TABLES),
        "expected_schema": EXPECTED_SCHEMA,
        "message": (
            "All pipeline tables and columns present"
            if success
            else _format_message(missing_tables, missing_columns)
        ),
    }
    _cache = (now, snapshot)
    return snapshot


def _format_message(
    missing_tables: List[str],
    missing_columns: Dict[str, List[str]],
) -> str:
    parts: List[str] = []
    if missing_tables:
        parts.append("Missing tables: " + ", ".join(missing_tables))
    if missing_columns:
        col_desc = "; ".join(
            f"{t}({', '.join(cols)})" for t, cols in missing_columns.items()
        )
        parts.append("Missing columns: " + col_desc)
    return " · ".join(parts) or "Database setup incomplete"


def check_missing_tables(*, force: bool = False) -> List[str]:
    snapshot = check_schema(force=force)
    return list(snapshot.get("missing_tables") or [])  # type: ignore[arg-type]


def check_missing_columns(*, force: bool = False) -> Dict[str, List[str]]:
    snapshot = check_schema(force=force)
    return dict(snapshot.get("missing_columns") or {})  # type: ignore[arg-type]


def database_health(*, force: bool = False) -> Dict[str, object]:
    """Public health payload for /health/database."""
    snapshot = check_schema(force=force)
    return {
        "success": bool(snapshot.get("success")),
        "missing_tables": list(snapshot.get("missing_tables") or []),  # type: ignore[arg-type]
        "missing_columns": dict(snapshot.get("missing_columns") or {}),  # type: ignore[arg-type]
        "required_tables": list(REQUIRED_TABLES),
        "expected_schema": EXPECTED_SCHEMA,
        "message": snapshot.get("message"),
    }


def warm_schema_cache() -> None:
    """Best-effort schema probe to prime the cache at startup.

    Called once from the FastAPI startup hook so the first write / worker claim
    does not pay the probe cost inline. Never raises — startup must not fail if
    Supabase is briefly unreachable.
    """
    try:
        check_schema(force=True)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("warm_schema_cache failed (non-fatal): %s", exc)


def assert_pipeline_ready(*, force: bool = False) -> None:
    from jobs.errors import DatabaseSetupError

    snapshot = check_schema(force=force)
    if snapshot.get("success"):
        return
    raise DatabaseSetupError(
        missing_tables=list(snapshot.get("missing_tables") or []),  # type: ignore[arg-type]
        missing_columns=dict(snapshot.get("missing_columns") or {}),  # type: ignore[arg-type]
    )
