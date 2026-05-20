"""Pipeline constants for K.U.A. async scan orchestration."""

from __future__ import annotations

# Job-level statuses
JOB_PENDING = "pending"
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_RETRYING = "retrying"
JOB_SUCCESS = "success"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"
JOB_TIMEOUT = "timeout"

JOB_STATUSES = {
    JOB_PENDING,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_RETRYING,
    JOB_SUCCESS,
    JOB_FAILED,
    JOB_CANCELLED,
    JOB_TIMEOUT,
}

# Step-level statuses
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_SUCCESS = "success"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"
STEP_RETRYING = "retrying"

# Canonical pipeline steps (order matters)
PIPELINE_STEPS = [
    "collect_listing_urls",
    "scrape_listing",
    "extract_property_data",
    "validate_extraction",
    "calculate_economics",
    "score_property",
    "classify_deal",
    "generate_memo",
    "save_to_supabase",
    "export_artifacts",
    "notify_frontend",
]

# Steps that run once per job (not per listing)
JOB_LEVEL_STEPS = {"collect_listing_urls", "export_artifacts", "notify_frontend"}

# Steps that run per listing
LISTING_LEVEL_STEPS = [
    s for s in PIPELINE_STEPS if s not in JOB_LEVEL_STEPS
]

DEFAULT_MAX_RETRIES = 3
DEFAULT_STEP_MAX_ATTEMPTS = 3
WORKER_POLL_INTERVAL_SEC = 2.0
WORKER_JOB_TIMEOUT_SEC = 3600
RETRY_BASE_DELAY_SEC = 2.0
RETRY_MAX_DELAY_SEC = 120.0

# Transient error patterns (retryable)
TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "temporarily",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "und_err",
    "network",
    "redis",
    "openai",
    "anthropic",
)
