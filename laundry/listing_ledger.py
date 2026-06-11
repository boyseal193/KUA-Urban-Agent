"""Listing trace ledger — every discovered URL must reach a terminal state.

Terminal buckets: processed, failed, skipped.
Invariant: listings_found == processed + failed + skipped
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from laundry import store as laundry_store

log = logging.getLogger("kua.laundry.ledger")

TRACE_DISCOVERED = "DISCOVERED"
TRACE_QUEUED = "QUEUED"
TRACE_CLAIMED = "CLAIMED"
TRACE_PROCESSED = "PROCESSED"
TRACE_FAILED = "FAILED"
TRACE_SKIPPED = "SKIPPED"
TRACE_DEDUPED = "DEDUPED"
TRACE_RETRIED = "RETRIED"


def normalize_listing_url(url: Optional[str]) -> str:
    return (url or "").strip().split("?")[0].rstrip("/").lower()


def trace_event(
    event: str,
    *,
    job_id: str,
    url: Optional[str] = None,
    listing_index: Optional[int] = None,
    **extra: Any,
) -> None:
    parts = [f"pipeline.trace event={event}", f"job_id={job_id}"]
    if listing_index is not None:
        parts.append(f"idx={listing_index}")
    if url:
        parts.append(f"url={url}")
    for key, val in extra.items():
        if val is not None:
            parts.append(f"{key}={val}")
    log.info(" ".join(parts))


@dataclass
class ListingDiagnostics:
    listings_found: int = 0
    listings_queued: int = 0
    listings_processed: int = 0
    listings_failed: int = 0
    listings_skipped: int = 0
    listings_retried: int = 0
    listings_deduped: int = 0
    listings_truncated: int = 0
    listings_resumed: int = 0
    invariant_ok: bool = True
    invariant_delta: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "listings_found": self.listings_found,
            "listings_queued": self.listings_queued,
            "listings_processed": self.listings_processed,
            "listings_failed": self.listings_failed,
            "listings_skipped": self.listings_skipped,
            "listings_retried": self.listings_retried,
            "listings_deduped": self.listings_deduped,
            "listings_truncated": self.listings_truncated,
            "listings_resumed": self.listings_resumed,
            "invariant_ok": self.invariant_ok,
            "invariant_delta": self.invariant_delta,
            "skip_reasons": dict(self.skip_reasons),
        }


@dataclass
class QueueItem:
    url: str
    index: int


def build_listing_queue(
    *,
    job_id: str,
    raw_urls: List[str],
    listing_limit: int,
    completed_indices: Set[int],
    completed_urls: Set[str],
    global_known_urls: Optional[Set[str]] = None,
) -> Tuple[List[QueueItem], ListingDiagnostics, List[Tuple[int, str, str]]]:
    """Build the processing queue and immediately account for non-queued URLs.

    Returns:
        queue items to process,
        running diagnostics,
        skip rows ``(index, url, reason)`` to persist before scraping.
    """
    diag = ListingDiagnostics()
    global_known_urls = global_known_urls or set()
    skip_rows: List[Tuple[int, str, str]] = []
    queue: List[QueueItem] = []
    seen_in_batch: Set[str] = set()
    next_index = 0

    diag.listings_found = len(raw_urls)
    for raw in raw_urls:
        url = (raw or "").strip()
        if not url:
            diag.listings_skipped += 1
            diag.skip_reasons["empty_url"] = diag.skip_reasons.get("empty_url", 0) + 1
            continue
        trace_event(TRACE_DISCOVERED, job_id=job_id, url=url)

        norm = normalize_listing_url(url)
        if norm in seen_in_batch:
            diag.listings_deduped += 1
            diag.listings_skipped += 1
            diag.skip_reasons["duplicate_in_batch"] = diag.skip_reasons.get("duplicate_in_batch", 0) + 1
            trace_event(TRACE_DEDUPED, job_id=job_id, url=url, reason="duplicate_in_batch")
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "duplicate_in_batch"))
            continue
        seen_in_batch.add(norm)

        if norm in completed_urls:
            diag.listings_resumed += 1
            trace_event(TRACE_SKIPPED, job_id=job_id, url=url, reason="already_processed_in_job")
            continue

        if norm in global_known_urls:
            diag.listings_skipped += 1
            diag.skip_reasons["known_listing_url"] = diag.skip_reasons.get("known_listing_url", 0) + 1
            trace_event(TRACE_DEDUPED, job_id=job_id, url=url, reason="known_listing_url")
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "known_listing_url"))
            continue

        if len(queue) >= listing_limit:
            diag.listings_truncated += 1
            diag.listings_skipped += 1
            diag.skip_reasons["listing_limit"] = diag.skip_reasons.get("listing_limit", 0) + 1
            trace_event(TRACE_SKIPPED, job_id=job_id, url=url, reason="listing_limit")
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "listing_limit"))
            continue

        idx = next_index
        next_index += 1
        if idx in completed_indices:
            diag.listings_resumed += 1
            continue

        queue.append(QueueItem(url=url, index=idx))
        diag.listings_queued += 1
        trace_event(TRACE_QUEUED, job_id=job_id, url=url, listing_index=idx)

    return queue, diag, skip_rows


def persist_skip_rows(job_id: str, skip_rows: List[Tuple[int, str, str]]) -> None:
    for idx, url, reason in skip_rows:
        laundry_store.record_listing_result(
            job_id,
            idx,
            listing_url=url,
            status="skipped",
            error_message=reason,
            result={"skip_reason": reason},
        )
        trace_event(TRACE_SKIPPED, job_id=job_id, url=url, listing_index=idx, reason=reason)


def reconcile_diagnostics(
    diag: ListingDiagnostics,
    listing_rows: List[Dict[str, Any]],
) -> ListingDiagnostics:
    processed = failed = skipped = 0
    for row in listing_rows:
        status = (row.get("status") or "").lower()
        if status in ("success", "extraction_failed") or row.get("property_id"):
            processed += 1
        elif status == "failed":
            failed += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

    diag.listings_processed = processed
    diag.listings_failed = failed
    diag.listings_skipped = skipped
    accounted = processed + failed + skipped
    diag.invariant_delta = diag.listings_found - accounted
    diag.invariant_ok = diag.invariant_delta == 0
    if not diag.invariant_ok:
        log.warning(
            "pipeline.invariant mismatch job_id rows=%s found=%s processed=%s failed=%s skipped=%s delta=%s",
            len(listing_rows),
            diag.listings_found,
            processed,
            failed,
            skipped,
            diag.invariant_delta,
        )
    return diag
