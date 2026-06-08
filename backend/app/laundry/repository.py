"""
Database access for the laundry vertical.

Every helper is async, scoped to the laundry tables only, and never touches
the storage tables. The repository exposes the small set of operations the
pipeline + API endpoints need; complex queries (admin reports, exports) live
in :mod:`app.laundry.services`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.laundry.models import (
    LaundryAnalysis,
    LaundryAuditLog,
    LaundryDuplicate,
    LaundryError,
    LaundryExport,
    LaundryGeneratedMemo,
    LaundryProperty,
    LaundryScanJob,
    LaundryScanStep,
    LaundrySettings,
)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


async def get_property(
    db: AsyncSession,
    property_id: UUID,
    *,
    include_deleted: bool = False,
) -> Optional[LaundryProperty]:
    q = select(LaundryProperty).where(LaundryProperty.id == property_id)
    if not include_deleted:
        q = q.where(LaundryProperty.deleted_at.is_(None))
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def get_property_by_dedupe_key(
    db: AsyncSession,
    dedupe_key: str,
    *,
    include_deleted: bool = False,
) -> Optional[LaundryProperty]:
    q = select(LaundryProperty).where(LaundryProperty.dedupe_key == dedupe_key)
    if not include_deleted:
        q = q.where(LaundryProperty.deleted_at.is_(None))
    r = await db.execute(q.order_by(LaundryProperty.created_at.desc()).limit(1))
    return r.scalar_one_or_none()


async def get_latest_analysis(
    db: AsyncSession,
    property_id: UUID,
) -> Optional[LaundryAnalysis]:
    q = (
        select(LaundryAnalysis)
        .where(
            LaundryAnalysis.property_id == property_id,
            LaundryAnalysis.deleted_at.is_(None),
        )
        .order_by(LaundryAnalysis.created_at.desc())
        .limit(1)
    )
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def get_property_with_analysis(
    db: AsyncSession,
    property_id: UUID,
) -> Tuple[Optional[LaundryProperty], Optional[LaundryAnalysis]]:
    prop = await get_property(db, property_id)
    if not prop:
        return None, None
    return prop, await get_latest_analysis(db, property_id)


async def list_properties(
    db: AsyncSession,
    *,
    deal_status: Optional[str] = None,
    deal_statuses: Optional[Iterable[str]] = None,
    order_by_score: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[LaundryProperty]:
    q = select(LaundryProperty).where(LaundryProperty.deleted_at.is_(None))
    if deal_status:
        q = q.where(LaundryProperty.deal_status == deal_status)
    if deal_statuses:
        q = q.where(LaundryProperty.deal_status.in_(list(deal_statuses)))
    if order_by_score:
        q = q.order_by(LaundryProperty.score.desc().nulls_last())
    else:
        q = q.order_by(LaundryProperty.created_at.desc())
    q = q.limit(limit).offset(offset)
    r = await db.execute(q)
    return list(r.scalars())


async def list_deleted_properties(
    db: AsyncSession, *, limit: int = 100
) -> List[LaundryProperty]:
    q = (
        select(LaundryProperty)
        .where(LaundryProperty.deleted_at.is_not(None))
        .order_by(LaundryProperty.deleted_at.desc())
        .limit(limit)
    )
    r = await db.execute(q)
    return list(r.scalars())


async def soft_delete_property(
    db: AsyncSession,
    property_id: UUID,
    *,
    reason: Optional[str] = None,
) -> Optional[LaundryProperty]:
    prop = await get_property(db, property_id, include_deleted=True)
    if not prop:
        return None
    if prop.deleted_at:
        return prop
    prop.deleted_at = datetime.now(timezone.utc)
    prop.deletion_reason = reason
    prop.deal_status = "deleted"
    # Also soft-delete analyses + memos so the operator listing stays clean
    await db.execute(
        update(LaundryAnalysis)
        .where(LaundryAnalysis.property_id == property_id)
        .values(deleted_at=datetime.now(timezone.utc))
    )
    return prop


async def restore_property(db: AsyncSession, property_id: UUID) -> Optional[LaundryProperty]:
    prop = await get_property(db, property_id, include_deleted=True)
    if not prop or not prop.deleted_at:
        return prop
    prop.deleted_at = None
    prop.deletion_reason = None
    prop.deal_status = "manual_review"
    await db.execute(
        update(LaundryAnalysis)
        .where(LaundryAnalysis.property_id == property_id)
        .values(deleted_at=None)
    )
    return prop


async def kpi_counters(db: AsyncSession) -> Dict[str, Any]:
    base = select(LaundryProperty).where(LaundryProperty.deleted_at.is_(None))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    approved = (
        await db.execute(
            select(func.count()).select_from(
                base.where(LaundryProperty.deal_status == "approved_candidate").subquery()
            )
        )
    ).scalar_one()
    review = (
        await db.execute(
            select(func.count()).select_from(
                base.where(LaundryProperty.deal_status == "manual_review").subquery()
            )
        )
    ).scalar_one()
    rejected = (
        await db.execute(
            select(func.count()).select_from(
                base.where(LaundryProperty.deal_status == "rejected").subquery()
            )
        )
    ).scalar_one()
    avg_score = (
        await db.execute(select(func.avg(LaundryProperty.score)).where(LaundryProperty.deleted_at.is_(None)))
    ).scalar()

    return {
        "total_scanned": int(total),
        "approved_count": int(approved),
        "manual_review_count": int(review),
        "rejected_count": int(rejected),
        "approval_rate": round((approved / total), 4) if total else 0,
        "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
    }


# ---------------------------------------------------------------------------
# Scan jobs + steps
# ---------------------------------------------------------------------------


async def create_scan_job(
    db: AsyncSession,
    *,
    user_id: Optional[UUID],
    search_type: str,
    property_type: Optional[str],
    acquisition_type: Optional[str],
    search_url: Optional[str],
    seed_text: Optional[str],
    filters: Dict[str, Any],
    overrides: Dict[str, Any],
    listing_limit: int,
    job_type: str = "area_search",
) -> LaundryScanJob:
    job = LaundryScanJob(
        created_by_user_id=user_id,
        job_type=job_type,
        property_type=property_type,
        acquisition_type=acquisition_type,
        search_type=search_type,
        search_url=search_url,
        seed_text=seed_text,
        filters=filters or {},
        overrides=overrides or {},
        listing_limit=listing_limit,
        status="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def get_scan_job(db: AsyncSession, job_id: UUID) -> Optional[LaundryScanJob]:
    q = select(LaundryScanJob).where(LaundryScanJob.id == job_id)
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def list_scan_jobs(
    db: AsyncSession, *, limit: int = 50
) -> List[LaundryScanJob]:
    q = (
        select(LaundryScanJob)
        .order_by(LaundryScanJob.created_at.desc())
        .limit(limit)
    )
    r = await db.execute(q)
    return list(r.scalars())


async def list_scan_steps(
    db: AsyncSession, job_id: UUID, *, limit: int = 500
) -> List[LaundryScanStep]:
    q = (
        select(LaundryScanStep)
        .where(LaundryScanStep.job_id == job_id)
        .order_by(LaundryScanStep.step_order.asc())
        .limit(limit)
    )
    r = await db.execute(q)
    return list(r.scalars())


async def add_scan_step(
    db: AsyncSession,
    *,
    job_id: UUID,
    listing_index: Optional[int],
    listing_url: Optional[str],
    step_key: str,
    step_order: int,
    status: str = "pending",
    payload: Optional[Dict[str, Any]] = None,
    attempt: int = 1,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> LaundryScanStep:
    step = LaundryScanStep(
        job_id=job_id,
        listing_index=listing_index,
        listing_url=listing_url,
        step_key=step_key,
        step_order=step_order,
        status=status,
        payload=payload or {},
        attempt=attempt,
        error_type=error_type,
        error_message=error_message,
        started_at=datetime.now(timezone.utc) if status == "running" else None,
        finished_at=datetime.now(timezone.utc) if status in ("success", "failed", "skipped") else None,
    )
    db.add(step)
    await db.flush()
    return step


async def update_scan_job_progress(
    db: AsyncSession,
    job: LaundryScanJob,
    *,
    status: Optional[str] = None,
    listings_total: Optional[int] = None,
    listings_done: Optional[int] = None,
    listings_failed: Optional[int] = None,
    approved_count: Optional[int] = None,
    manual_review_count: Optional[int] = None,
    rejected_count: Optional[int] = None,
    error_message: Optional[str] = None,
    excel_path: Optional[str] = None,
    progress_pct: Optional[float] = None,
) -> LaundryScanJob:
    if status is not None:
        job.status = status
        if status == "running" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        if status in ("success", "completed", "failed", "cancelled", "timeout"):
            job.finished_at = datetime.now(timezone.utc)
    if listings_total is not None:
        job.listings_total = listings_total
    if listings_done is not None:
        job.listings_done = listings_done
    if listings_failed is not None:
        job.listings_failed = listings_failed
    if approved_count is not None:
        job.approved_count = approved_count
    if manual_review_count is not None:
        job.manual_review_count = manual_review_count
    if rejected_count is not None:
        job.rejected_count = rejected_count
    if error_message is not None:
        job.error_message = error_message
    if excel_path is not None:
        job.excel_path = excel_path
    if progress_pct is not None:
        job.progress_pct = max(0.0, min(progress_pct, 100.0))
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Memos / exports / audit / errors / duplicates
# ---------------------------------------------------------------------------


async def save_memo(
    db: AsyncSession,
    *,
    property_id: UUID,
    analysis_id: Optional[UUID],
    markdown: str,
    polished: bool = False,
    kind: str = "ic_memo",
) -> LaundryGeneratedMemo:
    memo = LaundryGeneratedMemo(
        property_id=property_id,
        analysis_id=analysis_id,
        markdown=markdown,
        polished=polished,
        kind=kind,
    )
    db.add(memo)
    await db.flush()
    return memo


async def add_export(
    db: AsyncSession,
    *,
    fmt: str,
    file_path: str,
    size_bytes: int,
    user_id: Optional[UUID] = None,
    job_id: Optional[UUID] = None,
    property_id: Optional[UUID] = None,
) -> LaundryExport:
    record = LaundryExport(
        format=fmt,
        file_path=file_path,
        size_bytes=size_bytes,
        created_by_user_id=user_id,
        job_id=job_id,
        property_id=property_id,
    )
    db.add(record)
    await db.flush()
    return record


async def list_exports(db: AsyncSession, *, limit: int = 100) -> List[LaundryExport]:
    q = (
        select(LaundryExport)
        .order_by(LaundryExport.created_at.desc())
        .limit(limit)
    )
    r = await db.execute(q)
    return list(r.scalars())


async def audit(
    db: AsyncSession,
    *,
    actor_user_id: Optional[UUID],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> LaundryAuditLog:
    rec = LaundryAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    db.add(rec)
    await db.flush()
    return rec


async def record_duplicate(db: AsyncSession, *, dedupe_key: str, property_id: UUID) -> None:
    if not dedupe_key:
        return
    existing = await db.execute(
        select(LaundryDuplicate).where(
            LaundryDuplicate.dedupe_key == dedupe_key,
            LaundryDuplicate.property_id == property_id,
        )
    )
    if existing.scalar_one_or_none():
        return
    db.add(LaundryDuplicate(dedupe_key=dedupe_key, property_id=property_id))


async def duplicate_clusters(db: AsyncSession, *, limit: int = 50) -> List[Dict[str, Any]]:
    q = (
        select(
            LaundryDuplicate.dedupe_key.label("dedupe_key"),
            func.count(LaundryDuplicate.id).label("size"),
        )
        .group_by(LaundryDuplicate.dedupe_key)
        .having(func.count(LaundryDuplicate.id) > 1)
        .order_by(func.count(LaundryDuplicate.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    clusters: List[Dict[str, Any]] = []
    for r in rows:
        members = (
            await db.execute(
                select(LaundryDuplicate.property_id).where(
                    LaundryDuplicate.dedupe_key == r.dedupe_key
                )
            )
        ).scalars().all()
        props = (
            await db.execute(
                select(LaundryProperty).where(LaundryProperty.id.in_(list(members)))
            )
        ).scalars().all()
        clusters.append(
            {
                "dedupe_key": r.dedupe_key,
                "size": r.size,
                "properties": [
                    {
                        "id": str(p.id),
                        "address": p.address,
                        "listing_url": p.listing_url,
                        "score": p.score,
                        "deal_status": p.deal_status,
                    }
                    for p in props
                ],
            }
        )
    return clusters


async def record_error(
    db: AsyncSession,
    *,
    job_id: Optional[UUID],
    listing_url: Optional[str],
    error_type: str,
    message: str,
    retryable: bool = True,
    attempt: int = 1,
    traceback: Optional[str] = None,
) -> LaundryError:
    err = LaundryError(
        job_id=job_id,
        listing_url=listing_url,
        error_type=error_type,
        message=message,
        retryable=retryable,
        attempt=attempt,
        traceback=traceback,
    )
    db.add(err)
    await db.flush()
    return err


# ---------------------------------------------------------------------------
# Settings (assumption overrides)
# ---------------------------------------------------------------------------


async def get_settings(db: AsyncSession, *, name: str = "default") -> Optional[LaundrySettings]:
    r = await db.execute(select(LaundrySettings).where(LaundrySettings.name == name))
    return r.scalar_one_or_none()


async def upsert_settings(
    db: AsyncSession,
    *,
    name: str = "default",
    overrides: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> LaundrySettings:
    existing = await get_settings(db, name=name)
    if existing:
        if overrides is not None:
            existing.overrides = overrides
        if notes is not None:
            existing.notes = notes
        await db.flush()
        return existing
    record = LaundrySettings(name=name, overrides=overrides or {}, notes=notes)
    db.add(record)
    await db.flush()
    return record


async def purge_test_data(db: AsyncSession) -> int:
    """Hard-delete obvious test rows (listings flagged source='test')."""
    deleted = 0
    rows = (
        await db.execute(select(LaundryProperty).where(LaundryProperty.source == "test"))
    ).scalars().all()
    for row in rows:
        await db.execute(delete(LaundryProperty).where(LaundryProperty.id == row.id))
        deleted += 1
    return deleted
