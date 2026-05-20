"""Pipeline constants for K.U.A. async scan orchestration."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Job-level statuses
# ---------------------------------------------------------------------------
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

TERMINAL_JOB_STATUSES = {JOB_SUCCESS, JOB_FAILED, JOB_CANCELLED, JOB_TIMEOUT}
ACTIVE_JOB_STATUSES = {JOB_PENDING, JOB_QUEUED, JOB_RUNNING, JOB_RETRYING}

# ---------------------------------------------------------------------------
# Step-level statuses
# ---------------------------------------------------------------------------
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_SUCCESS = "success"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"
STEP_RETRYING = "retrying"
STEP_TIMEOUT = "timeout"

# ---------------------------------------------------------------------------
# Canonical pipeline steps (order matters)
# ---------------------------------------------------------------------------
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

JOB_LEVEL_STEPS = {"collect_listing_urls", "export_artifacts", "notify_frontend"}

LISTING_LEVEL_STEPS = [s for s in PIPELINE_STEPS if s not in JOB_LEVEL_STEPS]

# ---------------------------------------------------------------------------
# Retry / timeout policy
# ---------------------------------------------------------------------------
DEFAULT_MAX_RETRIES = 3
DEFAULT_STEP_MAX_ATTEMPTS = 3

# Worker loop cadence
WORKER_POLL_INTERVAL_SEC = 2.0
WORKER_HEARTBEAT_INTERVAL_SEC = 10.0

# A job is considered "stuck" if its heartbeat is older than this.
# Set generously to allow long scrapes; the dead-job sweeper uses this.
JOB_HEARTBEAT_STALE_SEC = 180

# Total job wall-clock timeout (defends against forever-stuck jobs).
WORKER_JOB_TIMEOUT_SEC = 1800  # 30 minutes

# Per-step wall-clock timeouts (seconds). Steps not listed default to 120s.
STEP_TIMEOUTS_SEC = {
    "collect_listing_urls": 180,
    "scrape_listing": 90,
    "extract_property_data": 120,
    "validate_extraction": 10,
    "calculate_economics": 30,
    "score_property": 60,
    "classify_deal": 5,
    "generate_memo": 180,
    "save_to_supabase": 30,
    "export_artifacts": 120,
    "notify_frontend": 5,
}
DEFAULT_STEP_TIMEOUT_SEC = 120

# Backoff between attempts
RETRY_BASE_DELAY_SEC = 2.0
RETRY_MAX_DELAY_SEC = 30.0

# ---------------------------------------------------------------------------
# Transient (retryable) error patterns
# ---------------------------------------------------------------------------
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
    "remote end closed",
    "read timed out",
)
