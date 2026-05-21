"""CRUD + soft-delete + dedupe helpers for the ``properties`` table.

This module is intentionally defensive: every call is wrapped so a transient
Supabase error never crashes the API. Errors are returned as structured
dicts and logged.

Lifecycle model
---------------
* A property has ``deleted_at IS NULL`` while active.
* ``soft_delete`` sets ``deleted_at``/``deleted_by``/``deletion_reason`` on the
  property AND cascades soft-delete to ``analyses`` and ``generated_memos``
  rows for that property.
* ``restore`` clears ``deleted_at`` on all three tables for that property.
* ``hard_purge`` (admin-only) issues a real DELETE. Use sparingly.

The unique partial index ``idx_properties_dedupe_key_active`` means that
soft-deleted rows do NOT block a fresh insert with the same dedupe key —
so re-scanning a previously-deleted property creates a brand-new row, which
is the right semantics for "the operator deleted this; we don't want it
silently coming back as an update to the dead row".
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger(__name__)


def _supabase():
    """Return the module-scoped Supabase client (lazy import)."""
    from database import supabase
    return supabase


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def write_audit(
    *,
    actor: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> None:
    """Best-effort append to ``public.audit_log``. Never raises."""
    try:
        _supabase().table("audit_log").insert(
            {
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "payload": payload or {},
                "request_id": request_id,
            }
        ).execute()
    except Exception as exc:  # pragma: no cover — diagnostic only
        log.warning("audit_log insert failed: %s", exc)


# ---------------------------------------------------------------------------
# Pipeline insert path (dedup-aware UPSERT)
# ---------------------------------------------------------------------------
def upsert_from_pipeline(
    *,
    property_insert: Dict[str, Any],
    extracted: Dict[str, Any],
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert OR update a property based on its computed dedupe key.

    Returns::

        {
            "success": True,
            "property_id": "...",
            "dedupe_key": "...",
            "dedupe_source": "listing_id" | "address" | "geo" | "fallback",
            "was_duplicate": bool,
            "scan_count": int,
        }

    When ``was_duplicate`` is True the existing row's mutable fields are
    refreshed (score, verdict, classification, description, etc.) and
    ``scan_count`` is incremented. The listing_url, address and dedupe_key
    are NEVER overwritten — those are the identity.

    Falls back to the original INSERT semantics if anything in the dedup
    path fails (network blip, schema migration not yet applied, etc.).
    """
    from jobs.dedupe import compute_dedupe_key, find_existing_active_property

    sb = _supabase()
    now = _now_iso()

    dedupe_key: Optional[str] = None
    dedupe_source: Optional[str] = None
    try:
        dedupe_key, dedupe_source = compute_dedupe_key(
            {**(extracted or {}), "listing_url": property_insert.get("listing_url")}
        )
    except Exception as exc:  # pragma: no cover
        log.warning("compute_dedupe_key failed: %s", exc)

    existing = find_existing_active_property(
        sb,
        dedupe_key=dedupe_key,
        listing_url=property_insert.get("listing_url"),
    )

    if existing:
        update_payload: Dict[str, Any] = {
            "score": property_insert.get("score"),
            "verdict": property_insert.get("verdict"),
            "classification": property_insert.get("classification"),
            "deal_status": property_insert.get("deal_status"),
            "status": property_insert.get("status"),
            "description": property_insert.get("description"),
            "gba_m2": property_insert.get("gba_m2"),
            "asking_price": property_insert.get("asking_price"),
            "asking_rent_month": property_insert.get("asking_rent_month"),
            "rent_per_m2": property_insert.get("rent_per_m2"),
            "last_seen_at": now,
            "last_seen_job_id": job_id,
        }
        if not existing.get("dedupe_key") and dedupe_key:
            update_payload["dedupe_key"] = dedupe_key
        if not existing.get("first_seen_at"):
            update_payload["first_seen_at"] = existing.get("created_at") or now
        if not existing.get("first_seen_job_id") and job_id:
            update_payload["first_seen_job_id"] = job_id
        update_payload["scan_count"] = (existing.get("scan_count") or 1) + 1
        # Drop None values so we don't clobber existing data.
        update_payload = {k: v for k, v in update_payload.items() if v is not None}
        try:
            sb.table("properties").update(update_payload).eq("id", existing["id"]).execute()
        except Exception as exc:
            log.warning("upsert_from_pipeline: update failed (%s); will INSERT instead", exc)
        else:
            return {
                "success": True,
                "property_id": existing["id"],
                "dedupe_key": dedupe_key,
                "dedupe_source": dedupe_source,
                "was_duplicate": True,
                "scan_count": update_payload.get("scan_count", existing.get("scan_count") or 1),
            }

    # Insert path. Augment the payload with dedupe + lifecycle metadata.
    insert_payload = dict(property_insert)
    if dedupe_key:
        insert_payload["dedupe_key"] = dedupe_key
    insert_payload.setdefault("first_seen_at", now)
    insert_payload.setdefault("last_seen_at", now)
    if job_id:
        insert_payload.setdefault("first_seen_job_id", job_id)
        insert_payload.setdefault("last_seen_job_id", job_id)
    insert_payload.setdefault("scan_count", 1)

    try:
        res = sb.table("properties").insert(insert_payload).execute()
        if res.data:
            return {
                "success": True,
                "property_id": res.data[0]["id"],
                "dedupe_key": dedupe_key,
                "dedupe_source": dedupe_source,
                "was_duplicate": False,
                "scan_count": 1,
            }
    except Exception as exc:
        msg = str(exc).lower()
        # If the unique partial index trips it means another scan inserted
        # the same dedupe_key between our SELECT and INSERT. Recover by
        # re-fetching and treating as an update.
        if "dedupe_key" in msg or "duplicate key" in msg or "23505" in msg:
            recovered = find_existing_active_property(
                sb, dedupe_key=dedupe_key, listing_url=property_insert.get("listing_url")
            )
            if recovered:
                return {
                    "success": True,
                    "property_id": recovered["id"],
                    "dedupe_key": dedupe_key,
                    "dedupe_source": dedupe_source,
                    "was_duplicate": True,
                    "scan_count": (recovered.get("scan_count") or 1) + 1,
                    "race_recovered": True,
                }
        log.exception("upsert_from_pipeline insert failed")
        # Final fallback: try the raw insert without dedupe metadata so a
        # missing migration doesn't block the scan.
        try:
            res = sb.table("properties").insert(property_insert).execute()
            if res.data:
                return {
                    "success": True,
                    "property_id": res.data[0]["id"],
                    "dedupe_key": None,
                    "dedupe_source": "fallback_no_schema",
                    "was_duplicate": False,
                    "scan_count": 1,
                }
        except Exception as inner:
            return {"success": False, "error": str(inner), "property_id": None}

    return {"success": False, "error": "supabase returned no rows", "property_id": None}


