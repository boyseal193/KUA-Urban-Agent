"""Database CRUD for the ``export_jobs`` table.

Every operation is wrapped in try/except: a missing table or a Supabase
outage MUST NOT crash the export endpoints — they degrade to
generate-on-demand mode and the scan worker keeps running.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database import supabase
from jobs.exports import EXTENSION_BY_FORMAT, MIME_BY_FORMAT, filename_for

log = logging.getLogger("kua.exports.store")

EXPORT_STATUS_PENDING = "pending"
EXPORT_STATUS_READY = "ready"
EXPORT_STATUS_FAILED = "failed"


def _safe_execute(fn):
    try:
        return fn()
    except Exception as exc:
        log.info("export_jobs operation failed: %s", exc)
        return None


def record_export(
    job_id: str,
    export_type: str,
    *,
    file_path: Optional[str],
    file_name: Optional[str] = None,
    size_bytes: int = 0,
    status: str = EXPORT_STATUS_READY,
    error_message: Optional[str] = None,
    job: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Upsert a single export_jobs row by (job_id, export_type). Safe."""
    if not job_id or not export_type:
        return None
    mime = MIME_BY_FORMAT.get(export_type)
    if not file_name and job:
        try:
            file_name = filename_for(job, export_type)
        except Exception:
            file_name = f"{export_type}.{EXTENSION_BY_FORMAT.get(export_type, 'bin')}"
    payload = {
        "job_id": job_id,
        "export_type": export_type,
        "file_path": file_path,
        "file_name": file_name,
        "mime_type": mime,
        "size_bytes": int(size_bytes or 0),
        "status": status,
        "error_message": (error_message or None),
    }
    res = _safe_execute(
        lambda: supabase.table("export_jobs")
        .upsert(payload, on_conflict="job_id,export_type")
        .execute()
    )
    if res is None or not getattr(res, "data", None):
        return None
    rows = res.data or []
    return rows[0] if rows else None


def list_exports(job_id: str) -> List[Dict[str, Any]]:
    if not job_id:
        return []
    res = _safe_execute(
        lambda: supabase.table("export_jobs")
        .select("*")
        .eq("job_id", job_id)
        .order("export_type")
        .execute()
    )
    if res is None:
        return []
    return list(res.data or [])


def get_export(job_id: str, export_type: str) -> Optional[Dict[str, Any]]:
    if not job_id or not export_type:
        return None
    res = _safe_execute(
        lambda: supabase.table("export_jobs")
        .select("*")
        .eq("job_id", job_id)
        .eq("export_type", export_type)
        .limit(1)
        .execute()
    )
    if res is None or not res.data:
        return None
    return res.data[0]


def increment_download_count(job_id: str, export_type: str) -> None:
    """Best-effort increment of the download counter."""
    row = get_export(job_id, export_type)
    if not row:
        return
    new_count = int(row.get("download_count") or 0) + 1
    _safe_execute(
        lambda: supabase.table("export_jobs")
        .update({"download_count": new_count})
        .eq("id", row["id"])
        .execute()
    )


def mark_failed(job_id: str, export_type: str, error_message: str) -> None:
    record_export(
        job_id,
        export_type,
        file_path=None,
        size_bytes=0,
        status=EXPORT_STATUS_FAILED,
        error_message=error_message,
    )
