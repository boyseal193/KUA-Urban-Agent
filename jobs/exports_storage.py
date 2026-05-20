"""Optional Supabase Storage backend for cached scan exports.

Design
------
We do NOT require a Supabase Storage bucket to be configured. If the
``SUPABASE_EXPORTS_BUCKET`` env var is unset (or any storage call fails),
the export endpoints regenerate from the database on every request. This
keeps the system functional out-of-the-box and treats persistence as a
performance optimisation.

When ``SUPABASE_EXPORTS_BUCKET`` IS set, we:
  * upload each generated artifact under ``<job_id>/<filename>``
  * download bytes on subsequent requests instead of regenerating
  * sign URLs on demand for clients that want a direct download link

Every operation is wrapped in try/except — a storage error never breaks
the scan or the download. The caller falls back to regenerating from DB.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from database import supabase
from jobs.exports import EXTENSION_BY_FORMAT, MIME_BY_FORMAT, filename_for

log = logging.getLogger("kua.exports.storage")


def bucket_name() -> Optional[str]:
    name = os.getenv("SUPABASE_EXPORTS_BUCKET")
    if name and name.strip():
        return name.strip()
    return None


def is_enabled() -> bool:
    return bucket_name() is not None


def _storage_client():
    bucket = bucket_name()
    if not bucket:
        return None
    try:
        return supabase.storage.from_(bucket)
    except Exception as exc:
        log.warning("Could not access Supabase storage bucket %s: %s", bucket, exc)
        return None


def object_path(job_id: str, fmt: str) -> str:
    ext = EXTENSION_BY_FORMAT.get(fmt, "bin")
    return f"{job_id}/{fmt}.{ext}"


def upload_bytes(job_id: str, fmt: str, data: bytes, *, job: Optional[dict] = None) -> Optional[str]:
    """Upload artifact bytes. Returns ``"bucket/path"`` on success, ``None`` otherwise."""
    bucket = bucket_name()
    client = _storage_client()
    if not bucket or client is None:
        return None
    path = object_path(job_id, fmt)
    mime = MIME_BY_FORMAT.get(fmt, "application/octet-stream")
    file_options = {
        "content-type": mime,
        "upsert": "true",
        "cache-control": "private, max-age=3600",
    }
    if job is not None:
        # Add a friendly file-name disposition for direct downloads.
        try:
            disposition = f'attachment; filename="{filename_for(job, fmt)}"'
            file_options["content-disposition"] = disposition
        except Exception:
            pass
    try:
        client.upload(path=path, file=data, file_options=file_options)
        return f"{bucket}/{path}"
    except Exception as exc:
        log.warning("storage upload failed for %s: %s", path, exc)
        return None


def download_bytes(file_path: str) -> Optional[bytes]:
    """Download an artifact previously uploaded. Returns ``None`` on any error."""
    if not file_path:
        return None
    bucket = bucket_name()
    client = _storage_client()
    if not bucket or client is None:
        return None
    # file_path may be either "bucket/key" or just "key".
    key = file_path.split("/", 1)[1] if file_path.startswith(f"{bucket}/") else file_path
    try:
        data = client.download(key)
        return bytes(data) if data is not None else None
    except Exception as exc:
        log.info("storage download miss for %s: %s", key, exc)
        return None


def signed_url(file_path: str, expires_seconds: int = 3600) -> Optional[str]:
    bucket = bucket_name()
    client = _storage_client()
    if not bucket or client is None:
        return None
    key = file_path.split("/", 1)[1] if file_path.startswith(f"{bucket}/") else file_path
    try:
        resp = client.create_signed_url(key, expires_seconds)
        if isinstance(resp, dict):
            return resp.get("signedURL") or resp.get("signed_url") or resp.get("url")
        return None
    except Exception as exc:
        log.info("signed url failed for %s: %s", key, exc)
        return None
