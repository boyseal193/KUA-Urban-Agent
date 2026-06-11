"""Structured terminal outcomes for laundry listing pipeline accounting."""
from __future__ import annotations

import traceback as _tb
from typing import Any, Dict, Optional, Tuple

# Non-terminal step states
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_RETRYING = "retrying"

# Terminal listing outcomes (scan_listing_results.status)
STATUS_SUCCESS = "success"
STATUS_DUPLICATE = "duplicate"
STATUS_FILTERED_OUT = "filtered_out"
STATUS_SCRAPE_FAILED = "scrape_failed"
STATUS_EXTRACTION_FAILED = "extraction_failed"
STATUS_PERSISTENCE_FAILED = "persistence_failed"
STATUS_SCORING_FAILED = "scoring_failed"
STATUS_MEMO_FAILED = "memo_failed"
STATUS_EXPORT_FAILED = "export_failed"
STATUS_FAILED = "failed"

TERMINAL_STATUSES = frozenset({
    STATUS_SUCCESS,
    STATUS_DUPLICATE,
    STATUS_FILTERED_OUT,
    STATUS_SCRAPE_FAILED,
    STATUS_EXTRACTION_FAILED,
    STATUS_PERSISTENCE_FAILED,
    STATUS_SCORING_FAILED,
    STATUS_MEMO_FAILED,
    STATUS_EXPORT_FAILED,
    STATUS_FAILED,
})

SUCCESS_STATUSES = frozenset({STATUS_SUCCESS})
DUPLICATE_STATUSES = frozenset({STATUS_DUPLICATE})
FILTERED_STATUSES = frozenset({STATUS_FILTERED_OUT})
FAILED_STATUSES = frozenset({
    STATUS_SCRAPE_FAILED,
    STATUS_EXTRACTION_FAILED,
    STATUS_PERSISTENCE_FAILED,
    STATUS_SCORING_FAILED,
    STATUS_MEMO_FAILED,
    STATUS_EXPORT_FAILED,
    STATUS_FAILED,
})

# Legacy generic skipped → structured mapping
LEGACY_SKIP_MAP: Dict[str, Tuple[str, str]] = {
    "empty_url": (STATUS_FAILED, "Empty listing URL"),
    "duplicate_in_batch": (STATUS_DUPLICATE, "Duplicate URL within the same scan batch"),
    "known_listing_url": (STATUS_DUPLICATE, "Listing URL already processed in this job"),
    "already_processed_in_job": (STATUS_DUPLICATE, "Listing already processed in this scan (resume)"),
    "listing_limit": (STATUS_FILTERED_OUT, "Beyond requested listing limit for this scan"),
    "neighbourhood_filter_no_match": (
        STATUS_FILTERED_OUT,
        "Listing neighbourhood did not match configured filters",
    ),
    "skipped": (STATUS_FAILED, "Unclassified skip — see worker logs"),
}

REASON_MESSAGES: Dict[str, str] = {
    "dedupe_key_collision": "Property already exists for this dedupe key",
    "scrape_failed": "Could not fetch listing detail page",
    "insufficient_extracted_fields": "Could not extract minimum required fields",
    "property_upsert_failed": "Failed to persist property row",
    "analysis_insert_failed": "Property saved but analysis insert failed",
    "partial_property_failed": "Failed to create partial property card",
    "max_retries_exceeded": "Maximum scrape/retry attempts exceeded",
    "persistence_failed_no_property_id": "Pipeline finished without a property id",
}


def resolve_legacy_skip(reason_code: str) -> Tuple[str, str]:
    code = (reason_code or "skipped").strip()
    status, message = LEGACY_SKIP_MAP.get(code, (STATUS_FAILED, REASON_MESSAGES.get(code, code)))
    return status, message


