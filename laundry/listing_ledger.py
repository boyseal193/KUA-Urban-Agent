"""Listing trace ledger — every discovered URL must reach a terminal state.

Terminal buckets: success, duplicate, filtered_out, failed (+ extraction_failed).
Invariant: discovered_count == success + duplicate + filtered_out + failed
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from laundry import store as laundry_store
from laundry.listing_outcomes import (
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_FILTERED_OUT,
    STATUS_SUCCESS,
    accounting_bucket,
    build_outcome,
    merge_pipeline_result,
    resolve_legacy_skip,
)

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
    requested_limit: int = 0
    effective_limit: int = 0
    discovered_count: int = 0
    source_available_count: Optional[int] = None
    success_count: int = 0
    duplicate_count: int = 0
    filtered_out_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
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
            "requested_limit": self.requested_limit,
            "effective_limit": self.effective_limit,
            "discovered_count": self.discovered_count,
            "source_available_count": self.source_available_count,
            "success_count": self.success_count,
            "duplicate_count": self.duplicate_count,
            "filtered_out_count": self.filtered_out_count,
            "failed_count": self.failed_count,
            "pending_count": self.pending_count,
            "invariant_ok": self.invariant_ok,
            "invariant_delta": self.invariant_delta,
            "skip_reasons": dict(self.skip_reasons),
        }


@dataclass
class QueueItem:
    url: str
    index: int


def _record_prequeue_outcome(
    job_id: str,
    idx: int,
    url: str,
    reason_code: str,
    *,
    filter_name: Optional[str] = None,
    filter_value: Optional[str] = None,
    actual_value: Optional[str] = None,
) -> None:
    status, message = resolve_legacy_skip(reason_code)
    outcome = build_outcome(
        status=status,
        reason_code=reason_code,
        reason_message=message,
        stage_failed="discover",
        listing_url=url,
        filter_name=filter_name,
        filter_value=filter_value,
        actual_value=actual_value,
    )
    laundry_store.record_listing_outcome(
        job_id,
        idx,
        listing_url=url,
        outcome=outcome,
    )
    trace_event(
        TRACE_SKIPPED,
        job_id=job_id,
        url=url,
        listing_index=idx,
        reason=reason_code,
        terminal_status=status,
    )


def build_listing_queue(
    *,
    job_id: str,
    raw_urls: List[str],
    listing_limit: int,
    completed_indices: Set[int],
    completed_urls: Set[str],
    global_known_urls: Optional[Set[str]] = None,
    source_available_count: Optional[int] = None,
) -> Tuple[List[QueueItem], ListingDiagnostics, List[Tuple[int, str, str]]]:
    """Build the processing queue and immediately account for non-queued URLs."""
    diag = ListingDiagnostics()
    global_known_urls = global_known_urls or set()
    skip_rows: List[Tuple[int, str, str]] = []
    queue: List[QueueItem] = []
    seen_in_batch: Set[str] = set()
    next_index = 0

    discovered = len(raw_urls)
    diag.requested_limit = listing_limit
    diag.discovered_count = discovered
    diag.source_available_count = source_available_count if source_available_count is not None else discovered
    diag.listings_found = discovered
    diag.effective_limit = min(listing_limit, discovered)

    for raw in raw_urls:
        url = (raw or "").strip()
        if not url:
            diag.failed_count += 1
            diag.skip_reasons["empty_url"] = diag.skip_reasons.get("empty_url", 0) + 1
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "empty_url"))
            continue
        trace_event(TRACE_DISCOVERED, job_id=job_id, url=url)

        norm = normalize_listing_url(url)
        if norm in seen_in_batch:
            diag.listings_deduped += 1
            diag.duplicate_count += 1
            diag.skip_reasons["duplicate_in_batch"] = diag.skip_reasons.get("duplicate_in_batch", 0) + 1
            trace_event(TRACE_DEDUPED, job_id=job_id, url=url, reason="duplicate_in_batch")
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "duplicate_in_batch"))
            continue
        seen_in_batch.add(norm)

        if norm in completed_urls:
            diag.listings_resumed += 1
            diag.duplicate_count += 1
            diag.skip_reasons["already_processed_in_job"] = diag.skip_reasons.get("already_processed_in_job", 0) + 1
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "already_processed_in_job"))
            trace_event(TRACE_SKIPPED, job_id=job_id, url=url, reason="already_processed_in_job")
            continue

        if norm in global_known_urls:
            diag.duplicate_count += 1
            diag.skip_reasons["known_listing_url"] = diag.skip_reasons.get("known_listing_url", 0) + 1
            trace_event(TRACE_DEDUPED, job_id=job_id, url=url, reason="known_listing_url")
            idx = next_index
            next_index += 1
            skip_rows.append((idx, url, "known_listing_url"))
            continue

        if len(queue) >= listing_limit:
            diag.listings_truncated += 1
            diag.filtered_out_count += 1
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

    diag.pending_count = diag.listings_queued
    return queue, diag, skip_rows


def persist_skip_rows(job_id: str, skip_rows: List[Tuple[int, str, str]]) -> None:
    for idx, url, reason in skip_rows:
        filter_name = None
        filter_value = None
        actual_value = None
        if reason == "listing_limit":
            filter_name = "listing_limit"
        _record_prequeue_outcome(
            job_id,
            idx,
            url,
            reason,
            filter_name=filter_name,
            filter_value=filter_value,
            actual_value=actual_value,
        )


def reconcile_diagnostics(
    diag: ListingDiagnostics,
    listing_rows: List[Dict[str, Any]],
) -> ListingDiagnostics:
    success = duplicate = filtered_out = failed = extraction_failed = 0
    for row in listing_rows:
        status = (row.get("status") or "").lower()
        bucket = accounting_bucket(status)
        if bucket == "success":
            success += 1
        elif bucket == "duplicate":
            duplicate += 1
        elif bucket == "filtered_out":
            filtered_out += 1
        elif status == "extraction_failed":
            extraction_failed += 1
            failed += 1
        elif status == "skipped":
            code = (row.get("reason_code") or (row.get("result") or {}).get("skip_reason") or "skipped")
            legacy_status, _ = resolve_legacy_skip(str(code))
            bucket = accounting_bucket(legacy_status)
            if bucket == "duplicate":
                duplicate += 1
            elif bucket == "filtered_out":
                filtered_out += 1
            else:
                failed += 1
        else:
            failed += 1

    processed = success + extraction_failed
    diag.listings_processed = processed
    diag.listings_failed = failed
    diag.listings_skipped = 0
    diag.success_count = success
    diag.duplicate_count = duplicate
    diag.filtered_out_count = filtered_out
    diag.failed_count = failed
    accounted = success + duplicate + filtered_out + failed
    diag.invariant_delta = diag.discovered_count - accounted
    diag.invariant_ok = diag.invariant_delta == 0
    if not diag.invariant_ok:
        log.warning(
            "pipeline.invariant mismatch job_id rows=%s discovered=%s success=%s dup=%s filtered=%s failed=%s delta=%s",
            len(listing_rows),
            diag.discovered_count,
            success,
            duplicate,
            filtered_out,
            failed,
            diag.invariant_delta,
        )
    return diag


def normalize_worker_result(res: Dict[str, Any]) -> Dict[str, Any]:
    return merge_pipeline_result(res)
