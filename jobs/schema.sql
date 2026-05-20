-- K.U.A. — Async scan job pipeline schema (Supabase / PostgreSQL)
-- Run once in Supabase SQL Editor.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- scan_jobs — top-level orchestration unit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        TEXT NOT NULL DEFAULT 'idealista_auto',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending','queued','running','retrying',
                        'success','failed','cancelled','timeout'
                    )),
    created_by      TEXT,
    search_url      TEXT,
    filters         JSONB NOT NULL DEFAULT '{}'::jsonb,
    listing_limit   INT NOT NULL DEFAULT 10,
    generate_excel  BOOLEAN NOT NULL DEFAULT TRUE,
    progress_pct    INT NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    current_step    TEXT,
    listings_total  INT NOT NULL DEFAULT 0,
    listings_done   INT NOT NULL DEFAULT 0,
    listings_failed INT NOT NULL DEFAULT 0,
    approved_count  INT NOT NULL DEFAULT 0,
    manual_review_count INT NOT NULL DEFAULT 0,
    rejected_count  INT NOT NULL DEFAULT 0,
    result_summary  JSONB,
    excel_path      TEXT,
    error_message   TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    max_retries     INT NOT NULL DEFAULT 3,
    request_id      TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status ON scan_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_created_at ON scan_jobs(created_at DESC);

-- ---------------------------------------------------------------------------
-- scan_steps — persisted pipeline steps (job-level + per-listing)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    listing_index   INT,
    listing_url     TEXT,
    step_key        TEXT NOT NULL,
    step_order      INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending','running','success','failed',
                        'skipped','retrying'
                    )),
    attempt         INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    input_data      JSONB,
    output_data     JSONB,
    error_type      TEXT,
    error_message   TEXT,
    retryable       BOOLEAN NOT NULL DEFAULT TRUE,
    duration_ms     INT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, listing_index, step_key)
);

CREATE INDEX IF NOT EXISTS idx_scan_steps_job ON scan_steps(job_id, step_order);

-- ---------------------------------------------------------------------------
-- scan_logs — structured observability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    step_id     UUID REFERENCES scan_steps(id) ON DELETE SET NULL,
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    context     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scan_logs_job ON scan_logs(job_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- scan_errors — failure records with tracebacks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_errors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    step_id     UUID REFERENCES scan_steps(id) ON DELETE SET NULL,
    listing_url TEXT,
    error_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    traceback   TEXT,
    retryable   BOOLEAN NOT NULL DEFAULT TRUE,
    attempt     INT NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scan_errors_job ON scan_errors(job_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- scan_listing_results — incremental results for frontend polling
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_listing_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    listing_index   INT NOT NULL,
    listing_url     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    property_id     TEXT,
    deal_status     TEXT,
    score           NUMERIC,
    verdict         TEXT,
    result          JSONB,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, listing_index)
);

CREATE INDEX IF NOT EXISTS idx_scan_listing_results_job ON scan_listing_results(job_id);

-- ---------------------------------------------------------------------------
-- generated_memos — persisted memo artifacts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS generated_memos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES scan_jobs(id) ON DELETE SET NULL,
    property_id     TEXT,
    listing_url     TEXT,
    memo_text       TEXT NOT NULL,
    verdict         TEXT,
    deal_status     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_memos_job ON generated_memos(job_id);

-- ---------------------------------------------------------------------------
-- extracted_properties — raw extraction snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES scan_jobs(id) ON DELETE SET NULL,
    listing_url     TEXT,
    property_id     TEXT,
    extracted       JSONB NOT NULL DEFAULT '{}'::jsonb,
    economics       JSONB,
    score           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extracted_properties_job ON extracted_properties(job_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION kua_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_scan_jobs_updated ON scan_jobs;
CREATE TRIGGER trg_scan_jobs_updated
    BEFORE UPDATE ON scan_jobs
    FOR EACH ROW EXECUTE FUNCTION kua_set_updated_at();

DROP TRIGGER IF EXISTS trg_scan_steps_updated ON scan_steps;
CREATE TRIGGER trg_scan_steps_updated
    BEFORE UPDATE ON scan_steps
    FOR EACH ROW EXECUTE FUNCTION kua_set_updated_at();

DROP TRIGGER IF EXISTS trg_scan_listing_results_updated ON scan_listing_results;
CREATE TRIGGER trg_scan_listing_results_updated
    BEFORE UPDATE ON scan_listing_results
    FOR EACH ROW EXECUTE FUNCTION kua_set_updated_at();
