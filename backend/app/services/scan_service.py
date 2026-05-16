"""High-level scan orchestration (API sync path + ARQ worker with Redis fan-out)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.exports.excel_service import export_scan_excel
from app.repositories.scan_repository import (
    add_scan_history_item,
    get_scan,
)
from app.scanners.idealista import scrape_idealista_search_urls
from app.services.pipeline_service import pipeline_service, split_scan_results
from app.websocket.manager import WebSocketManager, channel_scan

log = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def _emit_scan_event(
    *,
    scan_id: Optional[UUID],
    message: Dict[str, Any],
    ws_manager: Optional[WebSocketManager],
    redis_client: Optional[Redis],
) -> None:
    """Deliver live JSON to WebSocket subscribers (process-local or via Redis)."""
    if not scan_id:
        return
    channel = channel_scan(scan_id)
    if ws_manager is not None:
        await ws_manager.publish_redis(channel, message)
    elif redis_client is not None:
        await redis_client.publish(f"ws:{channel}", json.dumps(message, default=str))


async def run_idealista_scan_sync(
    db: AsyncSession,
    *,
    search_url: str,
    limit: int,
    generate_excel: bool,
    filters_used: Dict[str, Any],
    user_id: Optional[UUID] = None,
    ws_manager: Optional[WebSocketManager] = None,
    redis_client: Optional[Redis] = None,
    scan_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Full Idealista search scrape → per-URL underwriting.

    When ``scan_id`` is set, the `scans` row is updated and live events are emitted.
    """
    _ = user_id  # reserved for audit fields on `Scan`
    if not search_url:
        return {"success": False, "error": "search_url is required"}

    scan_row = None
    if scan_id:
        scan_row = await get_scan(db, scan_id)
        if scan_row:
            scan_row.status = "running"
            scan_row.filters = filters_used or scan_row.filters
            await db.flush()

    scraped = scrape_idealista_search_urls(search_url, limit=limit)
    if not scraped.get("success"):
        if scan_row:
            scan_row.status = "failed"
            scan_row.error_message = str(scraped.get("error", "scrape failed"))
            await db.flush()
        await _emit_scan_event(
            scan_id=scan_id,
            message={
                "event": "scan_failed",
                "reason": "search_scrape",
                "detail": scraped,
            },
            ws_manager=ws_manager,
            redis_client=redis_client,
        )
        return scraped

    urls: List[str] = scraped.get("urls", [])
    results: List[Dict[str, Any]] = []

    for idx, url in enumerate(urls):
        try:
            result = await pipeline_service.analyse_url(db, url)
            if isinstance(result, dict):
                result["source_url"] = url
            results.append(result)
            if scan_row:
                scan_row.scanned_count = idx + 1
                await db.flush()
            await _emit_scan_event(
                scan_id=scan_id,
                message={
                    "event": "listing_processed",
                    "index": idx,
                    "url": url,
                    "success": bool(
                        isinstance(result, dict) and result.get("property_id")
                    ),
                    "property_id": result.get("property_id")
                    if isinstance(result, dict)
                    else None,
                },
                ws_manager=ws_manager,
                redis_client=redis_client,
            )
            if scan_row:
                st = (
                    "ok"
                    if isinstance(result, dict) and result.get("property_id")
                    else "failed"
                )
                await add_scan_history_item(
                    db,
                    scan_id=scan_row.id,
                    url=url,
                    order_index=idx,
                    status=st,
                    payload=result
                    if isinstance(result, dict)
                    else {"error": str(result)},
                )
        except Exception as e:
            log.exception("scan.url_failed", url=url)
            err = {"url": url, "success": False, "error": str(e)}
            results.append(err)
            if scan_row:
                await add_scan_history_item(
                    db,
                    scan_id=scan_row.id,
                    url=url,
                    order_index=idx,
                    status="error",
                    payload=err,
                )
            await _emit_scan_event(
                scan_id=scan_id,
                message={
                    "event": "listing_error",
                    "index": idx,
                    "url": url,
                    "error": str(e),
                },
                ws_manager=ws_manager,
                redis_client=redis_client,
            )

    grouped = split_scan_results(results)
    response: Dict[str, Any] = {
        "success": True,
        "search_url_used": search_url,
        "scanned_count": len(results),
        "approved_candidates_count": len(grouped["approved_candidates"]),
        "manual_review_count": len(grouped["manual_review_deals"]),
        "top_deals_count": len(grouped["top_deals"]),
        "rejected_count": len(grouped["rejected_history"]),
        "approved_candidates": grouped["approved_candidates"],
        "manual_review_deals": grouped["manual_review_deals"],
        "top_deals": grouped["top_deals"],
        "rejected_history": grouped["rejected_history"],
        "all_results": results,
        "excel_export_generated": False,
        "filters_used": filters_used,
    }

    if generate_excel:
        try:
            path = export_scan_excel(
                successful_results=grouped["successful_results"],
                grouped=grouped,
                search_url=search_url,
                filters_used=filters_used,
            )
            response["excel_export_generated"] = True
            response["excel_export_path"] = path
            if scan_row:
                scan_row.excel_path = path
                await db.flush()
        except Exception as e:
            response["excel_export_generated"] = False
            response["excel_export_error"] = str(e)

    if scan_row:
        scan_row.status = "completed"
        await db.flush()
        await _emit_scan_event(
            scan_id=scan_id,
            message={
                "event": "scan_completed",
                "summary": {
                    k: response[k]
                    for k in response
                    if k.endswith("_count")
                },
            },
            ws_manager=ws_manager,
            redis_client=redis_client,
        )

    return response
