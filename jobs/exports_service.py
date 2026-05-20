"""High-level service tying together export builders, storage, and DB.

The worker calls :func:`generate_all_exports` after a successful scan to
warm the cache. The HTTP endpoints call :func:`get_or_generate` which
serves from cache if available, otherwise regenerates from DB rows.

Any partial failure (e.g. storage upload error, schema-not-ready) is
caught and logged, then the call falls back to regenerate-on-demand
behaviour. A failed export NEVER cascades into a failed scan.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from jobs import exports
from jobs import exports_storage
from jobs import exports_store

log = logging.getLogger("kua.exports.service")

# Order matters for the ZIP package: zip last so it can reuse the others
# if we ever decide to assemble it from already-rendered bytes.
ALL_FORMATS: Tuple[str, ...] = ("excel", "csv", "json", "memo", "zip")


def _load_job_context(job_id: str) -> Optional[Dict[str, Any]]:
    """Return ``{job, listings, logs, errors}`` for an export, or None on error."""
    try:
        from jobs import store
    except Exception as exc:
        log.error("export context load failed (cannot import store): %s", exc)
        return None
    try:
        job = store.get_job(job_id)
    except KeyError:
        return None
    except Exception as exc:
        log.warning("export context: get_job failed for %s: %s", job_id, exc)
        return None
    try:
        listings = store.get_listing_results(job_id)
    except Exception as exc:
        log.warning("export context: get_listing_results failed: %s", exc)
        listings = []
    try:
        logs = store.get_logs(job_id, limit=200)
    except Exception:
        logs = []
    try:
        errors = store.get_errors(job_id, limit=200)
    except Exception:
        errors = []
    return {"job": job, "listings": listings, "logs": logs, "errors": errors}


def _build_bytes(fmt: str, ctx: Dict[str, Any]) -> bytes:
    return exports.build_export(
        fmt,
        ctx.get("job") or {},
        ctx.get("listings") or [],
        logs=ctx.get("logs"),
        errors=ctx.get("errors"),
    )


def generate_one(
    job_id: str,
    fmt: str,
    *,
    ctx: Optional[Dict[str, Any]] = None,
    persist: bool = True,
) -> Optional[bytes]:
    """Build the bytes for one format. If ``persist`` is True, also upload
    to Supabase storage and record metadata in ``export_jobs``.

    Returns the raw bytes on success, ``None`` on unrecoverable error.
    """
    if fmt not in ALL_FORMATS:
        return None
    if ctx is None:
        ctx = _load_job_context(job_id)
    if ctx is None:
        return None
    try:
        data = _build_bytes(fmt, ctx)
    except Exception as exc:
        log.exception("export build failed (fmt=%s, job=%s): %s", fmt, job_id, exc)
        if persist:
            exports_store.mark_failed(job_id, fmt, str(exc)[:500])
        return None

    if persist:
        try:
            file_path = exports_storage.upload_bytes(job_id, fmt, data, job=ctx.get("job"))
            exports_store.record_export(
                job_id,
                fmt,
                file_path=file_path,
                size_bytes=len(data),
                status=exports_store.EXPORT_STATUS_READY,
                job=ctx.get("job"),
            )
        except Exception as exc:
            log.warning("export persist failed (fmt=%s): %s", fmt, exc)

    return data


def generate_all_exports(job_id: str) -> Dict[str, bool]:
    """Generate every export format for a job. Returns ``{format: ok}``.

    Designed to be called from the worker's ``export_artifacts`` step. A
    single format failing does NOT abort the others — the rest still run.
    """
    ctx = _load_job_context(job_id)
    if ctx is None:
        return {fmt: False for fmt in ALL_FORMATS}

    results: Dict[str, bool] = {}
    for fmt in ALL_FORMATS:
        try:
            data = generate_one(job_id, fmt, ctx=ctx, persist=True)
            results[fmt] = data is not None
        except Exception as exc:
            log.exception("export auto-generate crash (fmt=%s): %s", fmt, exc)
            results[fmt] = False
    return results


def get_or_generate(
    job_id: str,
    fmt: str,
) -> Optional[Tuple[bytes, str, str]]:
    """Return ``(bytes, mime, filename)`` for an export, or ``None``.

    Strategy:
      1. If the row exists in ``export_jobs`` AND a cached file exists in
         Supabase Storage, return that.
      2. Otherwise regenerate from DB rows on the fly, persist if storage
         is configured, and return the freshly built bytes.
    """
    if fmt not in ALL_FORMATS:
        return None

    mime = exports.MIME_BY_FORMAT.get(fmt, "application/octet-stream")
    cached_row = exports_store.get_export(job_id, fmt)
    cached_path = (cached_row or {}).get("file_path") if cached_row else None

    if cached_path and exports_storage.is_enabled():
        cached_bytes = exports_storage.download_bytes(cached_path)
        if cached_bytes:
            filename = (cached_row or {}).get("file_name") or exports.filename_for(
                {"id": job_id}, fmt
            )
            exports_store.increment_download_count(job_id, fmt)
            return cached_bytes, mime, filename

    # Cache miss → regenerate from DB.
    ctx = _load_job_context(job_id)
    if ctx is None:
        return None
    data = generate_one(job_id, fmt, ctx=ctx, persist=True)
    if data is None:
        return None
    filename = exports.filename_for(ctx.get("job") or {"id": job_id}, fmt)
    exports_store.increment_download_count(job_id, fmt)
    return data, mime, filename