def build_outcome(
    *,
    status: str,
    reason_code: str,
    reason_message: Optional[str] = None,
    stage_failed: Optional[str] = None,
    attempt_count: int = 0,
    listing_url: Optional[str] = None,
    property_id: Optional[str] = None,
    duplicate_of_property_id: Optional[str] = None,
    duplicate_of_listing_url: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    dedupe_method: Optional[str] = None,
    duplicate_confidence: Optional[float] = None,
    filter_name: Optional[str] = None,
    filter_value: Optional[str] = None,
    actual_value: Optional[str] = None,
    exception_type: Optional[str] = None,
    traceback: Optional[str] = None,
    raw_error: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    msg = reason_message or REASON_MESSAGES.get(reason_code) or reason_code.replace("_", " ")
    out: Dict[str, Any] = {
        "terminal_status": status,
        "status": status,
        "reason_code": reason_code,
        "reason_message": msg,
        "stage_failed": stage_failed,
        "attempt_count": attempt_count,
        "listing_url": listing_url,
        "property_id": property_id,
        "duplicate_of_property_id": duplicate_of_property_id,
        "duplicate_of_listing_url": duplicate_of_listing_url,
        "dedupe_key": dedupe_key,
        "dedupe_method": dedupe_method or ("dedupe_key" if dedupe_key else None),
        "duplicate_confidence": duplicate_confidence,
        "filter_name": filter_name,
        "filter_value": filter_value,
        "actual_value": actual_value,
        "exception_type": exception_type,
        "traceback": (traceback or "")[:8000] or None,
        "raw_error": (raw_error or "")[:2000] or None,
    }
    if extra:
        out.update(extra)
    return out


def outcome_from_exception(
    exc: BaseException,
    *,
    status: str = STATUS_FAILED,
    reason_code: str = "worker_exception",
    stage_failed: str = "underwrite",
    attempt_count: int = 0,
    listing_url: Optional[str] = None,
) -> Dict[str, Any]:
    return build_outcome(
        status=status,
        reason_code=reason_code,
        reason_message=str(exc),
        stage_failed=stage_failed,
        attempt_count=attempt_count,
        listing_url=listing_url,
        exception_type=type(exc).__name__,
        traceback=_tb.format_exc(limit=12),
        raw_error=str(exc),
    )


def merge_pipeline_result(res: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a pipeline worker result dict with terminal outcome fields."""
    if not isinstance(res, dict):
        return build_outcome(
            status=STATUS_FAILED,
            reason_code="invalid_worker_result",
            reason_message="Worker returned non-dict result",
            stage_failed="underwrite",
        )

    if res.get("terminal_status"):
        res.setdefault("status", res["terminal_status"])
        return res

    if res.get("skipped"):
        code = str(res.get("reason_code") or res.get("reason") or "skipped")
        status, msg = resolve_legacy_skip(code)
        merged = build_outcome(
            status=status,
            reason_code=code,
            reason_message=res.get("reason_message") or msg,
            stage_failed=res.get("stage_failed") or "filter",
            attempt_count=int(res.get("attempt_count") or 0),
            listing_url=res.get("url") or res.get("listing_url"),
            filter_name=res.get("filter_name"),
            filter_value=res.get("filter_value"),
            actual_value=res.get("actual_value"),
            property_id=res.get("property_id"),
            duplicate_of_property_id=res.get("duplicate_of_property_id"),
            dedupe_key=res.get("dedupe_key"),
            dedupe_method=res.get("dedupe_method"),
        )
        res.update(merged)
        res["skipped"] = False
        return res

    if res.get("duplicate"):
        merged = build_outcome(
            status=STATUS_DUPLICATE,
            reason_code=res.get("reason_code") or "dedupe_key_collision",
            reason_message=res.get("reason_message") or REASON_MESSAGES["dedupe_key_collision"],
            stage_failed="persist",
            attempt_count=int(res.get("attempt_count") or 0),
            listing_url=res.get("url") or res.get("listing_url"),
            property_id=res.get("property_id"),
            duplicate_of_property_id=res.get("duplicate_of_property_id") or res.get("property_id"),
            duplicate_of_listing_url=res.get("duplicate_of_listing_url"),
            dedupe_key=res.get("dedupe_key"),
            dedupe_method=res.get("dedupe_method") or "dedupe_key",
            duplicate_confidence=res.get("duplicate_confidence"),
        )
        res.update(merged)
        return res

    if res.get("extraction_failed") and res.get("property_id"):
        merged = build_outcome(
            status=STATUS_EXTRACTION_FAILED,
            reason_code=res.get("reason_code") or "insufficient_extracted_fields",
            reason_message=res.get("error") or REASON_MESSAGES.get("insufficient_extracted_fields"),
            stage_failed=res.get("stage_failed") or "extract",
            attempt_count=int(res.get("attempt_count") or 0),
            listing_url=res.get("url") or res.get("listing_url"),
            property_id=res.get("property_id"),
        )
        res.update(merged)
        return res

    if res.get("property_id") and res.get("success", True):
        merged = build_outcome(
            status=STATUS_SUCCESS,
            reason_code="processed",
            reason_message="Listing underwritten successfully",
            attempt_count=int(res.get("attempt_count") or 0),
            listing_url=res.get("url") or res.get("listing_url"),
            property_id=res.get("property_id"),
            dedupe_key=res.get("dedupe_key"),
        )
        res.update(merged)
        return res

    err = res.get("error") or res.get("persist_warning") or "unknown_failure"
    stage = res.get("stage_failed") or "underwrite"
    if "scrape" in str(err).lower():
        status = STATUS_SCRAPE_FAILED
        code = "scrape_failed"
    elif res.get("persist_warning") or "persist" in str(err).lower():
        status = STATUS_PERSISTENCE_FAILED
        code = "property_upsert_failed"
    else:
        status = STATUS_FAILED
        code = res.get("reason_code") or "pipeline_failed"

    merged = build_outcome(
        status=status,
        reason_code=code,
        reason_message=str(err),
        stage_failed=stage,
        attempt_count=int(res.get("attempt_count") or 0),
        listing_url=res.get("url") or res.get("listing_url"),
        property_id=res.get("property_id"),
        raw_error=str(err),
    )
    res.update(merged)
    return res


def step_status_for_terminal(terminal_status: str) -> str:
    """Map listing terminal status to scan_steps.status (never generic skipped)."""
    if terminal_status in TERMINAL_STATUSES:
        return terminal_status
    if terminal_status == "skipped":
        return STATUS_FAILED
    return terminal_status or STATUS_FAILED


def accounting_bucket(terminal_status: str) -> str:
    if terminal_status in SUCCESS_STATUSES:
        return "success"
    if terminal_status in DUPLICATE_STATUSES:
        return "duplicate"
    if terminal_status in FILTERED_STATUSES:
        return "filtered_out"
    if terminal_status == STATUS_EXTRACTION_FAILED:
        return "extraction_failed"
    return "failed"


def display_label(terminal_status: str) -> str:
    labels = {
        STATUS_SUCCESS: "SUCCESS",
        STATUS_DUPLICATE: "DUPLICATE",
        STATUS_FILTERED_OUT: "FILTERED OUT",
        STATUS_SCRAPE_FAILED: "SCRAPE FAILED",
        STATUS_EXTRACTION_FAILED: "EXTRACTION FAILED",
        STATUS_PERSISTENCE_FAILED: "PERSISTENCE FAILED",
        STATUS_SCORING_FAILED: "SCORING FAILED",
        STATUS_MEMO_FAILED: "MEMO FAILED",
        STATUS_EXPORT_FAILED: "EXPORT FAILED",
        STATUS_FAILED: "FAILED",
        STATUS_PENDING: "PENDING",
        STATUS_RUNNING: "RUNNING",
        STATUS_RETRYING: "RETRYING",
        "skipped": "FAILED",
    }
    return labels.get(terminal_status, terminal_status.replace("_", " ").upper())
