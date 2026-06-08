"""Scan orchestration for the laundry vertical."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.laundry.repository import (
    add_scan_step,
    get_scan_job,
    record_error,
    update_scan_job_progress,
)
from app.laundry.scanners.web import discover_area_listings, scrape_listing_text
from app.laundry.services.pipeline import pipeline_service, split_scan_results
from app.websocket.manager import WebSocketManager

log = structlog.get_logger(__name__)


def channel_for_job(job_id: UUID) -> str:
    return f"laundry-scan:{job_id}"


async def _emit(
    *,
    job_id: Optional[UUID],
    payload: Dict[str, Any],
    ws_manager: Optional[WebSocketManager],
    redis_client: Optional[Redis],
) -> None:
    if not job_id:
        return
    ch = channel_for_job(job_id)
    if ws_manager is not None:
        await ws_manager.publish_redis(ch, payload)
    elif redis_client is not None:
        await redis_client.publish(f"ws:{ch}", json.dumps(payload, default=str))


def _summary(grouped: Dict[str, Any], all_results: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "scanned_count": len(all_results),
        "approved_candidates_count": len(grouped["approved_candidates"]),
        "manual_review_count": len(grouped["manual_review_deals"]),
        "top_deals_count": len(grouped["top_deals"]),
        "rejected_count": len(grouped["rejected_history"]),
    }


async def run_laundry_scan(
    db: AsyncSession,
    *,
    job_id: UUID,
    overrides: Optional[Dict[str, Any]] = None,
    ws_manager: Optional[WebSocketManager] = None,
    redis_client: Optional[Redis] = None,
) -> Dict[str, Any]:
    """Execute a previously-created ``LaundryScanJob`` end-to-end."""
    job = await get_scan_job(db, job_id)
    if not job:
        return {"success": False, "error": "scan job not found"}

    await update_scan_job_progress(db, job, status="running", progress_pct=2.0)
    await _emit(
        job_id=job_id,
        payload={"event": "scan_started", "job_id": str(job_id), "ts": datetime.now(timezone.utc).isoformat()},
        ws_manager=ws_manager,
        redis_client=redis_client,
    )

    results: List[Dict[str, Any]] = []
    listing_urls: List[str] = []

    try:
        if job.search_type == "area_search":
            await add_scan_step(
                db,
                job_id=job.id,
                listing_index=None,
                listing_url=job.search_url,
                step_key="discover_area",
                step_order=0,
                status="running",
            )
            discover = await discover_area_listings(job.search_url or "", limit=job.listing_limit)
            if not discover.get("success"):
                await update_scan_job_progress(
                    db, job, status="failed", error_message=str(discover.get("error"))
                )
                await record_error(
                    db,
                    job_id=job.id,
                    listing_url=job.search_url,
                    error_type="area_discovery",
                    message=str(discover.get("error")),
                    retryable=True,
                )
                await _emit(
                    job_id=job_id,
                    payload={"event": "scan_failed", "stage": "discover_area", "detail": discover},
                    ws_manager=ws_manager,
                    redis_client=redis_client,
                )
                return {"success": False, "error": discover.get("error")}
            listing_urls = list(discover.get("urls") or [])
            await add_scan_step(
                db,
                job_id=job.id,
                listing_index=None,
                listing_url=job.search_url,
                step_key="discover_area",
                step_order=1,
                status="success",
                payload={"urls": listing_urls},
            )
        elif job.search_type == "manual_url":
            listing_urls = [job.search_url] if job.search_url else []
        elif job.search_type == "automatic_scan":
            # The default crawl can be extended via overrides["seed_urls"]; otherwise treat
            # the ``search_url`` field as the seed page.
            seeds = (overrides or {}).get("seed_urls") or ([job.search_url] if job.search_url else [])
            for seed in seeds:
                if not seed:
                    continue
                discover = await discover_area_listings(seed, limit=job.listing_limit)
                if discover.get("success"):
                    listing_urls.extend(discover.get("urls") or [])
            listing_urls = list(dict.fromkeys(listing_urls))[: job.listing_limit]

        await update_scan_job_progress(db, job, listings_total=len(listing_urls), progress_pct=10.0)
        await _emit(
            job_id=job_id,
            payload={
                "event": "listings_discovered",
                "job_id": str(job_id),
                "count": len(listing_urls),
            },
            ws_manager=ws_manager,
            redis_client=redis_client,
        )

        if not listing_urls:
            # Maybe a seed_text job — analyse it as a single listing
            if job.seed_text:
                result = await pipeline_service.analyse_text(
                    db, job.seed_text, overrides=overrides, user_id=job.created_by_user_id
                )
                results.append(result)
            else:
                await update_scan_job_progress(db, job, status="success", progress_pct=100.0)
                return {
                    "success": True,
                    "summary": _summary(split_scan_results([]), []),
                    "all_results": [],
                }
        else:
            done = 0
            failed = 0
            for idx, url in enumerate(listing_urls):
                step_order = idx + 2
                await add_scan_step(
                    db,
                    job_id=job.id,
                    listing_index=idx,
                    listing_url=url,
                    step_key="analyse_listing",
                    step_order=step_order,
                    status="running",
                )
                try:
                    result = await pipeline_service.analyse_url(
                        db,
                        url,
                        overrides=overrides,
                        user_id=job.created_by_user_id,
                    )
                    success = bool(result.get("property_id"))
                    if success:
                        done += 1
                        await add_scan_step(
                            db,
                            job_id=job.id,
                            listing_index=idx,
                            listing_url=url,
                            step_key="analyse_listing",
                            step_order=step_order,
                            status="success",
                            payload={
                                "property_id": result["property_id"],
                                "score": result.get("score", {}).get("score"),
                                "deal_status": result.get("deal_status"),
                            },
                        )
                    else:
                        failed += 1
                        await record_error(
                            db,
                            job_id=job.id,
                            listing_url=url,
                            error_type="pipeline_failed",
                            message=str(result.get("error") or "unknown"),
                            retryable=True,
                        )
                        await add_scan_step(
                            db,
                            job_id=job.id,
                            listing_index=idx,
                            listing_url=url,
                            step_key="analyse_listing",
                            step_order=step_order,
                            status="failed",
                            error_type="pipeline_failed",
                            error_message=str(result.get("error") or "unknown"),
                        )
                    results.append(result)
                except Exception as exc:
                    failed += 1
                    log.exception("laundry.analyse_failed", url=url)
                    await record_error(
                        db,
                        job_id=job.id,
                        listing_url=url,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retryable=True,
                    )
                    await add_scan_step(
                        db,
                        job_id=job.id,
                        listing_index=idx,
                        listing_url=url,
                        step_key="analyse_listing",
                        step_order=step_order,
                        status="failed",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    results.append({"success": False, "error": str(exc), "source_url": url})

                progress = 10 + (idx + 1) / max(len(listing_urls), 1) * 85
                await update_scan_job_progress(
                    db,
                    job,
                    listings_done=done,
                    listings_failed=failed,
                    progress_pct=progress,
                )
                await _emit(
                    job_id=job_id,
                    payload={
                        "event": "listing_processed",
                        "job_id": str(job_id),
                        "index": idx,
                        "url": url,
                        "ok": bool(
                            isinstance(results[-1], dict)
                            and results[-1].get("property_id")
                        ),
                        "deal_status": results[-1].get("deal_status") if isinstance(results[-1], dict) else None,
                        "progress_pct": round(progress, 1),
                    },
                    ws_manager=ws_manager,
                    redis_client=redis_client,
                )

        grouped = split_scan_results(results)
        summary = _summary(grouped, results)

        await update_scan_job_progress(
            db,
            job,
            status="success",
            progress_pct=100.0,
            approved_count=summary["approved_candidates_count"],
            manual_review_count=summary["manual_review_count"],
            rejected_count=summary["rejected_count"],
        )
        await _emit(
            job_id=job_id,
            payload={
                "event": "scan_completed",
                "job_id": str(job_id),
                "summary": summary,
            },
            ws_manager=ws_manager,
            redis_client=redis_client,
        )

        return {
            "success": True,
            "job_id": str(job_id),
            "summary": summary,
            "approved_candidates": grouped["approved_candidates"],
            "manual_review_deals": grouped["manual_review_deals"],
            "rejected_history": grouped["rejected_history"],
            "all_results": results,
        }

    except Exception as exc:  # pragma: no cover — defensive top-level guard
        log.exception("laundry.scan_failed", job_id=str(job_id))
        await record_error(
            db,
            job_id=job.id,
            listing_url=job.search_url,
            error_type=type(exc).__name__,
            message=str(exc),
            retryable=True,
        )
        await update_scan_job_progress(
            db,
            job,
            status="failed",
            error_message=str(exc),
        )
        await _emit(
            job_id=job_id,
            payload={"event": "scan_failed", "error": str(exc)},
            ws_manager=ws_manager,
            redis_client=redis_client,
        )
        return {"success": False, "error": str(exc)}