# ---------------------------------------------------------------------------
# Soft-delete + restore
# ---------------------------------------------------------------------------
def soft_delete(
    property_id: str,
    *,
    deleted_by: Optional[str] = None,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Soft-delete a property and cascade to its analyses + memos.

    Returns ``{"success": bool, "property": {...} | None, "error": str | None}``.
    Never raises — callers should check ``success``.
    """
    sb = _supabase()
    timestamp = _now_iso()

    try:
        existing = (
            sb.table("properties")
            .select("id, deleted_at, address, listing_url")
            .eq("id", property_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:
        log.exception("soft_delete: lookup failed for %s", property_id)
        return {"success": False, "property": None, "error": f"lookup_failed: {exc}"}

    if not existing:
        return {"success": False, "property": None, "error": "not_found"}

    if existing[0].get("deleted_at"):
        return {"success": True, "property": existing[0], "error": None, "already_deleted": True}

    try:
        update_res = (
            sb.table("properties")
            .update(
                {
                    "deleted_at": timestamp,
                    "deleted_by": deleted_by,
                    "deletion_reason": reason,
                }
            )
            .eq("id", property_id)
            .execute()
        )
    except Exception as exc:
        log.exception("soft_delete: update failed for %s", property_id)
        return {"success": False, "property": None, "error": f"update_failed: {exc}"}

    # Cascade soft-delete to children. Failures are non-fatal (audit only).
    for child_table in ("analyses", "generated_memos"):
        try:
            sb.table(child_table).update({"deleted_at": timestamp}).eq("property_id", property_id).execute()
        except Exception as exc:  # pragma: no cover
            log.warning("soft_delete: cascade %s failed: %s", child_table, exc)

    write_audit(
        actor=deleted_by,
        action="property.soft_delete",
        resource_type="property",
        resource_id=property_id,
        payload={"reason": reason},
        request_id=request_id,
    )

    return {
        "success": True,
        "property": (update_res.data or [None])[0] if update_res.data else existing[0],
        "error": None,
        "already_deleted": False,
    }


def restore(
    property_id: str,
    *,
    actor: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Clear ``deleted_at`` on a property and its children."""
    sb = _supabase()
    try:
        existing = (
            sb.table("properties")
            .select("id, deleted_at, dedupe_key")
            .eq("id", property_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:
        return {"success": False, "property": None, "error": f"lookup_failed: {exc}"}

    if not existing:
        return {"success": False, "property": None, "error": "not_found"}

    row = existing[0]
    if not row.get("deleted_at"):
        return {"success": True, "property": row, "error": None, "already_active": True}

    # Restoring may collide with the unique partial index if another property
    # has been created under the same dedupe_key while this one was deleted.
    # In that case we surface a conflict so the operator can resolve manually.
    dedupe_key = row.get("dedupe_key")
    if dedupe_key:
        try:
            conflict = (
                sb.table("properties")
                .select("id")
                .eq("dedupe_key", dedupe_key)
                .is_("deleted_at", "null")
                .neq("id", property_id)
                .limit(1)
                .execute()
                .data
            )
            if conflict:
                return {
                    "success": False,
                    "property": None,
                    "error": "dedupe_key_conflict",
                    "conflicting_property_id": conflict[0]["id"],
                }
        except Exception:
            pass

    try:
        sb.table("properties").update(
            {"deleted_at": None, "deleted_by": None, "deletion_reason": None}
        ).eq("id", property_id).execute()
    except Exception as exc:
        log.exception("restore: update failed for %s", property_id)
        return {"success": False, "property": None, "error": f"update_failed: {exc}"}

    for child_table in ("analyses", "generated_memos"):
        try:
            sb.table(child_table).update({"deleted_at": None}).eq("property_id", property_id).execute()
        except Exception as exc:  # pragma: no cover
            log.warning("restore: cascade %s failed: %s", child_table, exc)

    write_audit(
        actor=actor,
        action="property.restore",
        resource_type="property",
        resource_id=property_id,
        payload=None,
        request_id=request_id,
    )

    return {"success": True, "property": row, "error": None, "already_active": False}


def hard_purge(property_id: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
    """Issue a real DELETE. Cascades via DB FKs where defined."""
    sb = _supabase()
    try:
        sb.table("properties").delete().eq("id", property_id).execute()
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    write_audit(
        actor=actor,
        action="property.hard_purge",
        resource_type="property",
        resource_id=property_id,
        payload=None,
    )
    return {"success": True}


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------
def bulk_soft_delete(
    property_ids: Iterable[str],
    *,
    deleted_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    ids = [pid for pid in property_ids if pid]
    if not ids:
        return {"success": True, "deleted": 0, "errors": []}

    results = {"deleted": 0, "errors": []}
    for pid in ids:
        r = soft_delete(pid, deleted_by=deleted_by, reason=reason)
        if r.get("success"):
            results["deleted"] += 1
        else:
            results["errors"].append({"id": pid, "error": r.get("error")})
    return {"success": True, **results}


# ---------------------------------------------------------------------------
# Listing + filtering
# ---------------------------------------------------------------------------
def list_active(*, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        res = (
            _supabase()
            .table("properties")
            .select("*")
            .is_("deleted_at", "null")
            .order("last_seen_at", desc=True)
            .range(offset, offset + max(1, limit) - 1)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.warning("list_active failed: %s", exc)
        return []


def list_deleted(*, limit: int = 100) -> List[Dict[str, Any]]:
    try:
        res = (
            _supabase()
            .table("properties")
            .select("*")
            .not_.is_("deleted_at", "null")
            .order("deleted_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.warning("list_deleted failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Duplicate detection (post-hoc)
# ---------------------------------------------------------------------------
def find_duplicate_clusters(*, min_cluster_size: int = 2, limit: int = 50) -> List[Dict[str, Any]]:
    """Group active properties by dedupe_key and surface any with >1 row.

    Active properties cannot have duplicate dedupe_keys (the unique partial
    index forbids it), so this normally returns an empty list. If it does
    return clusters, something inserted around the index (e.g. a manual SQL
    insert) and the operator should investigate.

    To detect "true" duplicates that pre-existed the dedupe column, we also
    return rows whose dedupe_key is NULL but whose normalized
    address-or-listing_url matches another row's.
    """
    sb = _supabase()
    try:
        rows = (
            sb.table("properties")
            .select("id, dedupe_key, address, listing_url, score, last_seen_at, deleted_at")
            .is_("deleted_at", "null")
            .order("last_seen_at", desc=True)
            .limit(2000)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        log.warning("find_duplicate_clusters: list failed: %s", exc)
        return []

    from collections import defaultdict
    from jobs.dedupe import compute_dedupe_key

    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = row.get("dedupe_key")
        if not key:
            # Re-compute lazily for legacy rows.
            try:
                key, _src = compute_dedupe_key(row)
            except Exception:
                key = None
        if not key:
            continue
        buckets[key].append(row)

    clusters = [
        {
            "dedupe_key": k,
            "size": len(v),
            "properties": v,
        }
        for k, v in buckets.items()
        if len(v) >= min_cluster_size
    ]
    clusters.sort(key=lambda c: -c["size"])
    return clusters[:limit]


# ---------------------------------------------------------------------------
# Cleanup actions (admin)
# ---------------------------------------------------------------------------
def purge_failed_jobs(*, older_than_days: int = 1, actor: Optional[str] = None) -> Dict[str, Any]:
    """Hard-delete scan_jobs with status in (failed, timeout, cancelled)
    that are older than ``older_than_days``. Children cascade via FK.
    """
    sb = _supabase()
    cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    try:
        res = (
            sb.table("scan_jobs")
            .delete()
            .in_("status", ["failed", "timeout", "cancelled"])
            .lt("created_at", cutoff_iso)
            .execute()
        )
        count = len(res.data or [])
    except Exception as exc:
        return {"success": False, "error": str(exc), "deleted": 0}

    write_audit(
        actor=actor,
        action="admin.purge_failed_jobs",
        resource_type="scan_jobs",
        resource_id=None,
        payload={"older_than_days": older_than_days, "deleted": count},
    )
    return {"success": True, "deleted": count}


def purge_test_data(*, actor: Optional[str] = None) -> Dict[str, Any]:
    """Soft-delete every property flagged ``is_test = TRUE``."""
    sb = _supabase()
    try:
        rows = (
            sb.table("properties")
            .select("id")
            .eq("is_test", True)
            .is_("deleted_at", "null")
            .execute()
            .data
            or []
        )
        ids = [r["id"] for r in rows]
    except Exception as exc:
        return {"success": False, "error": str(exc), "deleted": 0}

    result = bulk_soft_delete(ids, deleted_by=actor, reason="admin_purge_test_data")
    write_audit(
        actor=actor,
        action="admin.purge_test_data",
        resource_type="property",
        resource_id=None,
        payload={"deleted": result.get("deleted", 0)},
    )
    return result


def purge_orphans(*, actor: Optional[str] = None) -> Dict[str, Any]:
    """Delete analyses/memos whose property_id no longer exists.

    NOTE: This walks the analyses table page-by-page and checks each
    property_id. For large datasets prefer an SQL job. Implemented in
    Python for portability.
    """
    sb = _supabase()
    deleted = {"analyses": 0, "generated_memos": 0}
    for table in ("analyses", "generated_memos"):
        try:
            rows = sb.table(table).select("id, property_id").limit(2000).execute().data or []
        except Exception as exc:
            log.warning("purge_orphans: list %s failed: %s", table, exc)
            continue
        if not rows:
            continue
        prop_ids = list({r.get("property_id") for r in rows if r.get("property_id")})
        if not prop_ids:
            continue
        try:
            existing = (
                sb.table("properties")
                .select("id")
                .in_("id", prop_ids)
                .execute()
                .data
                or []
            )
            existing_ids = {r["id"] for r in existing}
        except Exception as exc:
            log.warning("purge_orphans: properties lookup failed: %s", exc)
            continue
        orphan_ids = [r["id"] for r in rows if r.get("property_id") and r["property_id"] not in existing_ids]
        if not orphan_ids:
            continue
        try:
            sb.table(table).delete().in_("id", orphan_ids).execute()
            deleted[table] = len(orphan_ids)
        except Exception as exc:
            log.warning("purge_orphans: delete %s failed: %s", table, exc)

    write_audit(
        actor=actor,
        action="admin.purge_orphans",
        resource_type="multi",
        resource_id=None,
        payload=deleted,
    )
    return {"success": True, "deleted": deleted}


def admin_stats() -> Dict[str, Any]:
    sb = _supabase()
    out: Dict[str, Any] = {}
    try:
        out["properties_active"] = (
            sb.table("properties").select("id", count="exact").is_("deleted_at", "null").execute().count
        )
    except Exception:
        out["properties_active"] = None
    try:
        out["properties_deleted"] = (
            sb.table("properties").select("id", count="exact").not_.is_("deleted_at", "null").execute().count
        )
    except Exception:
        out["properties_deleted"] = None
    try:
        out["properties_test"] = (
            sb.table("properties").select("id", count="exact").eq("is_test", True).execute().count
        )
    except Exception:
        out["properties_test"] = None
    try:
        out["scan_jobs_failed"] = (
            sb.table("scan_jobs")
            .select("id", count="exact")
            .in_("status", ["failed", "timeout"])
            .execute()
            .count
        )
    except Exception:
        out["scan_jobs_failed"] = None
    try:
        out["scan_jobs_active"] = (
            sb.table("scan_jobs")
            .select("id", count="exact")
            .in_("status", ["queued", "running", "pending"])
            .execute()
            .count
        )
    except Exception:
        out["scan_jobs_active"] = None
    return out
