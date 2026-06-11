"""Autonomous acquisition sequencer for laundry scans.

The operator launches a scan once; the sequencer decides the next step from
job state, retries failed work, broadens empty searches, skips bad listings,
continues with partial records, generates exports, and resumes interrupted jobs.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback as _tb
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from jobs import store as job_store
from jobs.constants import JOB_CANCELLED, JOB_FAILED, JOB_RUNNING, JOB_SUCCESS

from laundry import exports, pipeline, store as laundry_store, url_builder
from laundry.limits import availability_message, clamp_listing_limit
from laundry.listing_ledger import (
    ListingDiagnostics,
    TRACE_CLAIMED,
    TRACE_FAILED,
    TRACE_PROCESSED,
    TRACE_RETRIED,
    build_listing_queue,
    normalize_worker_result,
    persist_skip_rows,
    reconcile_diagnostics,
    trace_event,
)
from laundry.listing_outcomes import (
    accounting_bucket,
    display_label,
    merge_pipeline_result,
    resolve_legacy_skip,
    step_status_for_terminal,
)
from laundry.pipeline import EXTRACTION_FAILED

log = logging.getLogger("kua.laundry.sequencer")

JOB_NO_RESULTS = "no_results"
AREA_SEARCH_TYPES = {"area_search", "automatic_scan"}

OPERATION_MODES = ("conservative", "balanced", "aggressive")
TIMEOUT_LEVELS = ("short", "normal", "long")

MODE_PRESETS: Dict[str, Dict[str, Any]] = {
    "conservative": {
        "listing_retries": 1,
        "discovery_attempts": 2,
        "thresholds": {"approved_min": 80, "manual_review_min": 45},
        "prefer_manual_over_reject": False,
        "auto_export": True,
    },
    "balanced": {
        "listing_retries": 2,
        "discovery_attempts": 3,
        "thresholds": {"approved_min": 75, "manual_review_min": 40},
        "prefer_manual_over_reject": False,
        "auto_export": True,
    },
    "aggressive": {
        "listing_retries": 3,
        "discovery_attempts": 5,
        "thresholds": {"approved_min": 70, "manual_review_min": 35},
        "prefer_manual_over_reject": True,
        "auto_export": True,
    },
}

TIMEOUT_SECONDS = {
    "short": 45,
    "normal": 90,
    "long": 180,
}

DEFAULT_AUTONOMOUS_DEFAULTS: Dict[str, Any] = {
    "autonomous_mode": True,
    "operation_mode": "balanced",
    "max_attempts": 3,
    "concurrency": int(os.getenv("PIPELINE_CONCURRENCY", "3")),
    "timeout_level": "normal",
    "auto_export": True,
}


@dataclass
class AutonomousConfig:
    enabled: bool = True
    operation_mode: str = "balanced"
    max_attempts: int = 3
    concurrency: int = 2
    timeout_level: str = "normal"
    auto_export: bool = True

    listing_retries: int = 2
    discovery_attempts: int = 3
    listing_timeout_sec: int = 90
    prefer_manual_over_reject: bool = False
    scoring_overrides: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> AutonomousConfig:
        raw = payload.get("autonomous") or {}
        if not isinstance(raw, dict):
            raw = {}

        enabled = payload.get("autonomous_mode")
        if enabled is None:
            enabled = raw.get("enabled", DEFAULT_AUTONOMOUS_DEFAULTS["autonomous_mode"])
        enabled = bool(enabled)

        mode = (
            payload.get("operation_mode")
            or raw.get("operation_mode")
            or DEFAULT_AUTONOMOUS_DEFAULTS["operation_mode"]
        ).lower()
        if mode not in OPERATION_MODES:
            mode = "balanced"

        preset = MODE_PRESETS[mode]
        max_attempts = int(
            payload.get("max_attempts")
            or raw.get("max_attempts")
            or preset.get("discovery_attempts")
            or DEFAULT_AUTONOMOUS_DEFAULTS["max_attempts"]
        )
        max_attempts = max(1, min(max_attempts, 10))

        concurrency = int(
            payload.get("concurrency")
            or raw.get("concurrency")
            or os.getenv("PIPELINE_CONCURRENCY")
            or DEFAULT_AUTONOMOUS_DEFAULTS["concurrency"]
        )
        concurrency = max(1, min(concurrency, 5))

        timeout_level = (
            payload.get("timeout_level")
            or raw.get("timeout_level")
            or DEFAULT_AUTONOMOUS_DEFAULTS["timeout_level"]
        ).lower()
        if timeout_level not in TIMEOUT_LEVELS:
            timeout_level = "normal"

        auto_export = payload.get("auto_export")
        if auto_export is None:
            auto_export = raw.get("auto_export", preset.get("auto_export", True))
        auto_export = bool(auto_export)

        listing_retries = min(
            int(preset.get("listing_retries", 2)),
            max_attempts,
        )
        if not enabled:
            listing_retries = 0
            auto_export = bool(payload.get("auto_export") or raw.get("auto_export"))

        thresholds = dict(preset.get("thresholds") or {})
        scoring_overrides: Dict[str, Any] = {"thresholds": thresholds}

        return cls(
            enabled=enabled,
            operation_mode=mode,
            max_attempts=max_attempts,
            concurrency=concurrency,
            timeout_level=timeout_level,
            auto_export=auto_export and enabled,
            listing_retries=listing_retries if enabled else 0,
            discovery_attempts=max_attempts if enabled else 1,
            listing_timeout_sec=TIMEOUT_SECONDS[timeout_level],
            prefer_manual_over_reject=bool(preset.get("prefer_manual_over_reject")),
            scoring_overrides=scoring_overrides,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "operation_mode": self.operation_mode,
            "max_attempts": self.max_attempts,
            "concurrency": self.concurrency,
            "timeout_level": self.timeout_level,
            "auto_export": self.auto_export,
            "listing_retries": self.listing_retries,
            "discovery_attempts": self.discovery_attempts,
            "listing_timeout_sec": self.listing_timeout_sec,
            "prefer_manual_over_reject": self.prefer_manual_over_reject,
        }

    def merge_overrides(self, base: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base or {})
        if self.scoring_overrides:
            existing = dict(merged.get("thresholds") or {})
            existing.update(self.scoring_overrides.get("thresholds") or {})
            merged["thresholds"] = existing
        merged["sequencer_mode"] = self.operation_mode
        merged["prefer_manual_over_reject"] = self.prefer_manual_over_reject
        return merged


def parse_autonomous_defaults(stored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(DEFAULT_AUTONOMOUS_DEFAULTS)
    if not stored:
        return out
    autonomous = stored.get("autonomous") if isinstance(stored.get("autonomous"), dict) else stored
    for key in DEFAULT_AUTONOMOUS_DEFAULTS:
        if key in autonomous:
            out[key] = autonomous[key]
    if out.get("operation_mode") not in OPERATION_MODES:
        out["operation_mode"] = "balanced"
    if out.get("timeout_level") not in TIMEOUT_LEVELS:
        out["timeout_level"] = "normal"
    out["max_attempts"] = max(1, min(int(out.get("max_attempts") or 3), 10))
    out["concurrency"] = max(1, min(int(out.get("concurrency") or os.getenv("PIPELINE_CONCURRENCY", 3)), 5))
    out["autonomous_mode"] = bool(out.get("autonomous_mode", True))
    out["auto_export"] = bool(out.get("auto_export", True))
    return out


class AutonomousSequencer:
    """State-driven orchestrator for a single laundry scan job."""

    def __init__(
        self,
        *,
        job_id: str,
        job: Dict[str, Any],
        payload: Dict[str, Any],
        config: AutonomousConfig,
        worker_id: str,
    ) -> None:
        self.job_id = job_id
        self.job = job
        self.payload = payload
        self.config = config
        self.worker_id = worker_id
        self.started = time.monotonic()

        self.filters = payload.get("filters") or {}
        self.overrides = config.merge_overrides(payload.get("overrides") or {})
        self.listing_url = payload.get("url") or job.get("search_url") or None
        self.raw_text = payload.get("raw_text")
        self.use_llm = bool(payload.get("use_llm_extraction", False))
        self.listing_limit = clamp_listing_limit(
            payload.get("listing_limit") or job.get("listing_limit") or 10
        )
        self.requested_limit = self.listing_limit
        self.search_type = (payload.get("search_type") or self.filters.get("search_type") or "manual_url").lower()
        self.search_provider = payload.get("search_provider") or "idealista"
        self.search_diagnostics = payload.get("search_diagnostics") or {}

        self._counter_lock = threading.Lock()
        self._diagnostics = ListingDiagnostics()
        self._retried_count = 0
        self._completed_urls: Set[str] = set()

        self.counters: Dict[str, int] = {
            "done": 0,
            "total": 0,
            "approved": 0,
            "manual_review": 0,
            "rejected": 0,
            "failed": 0,
            "success": 0,
            "duplicate": 0,
            "filtered_out": 0,
            "extraction_failed": 0,
            "deduped": 0,
            "resumed": 0,
        }
        self._completed_indices: Set[int] = set()

    def run(self) -> Dict[str, Any]:
        if (self.job.get("status") or "").lower() == "cancelled":
            return {"success": True, "skipped": "cancelled", "job_id": self.job_id}

        schema_ok, schema_err = laundry_store.check_laundry_schema()
        if not schema_ok:
            log.error("laundry.sequencer abort job_id=%s schema_not_ready: %s", self.job_id, schema_err)
            laundry_store.update_job(
                self.job_id,
                status=JOB_FAILED,
                finished_at=job_store._now(),
                error_message=f"Laundry schema not ready: {schema_err}. Run laundry/schema.sql in Supabase.",
            )
            return self._final_response(JOB_FAILED)

        laundry_store.clean_stale_running_jobs(max_age_minutes=120)

        laundry_store.update_job(
            self.job_id,
            status=JOB_RUNNING,
            started_at=job_store._now(),
            worker_id=self.worker_id,
            progress_pct=2,
            error_message=None,
        )
        self._touch_heartbeat()

        self._load_resume_state()

        try:
            if not self._step_ingest():
                return self._final_response(JOB_NO_RESULTS)

            mode = self._detect_mode()
            listing_targets = self._step_discover(mode)
            if listing_targets is None:
                return self._final_response(JOB_FAILED)
            if not listing_targets:
                return self._final_response(JOB_NO_RESULTS)

            if not self._step_underwrite(listing_targets):
                return self._final_response(JOB_CANCELLED)

            final_status = self._step_summarize(None)
            if self.config.auto_export:
                threading.Thread(
                    target=self._run_export_background,
                    name=f"laundry-export-{self.job_id[:8]}",
                    daemon=True,
                ).start()
            return self._final_response(final_status)

        except Exception as exc:
            log.exception("Autonomous sequencer crashed: %s", exc)
            self._finalize_failed(str(exc)[:1000])
            return self._final_response(JOB_FAILED)

    def _load_resume_state(self) -> None:
        existing = laundry_store.get_listing_results(self.job_id)
        self._completed_urls = laundry_store.get_completed_listing_urls(self.job_id)
        self.counters["done"] = len(existing)
        for row in existing:
            idx = row.get("listing_index")
            if idx is None:
                continue
            status = (row.get("status") or "").lower()
            if row.get("property_id") or status in ("success", "skipped", EXTRACTION_FAILED, "failed"):
                self._completed_indices.add(int(idx))
                bucket = _classify_listing_row(row)
                self.counters[bucket] = self.counters.get(bucket, 0) + 1
        if self._completed_indices:
            self.counters["resumed"] = len(self._completed_indices)
            log.info(
                "laundry.sequencer resume job_id=%s skipping_indices=%s",
                self.job_id,
                sorted(self._completed_indices),
            )

    def _step_ingest(self) -> bool:
        laundry_store.start_step(self.job_id, laundry_store.JOB_STEP_INGEST)

        if self.config.enabled and not self.listing_url and not self.raw_text:
            built = self._auto_generate_search_url()
            if built:
                self.listing_url = built.get("url") or self.listing_url
                if built.get("diagnostics"):
                    self.search_diagnostics = built["diagnostics"]

        if not self.listing_url and not self.raw_text:
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_INGEST,
                status=laundry_store.STEP_FAILED,
                error_message="No listing_url, search URL or raw text supplied",
            )
            self._finalize_no_results("No URL or raw text supplied")
            return False

        laundry_store.finish_step(
            self.job_id,
            laundry_store.JOB_STEP_INGEST,
            status=laundry_store.STEP_SUCCESS,
            output={
                "listing_url": self.listing_url,
                "has_text": bool(self.raw_text),
                "search_type": self.search_type,
                "autonomous": self.config.to_dict(),
            },
        )
        return True

    def _auto_generate_search_url(self) -> Optional[Dict[str, Any]]:
        if self.search_type not in AREA_SEARCH_TYPES and not self.config.enabled:
            return None
        try:
            builder_payload = self._url_builder_payload()
            built = url_builder.resolve_search_url(
                builder_payload,
                provider=self.search_provider,
                validate=True,
            )
            log.info(
                "laundry.sequencer auto_url job_id=%s provider=%s url=%s broadened=%s",
                self.job_id,
                built.provider,
                built.url,
                (built.diagnostics.search_broadened if built.diagnostics else False),
            )
            laundry_store.update_job(self.job_id, search_url=built.url)
            try:
                job_store.update_job(self.job_id, search_url=built.url)
            except Exception:
                pass
            return {
                "url": built.url,
                "provider": built.provider,
                "diagnostics": built.diagnostics.to_dict() if built.diagnostics else None,
            }
        except url_builder.UnsupportedFilterError as exc:
            log.warning("laundry.sequencer auto_url failed job_id=%s: %s", self.job_id, exc)
            return None

    def _url_builder_payload(self) -> Dict[str, Any]:
        f = self.filters
        return {
            "acquisition_type": f.get("acquisition_type") or "rent",
            "property_type": f.get("property_type") or "empty_commercial",
            "city": f.get("city") or "Barcelona",
            "neighbourhoods": list(f.get("neighbourhood_filters") or f.get("neighbourhoods") or []),
            "max_size_sqm": float(f["max_size_sqm"]) if f.get("max_size_sqm") else None,
            "min_size_sqm": float(f["min_size_sqm"]) if f.get("min_size_sqm") else None,
            "max_price_eur": float(f["max_price_eur"]) if f.get("max_price_eur") else None,
            "max_rent_month_eur": float(f["max_rent_month_eur"]) if f.get("max_rent_month_eur") else None,
            "ground_floor_only": bool(f.get("ground_floor_only", True)),
            "listing_limit": self.listing_limit,
            "extra_filters": dict(f.get("extra_filters") or {}),
        }

    def _detect_mode(self) -> str:
        if self.raw_text and not self.listing_url:
            return "inline_text"
        if self.listing_url and self.search_type in AREA_SEARCH_TYPES:
            return "area_discover"
        return "single_listing"

    def _step_discover(self, mode: str) -> Optional[List[Tuple[Optional[str], Optional[str], int]]]:
        if mode == "inline_text":
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_DISCOVER,
                status=laundry_store.STEP_SKIPPED,
                output={"reason": "inline_text_only"},
            )
            self._diagnostics.listings_found = 1
            self._diagnostics.listings_queued = 1
            self._diagnostics.requested_limit = self.requested_limit
            self._diagnostics.effective_limit = 1
            self._diagnostics.discovered_count = 1
            self._diagnostics.source_available_count = 1
            return [(None, self.raw_text, 0)]

        if mode == "single_listing":
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_DISCOVER,
                status=laundry_store.STEP_SKIPPED,
                output={"reason": "single_listing_url"},
            )
            self._diagnostics.listings_found = 1
            self._diagnostics.listings_queued = 1
            self._diagnostics.requested_limit = self.requested_limit
            self._diagnostics.effective_limit = 1
            self._diagnostics.discovered_count = 1
            self._diagnostics.source_available_count = 1
            return [(self.listing_url, None, 0)]

        laundry_store.start_step(self.job_id, laundry_store.JOB_STEP_DISCOVER, listing_url=self.listing_url)
        raw_urls, diagnostics = self._discover_with_retries()
        if diagnostics:
            self.search_diagnostics = diagnostics

        if diagnostics.get("search_url") and diagnostics["search_url"] != self.listing_url:
            self.listing_url = diagnostics["search_url"]
            laundry_store.update_job(self.job_id, search_url=self.listing_url)
            try:
                job_store.update_job(self.job_id, search_url=self.listing_url)
            except Exception:
                pass

        source_available_count = None
        if diagnostics:
            self.search_diagnostics = diagnostics
            source_available_count = diagnostics.get("source_available_count")

        queue, self._diagnostics, skip_rows = build_listing_queue(
            job_id=self.job_id,
            raw_urls=raw_urls,
            listing_limit=self.listing_limit,
            completed_indices=self._completed_indices,
            completed_urls=self._completed_urls,
            source_available_count=source_available_count,
        )
        persist_skip_rows(self.job_id, skip_rows)
        for item in queue:
            laundry_store.seed_listing_step(
                self.job_id,
                item.index,
                listing_url=item.url,
                status=laundry_store.STEP_PENDING,
            )
        for idx, url, reason in skip_rows:
            terminal_status, msg = resolve_legacy_skip(reason)
            laundry_store.seed_listing_step(
                self.job_id,
                idx,
                listing_url=url,
                status=step_status_for_terminal(terminal_status),
                error_message=msg,
                output={"reason_code": reason, "reason_message": msg, "terminal_status": terminal_status},
            )

        availability_note = availability_message(
            requested_limit=self.requested_limit,
            discovered_count=self._diagnostics.discovered_count,
            source_available_count=self._diagnostics.source_available_count,
        )

        discover_output: Dict[str, Any] = {
            "discovered_count": self._diagnostics.discovered_count,
            "queued_count": self._diagnostics.listings_queued,
            "requested_limit": self.requested_limit,
            "effective_limit": self._diagnostics.effective_limit,
            "source_available_count": self._diagnostics.source_available_count,
            "availability_message": availability_note,
            "search_url": self.listing_url,
            "urls": raw_urls[:20],
            "diagnostics": self._diagnostics.to_dict(),
        }
        if self.search_diagnostics:
            discover_output["search_diagnostics"] = self.search_diagnostics

        if self._diagnostics.listings_found == 0:
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_DISCOVER,
                status=laundry_store.STEP_FAILED,
                output=discover_output,
                error_message="No listings discovered even after automatic search broadening.",
            )
            self._finalize_no_results(
                "No listings found even after broadening the search URL "
                "(neighbourhood → district → Barcelona → metropolitan). "
                "Try a different provider or paste a custom search URL."
            )
            laundry_store.finish_step(self.job_id, laundry_store.JOB_STEP_UNDERWRITE, status=laundry_store.STEP_SKIPPED)
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_SUMMARY,
                status=laundry_store.STEP_SUCCESS,
                output={"reason": "no_listings_to_score"},
            )
            return []

        laundry_store.finish_step(
            self.job_id,
            laundry_store.JOB_STEP_DISCOVER,
            status=laundry_store.STEP_SUCCESS,
            output=discover_output,
        )
        return [(item.url, None, item.index) for item in queue]

    def _discover_with_retries(self) -> Tuple[List[str], Dict[str, Any]]:
        attempts = 0
        last_urls: List[str] = []
        diagnostics: Dict[str, Any] = dict(self.search_diagnostics or {})
        max_tries = self.config.discovery_attempts if self.config.enabled else 1

        while attempts < max_tries:
            attempts += 1
            try:
                urls, resolved = url_builder.discover_with_fallback(
                    self.listing_url or "",
                    self.filters,
                    provider=self.search_provider,
                    limit=self.listing_limit,
                )
                if resolved.diagnostics:
                    diagnostics = resolved.diagnostics.to_dict()
                diagnostics["search_url"] = resolved.url
                diagnostics["attempt"] = attempts
                if urls:
                    return urls, diagnostics
                last_urls = urls
                if not self.config.enabled:
                    break
                log.info(
                    "laundry.sequencer discover retry job_id=%s attempt=%s/%s",
                    self.job_id,
                    attempts,
                    max_tries,
                )
                time.sleep(min(attempts, 3))
            except Exception as exc:
                log.exception("Discovery attempt %s failed: %s", attempts, exc)
                diagnostics["last_error"] = str(exc)
                if attempts >= max_tries:
                    raise

        return last_urls, diagnostics

    def _step_underwrite(self, targets: List[Tuple[Optional[str], Optional[str], int]]) -> bool:
        self.counters["total"] = self.requested_limit
        self.counters["deduped"] = self._diagnostics.listings_deduped
        laundry_store.set_job_counters(
            self.job_id,
            listings_total=self.requested_limit,
            progress_pct=10,
        )
        laundry_store.start_step(self.job_id, laundry_store.JOB_STEP_UNDERWRITE)

        pending = [
            (url, text, idx)
            for url, text, idx in targets
            if idx not in self._completed_indices
        ]
        url_by_idx = {idx: url for url, text, idx in targets}
        workers = max(1, min(self.config.concurrency, len(pending) or 1))

        if workers <= 1 or len(pending) <= 1:
            for url, text, idx in pending:
                if not self._process_one_listing(url, text, idx):
                    return False
        else:
            log.info(
                "laundry.sequencer concurrent job_id=%s workers=%s pending=%s",
                self.job_id,
                workers,
                len(pending),
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._process_listing_worker, url, text, idx): idx
                    for url, text, idx in pending
                }
                for future in as_completed(futures):
                    if laundry_store.is_job_cancelled(self.job_id):
                        self._handle_cancel(futures[future])
                        return False
                    idx = futures[future]
                    try:
                        _ok, res = future.result()
                    except Exception as exc:
                        log.exception("Concurrent listing worker failed idx=%s: %s", idx, exc)
                        res = {"success": False, "error": str(exc)}
                        if url_by_idx.get(idx):
                            res = pipeline.persist_extraction_failed(
                                listing_url=url_by_idx[idx],
                                job_id=self.job_id,
                                extracted={},
                                error=str(exc),
                            )
                    self._apply_listing_result(idx, url_by_idx.get(idx), res)

        laundry_store.finish_step(
            self.job_id,
            laundry_store.JOB_STEP_UNDERWRITE,
            status=laundry_store.STEP_SUCCESS,
            output={
                k: self.counters[k]
                for k in (
                    "approved",
                    "manual_review",
                    "rejected",
                    "failed",
                    "skipped",
                    "extraction_failed",
                    "deduped",
                    "resumed",
                )
            },
        )
        return True

    def _process_one_listing(
        self,
        url: Optional[str],
        text: Optional[str],
        idx: int,
    ) -> bool:
        if laundry_store.is_job_cancelled(self.job_id):
            self._handle_cancel(idx)
            return False
        self._touch_heartbeat()
        res = self._process_listing_worker(url, text, idx)[1]
        self._apply_listing_result(idx, url, res)
        return True

    def _process_listing_worker(
        self,
        url: Optional[str],
        text: Optional[str],
        idx: int,
    ) -> Tuple[bool, Dict[str, Any]]:
        trace_event(TRACE_CLAIMED, job_id=self.job_id, url=url, listing_index=idx)
        laundry_store.start_step(
            self.job_id,
            laundry_store.LISTING_STEP_PROCESS,
            listing_index=idx,
            listing_url=url,
        )
        step_started = time.monotonic()
        res, retries = self._run_listing_with_retries(url, text, idx)
        res = merge_pipeline_result(normalize_worker_result(res))
        if retries:
            with self._counter_lock:
                self._retried_count += retries
        res = self._maybe_upgrade_to_manual_review(res)

        step_ms = int((time.monotonic() - step_started) * 1000)
        terminal_status = res.get("status") or res.get("terminal_status") or "failed"
        bucket = accounting_bucket(terminal_status)
        if bucket == "failed" or terminal_status == EXTRACTION_FAILED:
            trace_event(
                TRACE_FAILED,
                job_id=self.job_id,
                url=url,
                listing_index=idx,
                error=res.get("reason_message") or res.get("error"),
                terminal_status=terminal_status,
            )
        else:
            trace_event(
                TRACE_PROCESSED,
                job_id=self.job_id,
                url=url,
                listing_index=idx,
                property_id=res.get("property_id"),
                deal_status=_deal_status(res),
                terminal_status=terminal_status,
            )
        listing_status = step_status_for_terminal(terminal_status)
        laundry_store.finish_step(
            self.job_id,
            laundry_store.LISTING_STEP_PROCESS,
            listing_index=idx,
            status=listing_status,
            error_type=res.get("reason_code") if listing_status != laundry_store.STEP_SUCCESS else None,
            error_message=res.get("reason_message") or res.get("error") or res.get("persist_warning"),
            duration_ms=step_ms,
            output={
                "terminal_status": terminal_status,
                "reason_code": res.get("reason_code"),
                "reason_message": res.get("reason_message"),
                "stage_failed": res.get("stage_failed"),
                "attempt_count": res.get("attempt_count"),
                "deal_status": _deal_status(res),
                "score": (res.get("scoring") or {}).get("score"),
                "property_id": res.get("property_id"),
                "analysis_id": res.get("analysis_id"),
                "duplicate_of_property_id": res.get("duplicate_of_property_id"),
                "extraction_failed": bool(res.get("extraction_failed")),
            },
        )
        return True, res

    def _apply_listing_result(self, idx: int, url: Optional[str], res: Dict[str, Any]) -> None:
        res = merge_pipeline_result(res)
        bucket = _classify_result(res)
        _record_listing(self.job_id, idx, url, res)
        with self._counter_lock:
            self.counters[bucket] = self.counters.get(bucket, 0) + 1
            terminal = res.get("status") or res.get("terminal_status")
            acct = accounting_bucket(str(terminal or bucket))
            if acct == "success":
                self.counters["success"] = self.counters.get("success", 0) + 1
            elif acct == "duplicate":
                self.counters["duplicate"] = self.counters.get("duplicate", 0) + 1
            elif acct == "filtered_out":
                self.counters["filtered_out"] = self.counters.get("filtered_out", 0) + 1
            elif acct == "failed":
                self.counters["failed"] = self.counters.get("failed", 0) + 1
            self.counters["done"] = self.counters.get("done", 0) + 1
            done = self.counters["done"]
            total = self.counters["total"]
            failed = self.counters["failed"]
            approved = self.counters["approved"]
            manual = self.counters["manual_review"]
            rejected = self.counters["rejected"]

        progress = 10 + int((done / max(total, 1)) * 70)
        laundry_store.set_job_counters(
            self.job_id,
            listings_done=done,
            listings_failed=failed,
            approved_count=approved,
            manual_review_count=manual,
            rejected_count=rejected,
            progress_pct=min(progress, 90),
        )
        log.info(
            "laundry.sequencer listing %s/%s url=%s bucket=%s property_id=%s",
            done,
            total,
            url,
            bucket,
            res.get("property_id"),
        )

    def _run_listing_with_retries(
        self,
        url: Optional[str],
        text: Optional[str],
        idx: int,
    ) -> Tuple[Dict[str, Any], int]:
        attempts = 0
        retries = 0
        max_tries = 1 + self.config.listing_retries
        last: Dict[str, Any] = {"success": False, "error": "not_started"}

        while attempts < max_tries:
            attempts += 1
            try:
                if text and not url:
                    last = pipeline.analyse_listing(
                        raw_text=text,
                        listing_url=None,
                        source="manual_text",
                        overrides=self.overrides,
                        filters=self.filters,
                        use_llm=self.use_llm,
                        job_id=self.job_id,
                        persist=True,
                    )
                else:
                    last = pipeline.process_listing_url(
                        url=url or "",
                        overrides=self.overrides,
                        filters=self.filters,
                        use_llm=False,
                        job_id=self.job_id,
                        persist=True,
                    )
                if last.get("property_id"):
                    return merge_pipeline_result(last), retries
                if last.get("terminal_status") in ("duplicate", "filtered_out"):
                    return merge_pipeline_result(last), retries
                if last.get("extraction_failed") and last.get("property_id"):
                    return last, retries
                if attempts >= max_tries:
                    if url and not last.get("property_id"):
                        last = pipeline.persist_extraction_failed(
                            listing_url=url,
                            job_id=self.job_id,
                            extracted=last.get("extracted") or {},
                            error=last.get("error") or "max_retries_exceeded",
                        )
                    return last, retries
                if not self.config.enabled:
                    return last, retries
                retries += 1
                trace_event(
                    TRACE_RETRIED,
                    job_id=self.job_id,
                    url=url,
                    listing_index=idx,
                    attempt=attempts,
                    max_tries=max_tries,
                )
                log.info(
                    "laundry.sequencer listing retry job_id=%s idx=%s attempt=%s/%s",
                    self.job_id,
                    idx,
                    attempts,
                    max_tries,
                )
                time.sleep(min(attempts, 2))
            except Exception as exc:
                log.exception("Listing %s failed: %s", url or "<inline>", exc)
                last = {
                    "success": False,
                    "url": url,
                    "error": str(exc),
                    "traceback": _tb.format_exc(limit=8),
                }
                if url:
                    last = pipeline.persist_extraction_failed(
                        listing_url=url,
                        job_id=self.job_id,
                        extracted={},
                        error=str(exc),
                    )
                if attempts >= max_tries:
                    return last, retries
                retries += 1

        return last, retries

    def _maybe_upgrade_to_manual_review(self, res: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config.prefer_manual_over_reject:
            return res
        scoring = res.get("scoring") or {}
        if scoring.get("deal_status") != "rejected":
            return res
        score = scoring.get("score")
        min_review = (self.config.scoring_overrides.get("thresholds") or {}).get("manual_review_min", 35)
        if score is not None and float(score) >= float(min_review) - 5:
            scoring = dict(scoring)
            scoring["deal_status"] = "manual_review"
            scoring["verdict"] = "MANUAL REVIEW"
            res = dict(res)
            res["scoring"] = scoring
        return res

    def _run_export_background(self) -> None:
        laundry_store.start_step(self.job_id, laundry_store.JOB_STEP_EXPORT)
        try:
            meta = self._generate_export_file()
            if meta:
                laundry_store.finish_step(
                    self.job_id,
                    laundry_store.JOB_STEP_EXPORT,
                    status=laundry_store.STEP_SUCCESS,
                    output=meta,
                )
                laundry_store.update_job(self.job_id, generate_excel=True)
            else:
                laundry_store.finish_step(
                    self.job_id,
                    laundry_store.JOB_STEP_EXPORT,
                    status=laundry_store.STEP_SKIPPED,
                    output={"reason": "no_properties_to_export"},
                )
        except Exception as exc:
            log.warning("laundry.sequencer export failed job_id=%s: %s", self.job_id, exc)
            laundry_store.finish_step(
                self.job_id,
                laundry_store.JOB_STEP_EXPORT,
                status=laundry_store.STEP_FAILED,
                error_message=str(exc)[:500],
            )

    def _generate_export_file(self) -> Optional[Dict[str, Any]]:
        if not self.config.auto_export:
            return None
        properties, analyses = laundry_store.list_properties_for_export(job_id=self.job_id, limit=500)
        listing_rows = laundry_store.get_listing_results(self.job_id)
        summary = laundry_store.build_scan_summary(self.job, listing_rows, properties)
        label = f"Scan {self.job_id[:8]} · Autonomous pipeline"
        meta = exports.generate_pipeline_export(
            properties,
            analyses,
            label=label,
            job=self.job,
        )
        accounting_meta = exports.generate_listing_accounting_export(
            listing_rows,
            label=f"Scan {self.job_id[:8]} · All Listings",
            summary=summary,
            job=self.job,
        )
        ok, record, err = laundry_store.create_export_record(
            file_path=meta["file_path"],
            size_bytes=meta["size_bytes"],
            fmt=meta.get("format") or "excel",
            export_type="scan_autonomous",
            label=label,
            job_id=self.job_id,
        )
        if not ok or not record:
            raise RuntimeError(err or "export_persist_failed")
        return {
            "export_id": record.get("id"),
            "file_path": record.get("file_path"),
            "row_count": meta.get("row_count"),
            "download_url": record.get("download_url"),
            "listing_accounting_export": accounting_meta,
        }

    def _step_summarize(self, export_meta: Optional[Dict[str, Any]]) -> str:
        laundry_store.start_step(self.job_id, laundry_store.JOB_STEP_SUMMARY)
        listing_rows = laundry_store.get_listing_results(self.job_id)
        self._diagnostics = reconcile_diagnostics(self._diagnostics, listing_rows)
        self._diagnostics.listings_retried = self._retried_count
        persisted_count = len([r for r in listing_rows if r.get("property_id")])
        scored_anything = (
            self.counters["approved"] + self.counters["manual_review"] + self.counters["rejected"]
        ) > 0
        has_cards = persisted_count > 0

        if not self._diagnostics.invariant_ok:
            log.error(
                "laundry.sequencer invariant broken job_id=%s found=%s accounted=%s delta=%s",
                self.job_id,
                self._diagnostics.listings_found,
                self._diagnostics.listings_processed
                + self._diagnostics.listings_failed
                + self._diagnostics.listings_skipped,
                self._diagnostics.invariant_delta,
            )

        if self.counters["done"] > 0 and not has_cards and self.counters.get("skipped", 0) < self.counters["done"]:
            final_status = JOB_FAILED
            finish_error = (
                "Scan processed listings but no property rows were persisted. "
                "Check Supabase connectivity and laundry/schema.sql migrations."
            )
        elif has_cards or scored_anything or self._diagnostics.listings_found > 0:
            final_status = JOB_SUCCESS
            finish_error = None
        else:
            final_status = JOB_NO_RESULTS
            finish_error = "Worker processed listings but every one was skipped or failed to score."

        availability_note = availability_message(
            requested_limit=self.requested_limit,
            discovered_count=self._diagnostics.discovered_count,
            source_available_count=self._diagnostics.source_available_count,
        )

        summary = {
            "approved_count": self.counters["approved"],
            "manual_review_count": self.counters["manual_review"],
            "rejected_count": self.counters["rejected"],
            "failed_count": self.counters["failed"],
            "extraction_failed_count": self.counters["extraction_failed"],
            "skipped_count": self._diagnostics.listings_skipped,
            "deduped_count": self._diagnostics.listings_deduped,
            "resumed_count": self.counters.get("resumed", 0),
            "total": self.requested_limit,
            "listings_found": self._diagnostics.listings_found,
            "listings_queued": self._diagnostics.listings_queued,
            "listings_processed": self._diagnostics.listings_processed,
            "listings_failed_count": self._diagnostics.listings_failed,
            "listings_skipped": self._diagnostics.listings_skipped,
            "listings_retried": self._retried_count,
            "listings_truncated": self._diagnostics.listings_truncated,
            "requested_limit": self.requested_limit,
            "effective_limit": self._diagnostics.effective_limit,
            "discovered_count": self._diagnostics.discovered_count,
            "source_available_count": self._diagnostics.source_available_count,
            "source_found_count": self._diagnostics.source_available_count,
            "queued_count": self._diagnostics.listings_queued,
            "processed_count": self._diagnostics.listings_processed,
            "success_count": self._diagnostics.success_count,
            "duplicate_count": self._diagnostics.duplicate_count,
            "filtered_out_count": self._diagnostics.filtered_out_count,
            "exported_count": (export_meta or {}).get("row_count") if export_meta else 0,
            "availability_message": availability_note,
            "persisted_count": persisted_count,
            "listing_result_count": len(listing_rows),
            "elapsed_sec": round(time.monotonic() - self.started, 2),
            "autonomous": self.config.to_dict(),
            "diagnostics": self._diagnostics.to_dict(),
            "invariant_ok": self._diagnostics.invariant_ok,
            "export": export_meta,
        }
        laundry_store.finish_step(
            self.job_id,
            laundry_store.JOB_STEP_SUMMARY,
            status=laundry_store.STEP_SUCCESS,
            output=summary,
        )
        laundry_store.update_job(
            self.job_id,
            status=final_status,
            progress_pct=100,
            finished_at=job_store._now(),
            summary=summary,
            error_message=finish_error,
            listings_done=self.counters.get("done", 0),
            listings_total=self.requested_limit,
            listings_failed=self._diagnostics.listings_failed,
        )
        log.info(
            "laundry.sequencer finished job_id=%s status=%s persisted=%s autonomous=%s",
            self.job_id,
            final_status,
            persisted_count,
            self.config.operation_mode,
        )
        return final_status

    def _handle_cancel(self, idx: int) -> None:
        log.info("laundry.sequencer cancelled job_id=%s after=%s", self.job_id, idx)
        laundry_store.finish_step(
            self.job_id,
            laundry_store.JOB_STEP_UNDERWRITE,
            status=laundry_store.STEP_SKIPPED,
            output={"cancelled_after": idx},
        )
        laundry_store.update_job(self.job_id, status="cancelled", finished_at=job_store._now())

    def _finalize_no_results(self, reason: str) -> None:
        laundry_store.set_job_counters(
            self.job_id,
            listings_total=self.counters.get("total", 0),
            listings_done=self.counters.get("done", 0),
            listings_failed=self.counters.get("failed", 0),
            approved_count=self.counters.get("approved", 0),
            manual_review_count=self.counters.get("manual_review", 0),
            rejected_count=self.counters.get("rejected", 0),
            progress_pct=100,
        )
        laundry_store.update_job(
            self.job_id,
            status=JOB_NO_RESULTS,
            finished_at=job_store._now(),
            error_message=reason,
        )

    def _finalize_failed(self, error: str) -> None:
        laundry_store.set_job_counters(
            self.job_id,
            listings_total=self.counters.get("total", 0),
            listings_done=self.counters.get("done", 0),
            listings_failed=self.counters.get("failed", 0),
            approved_count=self.counters.get("approved", 0),
            manual_review_count=self.counters.get("manual_review", 0),
            rejected_count=self.counters.get("rejected", 0),
            progress_pct=100,
        )
        laundry_store.update_job(
            self.job_id,
            status=JOB_FAILED,
            finished_at=job_store._now(),
            error_message=error,
        )

    def _touch_heartbeat(self) -> None:
        try:
            job_store.touch_heartbeat(self.job_id, self.worker_id)
        except Exception:
            pass

    def _final_response(self, status: str) -> Dict[str, Any]:
        return {
            "success": status in (JOB_SUCCESS, JOB_NO_RESULTS),
            "job_id": self.job_id,
            "status": status,
        }


def _classify_listing_row(row: Dict[str, Any]) -> str:
    status = (row.get("status") or "").lower()
    bucket = accounting_bucket(status)
    if bucket == "duplicate":
        return "duplicate"
    if bucket == "filtered_out":
        return "filtered_out"
    if status == EXTRACTION_FAILED or row.get("deal_status") == EXTRACTION_FAILED:
        return "extraction_failed"
    if bucket == "failed" or status == "failed":
        return "failed"
    if status == "skipped":
        code = row.get("reason_code") or (row.get("result") or {}).get("skip_reason") or "skipped"
        legacy_bucket = accounting_bucket(resolve_legacy_skip(str(code))[0])
        return legacy_bucket if legacy_bucket in ("duplicate", "filtered_out") else "failed"
    ds = row.get("deal_status")
    if not row.get("property_id"):
        return "failed"
    if ds == "approved_candidate":
        return "approved"
    if ds == "manual_review":
        return "manual_review"
    return "rejected"


def _deal_status(res: Dict[str, Any]) -> Optional[str]:
    if res.get("extraction_failed"):
        return EXTRACTION_FAILED
    return (res.get("scoring") or {}).get("deal_status")


def _classify_result(res: Dict[str, Any]) -> str:
    if not isinstance(res, dict):
        return "failed"
    res = merge_pipeline_result(res)
    terminal = res.get("status") or res.get("terminal_status")
    if terminal:
        bucket = accounting_bucket(str(terminal))
        if bucket == "duplicate":
            return "duplicate"
        if bucket == "filtered_out":
            return "filtered_out"
        if bucket == "failed":
            if terminal == EXTRACTION_FAILED or res.get("extraction_failed"):
                return "extraction_failed"
            return "failed"
    if res.get("duplicate"):
        return "duplicate"
    if res.get("extraction_failed") and res.get("property_id"):
        return "extraction_failed"
    if not res.get("property_id"):
        return "failed"
    ds = _deal_status(res)
    if ds == "approved_candidate":
        return "approved"
    if ds == "manual_review":
        return "manual_review"
    return "rejected"


def _listing_row_status(res: Dict[str, Any]) -> str:
    if not isinstance(res, dict):
        return "failed"
    merged = merge_pipeline_result(res)
    return merged.get("status") or merged.get("terminal_status") or "failed"


def _extracted(res: Dict[str, Any]) -> Dict[str, Any]:
    return res.get("extracted") or {}


def _record_listing(
    job_id: str,
    idx: int,
    url: Optional[str],
    res: Dict[str, Any],
) -> bool:
    res = merge_pipeline_result(res)
    extracted = _extracted(res)
    deal_status = _deal_status(res)
    outcome = dict(res)
    outcome.setdefault("listing_url", url)
    outcome.setdefault("deal_status", deal_status)
    outcome.setdefault("score", (res.get("scoring") or {}).get("score"))
    result_payload = {
        "verdict": (res.get("scoring") or {}).get("verdict"),
        "classification": (res.get("scoring") or {}).get("classification"),
        "preferred_market": (res.get("scoring") or {}).get("preferred_market"),
        "address": extracted.get("address"),
        "city": extracted.get("city"),
        "neighbourhood": extracted.get("neighbourhood"),
        "title": extracted.get("title"),
        "description": extracted.get("description"),
        "floor_area_m2": extracted.get("floor_area_m2") or (res.get("economics") or {}).get("floor_area_m2"),
        "asking_price": extracted.get("asking_price"),
        "asking_rent_month": extracted.get("asking_rent_month"),
        "ebitda_eur": (res.get("economics") or {}).get("ebitda_eur"),
        "payback_years": (res.get("economics") or {}).get("payback_years"),
        "analysis_id": res.get("analysis_id"),
    }
    outcome.update(result_payload)
    return laundry_store.record_listing_outcome(
        job_id,
        idx,
        listing_url=url,
        outcome=outcome,
        property_id=res.get("property_id"),
        deal_status=deal_status,
        score=(res.get("scoring") or {}).get("score"),
        address=extracted.get("address"),
        city=extracted.get("city"),
        neighbourhood=extracted.get("neighbourhood"),
        title=extracted.get("title"),
        description=extracted.get("description"),
    )
