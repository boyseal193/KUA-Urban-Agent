-- =============================================================================
-- K.U.A. — Pipeline schema migration (Supabase / PostgreSQL)
--
-- WHAT THIS DOES
--   Creates and/or repairs every Supabase table the K.U.A. backend writes to:
--     * scan_jobs
--     * scan_steps
--     * scan_logs
--     * scan_errors
--     * scan_listing_results
--     * generated_memos
--     * extracted_properties
--
--   Adds EVERY column the backend touches via ALTER TABLE ... ADD COLUMN
--   IF NOT EXISTS, so partial / hand-rolled tables get upgraded in place
--   without losing data. Adds indexes and (where data permits) UNIQUE
--   constraints needed by the orchestrator. Safe to run repeatedly.
--
-- HOW TO USE
--   Supabase → SQL Editor → New query → paste this file → Run.
--   Re-running is a no-op for already-correct schemas.
--
-- DESIGN NOTES
--   * No CHECK constraints on status fields — the backend validates them
--     and CHECKs would fail to retrofit if any legacy row violates them.
--   * property_id is TEXT (not UUID) because the backend treats it as an
--     opaque identifier and inserts it from Supabase-side UUID strings.
--   * step_id is UUID with ON DELETE SET NULL so log/error rows survive
--     step deletion.
--   * job_id is UUID with ON DELETE CASCADE so cleanup removes children.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- updated_at helper (idempotent)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.kua_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- scan_jobs
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.scan_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS job_type            TEXT NOT NULL DEFAULT 'idealista_auto';
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS status              TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS created_by          TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS search_url          TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS filters             JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS payload             JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS listing_limit       INT  NOT NULL DEFAULT 10;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS generate_excel      BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS progress_pct        INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS current_step        TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS listings_total      INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS listings_done       INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS listings_failed     INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS approved_count      INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS manual_review_count INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS rejected_count      INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS result_summary      JSONB;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS result              JSONB;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS excel_path          TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS error_message       TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS retry_count         INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS max_retries         INT  NOT NULL DEFAULT 3;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS request_id          TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS worker_id           TEXT;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS last_heartbeat_at   TIMESTAMPTZ;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS started_at          TIMESTAMPTZ;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS finished_at         TIMESTAMPTZ;
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status         ON public.scan_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_created_at     ON public.scan_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_heartbeat      ON public.scan_jobs(last_heartbeat_at);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_created ON public.scan_jobs(status, created_at);

DROP TRIGGER IF EXISTS trg_scan_jobs_updated ON public.scan_jobs;
CREATE TRIGGER trg_scan_jobs_updated
    BEFORE UPDATE ON public.scan_jobs
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- scan_steps  (listing_index = -1 for job-level steps; NULL would break UNIQUE)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.scan_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS job_id          UUID;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS listing_index   INT NOT NULL DEFAULT -1;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS listing_url     TEXT;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS step_key        TEXT NOT NULL DEFAULT '';
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS step_order      INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS status          TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS attempt         INT  NOT NULL DEFAULT 0;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS max_attempts    INT  NOT NULL DEFAULT 3;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS payload         JSONB;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS input_data      JSONB;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS output_data     JSONB;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS result          JSONB;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS error_type      TEXT;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS error_message   TEXT;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS traceback       TEXT;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS retryable       BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS duration_ms     INT;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS started_at      TIMESTAMPTZ;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS finished_at     TIMESTAMPTZ;
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.scan_steps ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- FK + UNIQUE conditionally (skip if data would violate)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_steps'
           AND constraint_name='scan_steps_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_steps
              ADD CONSTRAINT scan_steps_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_steps_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_steps'
           AND constraint_name='scan_steps_job_listing_step_uniq'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_steps
              ADD CONSTRAINT scan_steps_job_listing_step_uniq
              UNIQUE (job_id, listing_index, step_key);
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_steps unique constraint: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_scan_steps_job_id    ON public.scan_steps(job_id);
CREATE INDEX IF NOT EXISTS idx_scan_steps_status    ON public.scan_steps(status);
CREATE INDEX IF NOT EXISTS idx_scan_steps_job_order ON public.scan_steps(job_id, step_order);
CREATE INDEX IF NOT EXISTS idx_scan_steps_created   ON public.scan_steps(created_at DESC);

DROP TRIGGER IF EXISTS trg_scan_steps_updated ON public.scan_steps;
CREATE TRIGGER trg_scan_steps_updated
    BEFORE UPDATE ON public.scan_steps
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- scan_logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.scan_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS job_id     UUID;
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS step_id    UUID;
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS level      TEXT NOT NULL DEFAULT 'info';
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS message    TEXT NOT NULL DEFAULT '';
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS context    JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS payload    JSONB;
ALTER TABLE public.scan_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_logs'
           AND constraint_name='scan_logs_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_logs
              ADD CONSTRAINT scan_logs_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_logs_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_logs'
           AND constraint_name='scan_logs_step_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_logs
              ADD CONSTRAINT scan_logs_step_id_fkey
              FOREIGN KEY (step_id) REFERENCES public.scan_steps(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_logs_step_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_scan_logs_job_id     ON public.scan_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_scan_logs_created_at ON public.scan_logs(job_id, created_at DESC);


-- =============================================================================
-- scan_errors
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.scan_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS job_id      UUID;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS step_id     UUID;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS listing_url TEXT;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS error_type  TEXT NOT NULL DEFAULT 'Unknown';
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS message     TEXT NOT NULL DEFAULT '';
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS traceback   TEXT;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS payload     JSONB;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS retryable   BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS attempt     INT NOT NULL DEFAULT 1;
ALTER TABLE public.scan_errors ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_errors'
           AND constraint_name='scan_errors_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_errors
              ADD CONSTRAINT scan_errors_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_errors_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_errors'
           AND constraint_name='scan_errors_step_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_errors
              ADD CONSTRAINT scan_errors_step_id_fkey
              FOREIGN KEY (step_id) REFERENCES public.scan_steps(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_errors_step_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_scan_errors_job_id     ON public.scan_errors(job_id);
CREATE INDEX IF NOT EXISTS idx_scan_errors_created_at ON public.scan_errors(job_id, created_at DESC);


-- =============================================================================
-- scan_listing_results
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.scan_listing_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS job_id        UUID;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS listing_index INT NOT NULL DEFAULT 0;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS listing_url   TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS property_id   TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS deal_status   TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS score         NUMERIC;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS verdict       TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS result        JSONB;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS payload       JSONB;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_listing_results'
           AND constraint_name='scan_listing_results_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_listing_results
              ADD CONSTRAINT scan_listing_results_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_listing_results_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='scan_listing_results'
           AND constraint_name='scan_listing_results_job_listing_uniq'
    ) THEN
        BEGIN
            ALTER TABLE public.scan_listing_results
              ADD CONSTRAINT scan_listing_results_job_listing_uniq
              UNIQUE (job_id, listing_index);
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped scan_listing_results unique constraint: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_scan_listing_results_job_id ON public.scan_listing_results(job_id);
CREATE INDEX IF NOT EXISTS idx_scan_listing_results_status ON public.scan_listing_results(status);
CREATE INDEX IF NOT EXISTS idx_scan_listing_results_created ON public.scan_listing_results(created_at DESC);

DROP TRIGGER IF EXISTS trg_scan_listing_results_updated ON public.scan_listing_results;
CREATE TRIGGER trg_scan_listing_results_updated
    BEFORE UPDATE ON public.scan_listing_results
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- extracted_properties
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.extracted_properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS job_id      UUID;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS listing_url TEXT;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS property_id TEXT;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS extracted   JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS economics   JSONB;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS score       JSONB;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS result      JSONB;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS payload     JSONB;
ALTER TABLE public.extracted_properties ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='extracted_properties'
           AND constraint_name='extracted_properties_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.extracted_properties
              ADD CONSTRAINT extracted_properties_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped extracted_properties_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_extracted_properties_job_id  ON public.extracted_properties(job_id);
CREATE INDEX IF NOT EXISTS idx_extracted_properties_created ON public.extracted_properties(created_at DESC);


-- =============================================================================
-- generated_memos
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.generated_memos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS job_id      UUID;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS property_id TEXT;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS listing_url TEXT;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS memo_text   TEXT NOT NULL DEFAULT '';
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS verdict     TEXT;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS deal_status TEXT;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS payload     JSONB;
ALTER TABLE public.generated_memos ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='generated_memos'
           AND constraint_name='generated_memos_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.generated_memos
              ADD CONSTRAINT generated_memos_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped generated_memos_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_generated_memos_job_id  ON public.generated_memos(job_id);
CREATE INDEX IF NOT EXISTS idx_generated_memos_created ON public.generated_memos(created_at DESC);


-- =============================================================================
-- export_jobs
-- Tracks every export artifact generated for a scan job (excel, csv, json,
-- memo, zip). One row per (job_id, export_type). Artifacts may be cached in
-- Supabase Storage (file_path = "bucket/path") or regenerated on demand.
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.export_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS job_id          UUID;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS export_type     TEXT NOT NULL DEFAULT 'excel';
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS file_path       TEXT;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS file_name       TEXT;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS mime_type       TEXT;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS size_bytes      BIGINT NOT NULL DEFAULT 0;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS status          TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS error_message   TEXT;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS download_count  INT NOT NULL DEFAULT 0;
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.export_jobs ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='export_jobs'
           AND constraint_name='export_jobs_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.export_jobs
              ADD CONSTRAINT export_jobs_job_id_fkey
              FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped export_jobs_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='export_jobs'
           AND constraint_name='export_jobs_job_id_type_uniq'
    ) THEN
        BEGIN
            ALTER TABLE public.export_jobs
              ADD CONSTRAINT export_jobs_job_id_type_uniq UNIQUE (job_id, export_type);
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped export_jobs_job_id_type_uniq: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_export_jobs_job_id     ON public.export_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_export_jobs_created_at ON public.export_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_export_jobs_status     ON public.export_jobs(status);

CREATE OR REPLACE FUNCTION public.touch_export_jobs_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_export_jobs_updated_at ON public.export_jobs;
CREATE TRIGGER trg_export_jobs_updated_at
BEFORE UPDATE ON public.export_jobs
FOR EACH ROW EXECUTE FUNCTION public.touch_export_jobs_updated_at();


-- =============================================================================
-- properties — dedupe + soft-delete columns
-- The properties table itself is created/owned by the legacy Supabase setup;
-- here we only ADD COLUMN IF NOT EXISTS, so existing rows are preserved.
-- =============================================================================
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS deleted_at              TIMESTAMPTZ;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS deleted_by              TEXT;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS deletion_reason         TEXT;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS dedupe_key              TEXT;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS duplicate_of            UUID;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS merged_into_property_id UUID;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS is_test                 BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS scan_count              INT     NOT NULL DEFAULT 1;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS first_seen_at           TIMESTAMPTZ;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS last_seen_at            TIMESTAMPTZ;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS first_seen_job_id       UUID;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS last_seen_job_id        UUID;

-- Self-referencing FK for duplicate_of (no CASCADE — a deleted duplicate
-- should not nuke the canonical row it points to).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='properties'
           AND constraint_name='properties_duplicate_of_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.properties
              ADD CONSTRAINT properties_duplicate_of_fkey
              FOREIGN KEY (duplicate_of) REFERENCES public.properties(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped properties_duplicate_of_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema='public' AND table_name='properties'
           AND constraint_name='properties_merged_into_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.properties
              ADD CONSTRAINT properties_merged_into_fkey
              FOREIGN KEY (merged_into_property_id) REFERENCES public.properties(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped properties_merged_into_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- Unique partial index: at most one ACTIVE (non-deleted) row per dedupe_key.
-- Soft-deleted rows are exempt so the operator can restore one later.
CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_dedupe_key_active
ON public.properties(dedupe_key)
WHERE deleted_at IS NULL AND dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_properties_deleted_at      ON public.properties(deleted_at);
CREATE INDEX IF NOT EXISTS idx_properties_listing_url     ON public.properties(listing_url) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_properties_duplicate_of    ON public.properties(duplicate_of);
CREATE INDEX IF NOT EXISTS idx_properties_last_seen_at    ON public.properties(last_seen_at DESC);


-- =============================================================================
-- analyses / generated_memos / scan_jobs / scan_listing_results — soft-delete
-- =============================================================================
ALTER TABLE public.analyses              ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.generated_memos       ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.scan_jobs             ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.scan_listing_results  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.extracted_properties  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_analyses_deleted_at             ON public.analyses(deleted_at);
CREATE INDEX IF NOT EXISTS idx_generated_memos_deleted_at      ON public.generated_memos(deleted_at);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_deleted_at            ON public.scan_jobs(deleted_at);
CREATE INDEX IF NOT EXISTS idx_scan_listing_results_deleted_at ON public.scan_listing_results(deleted_at);
CREATE INDEX IF NOT EXISTS idx_extracted_properties_deleted_at ON public.extracted_properties(deleted_at);


-- =============================================================================
-- audit_log — append-only record of deletes / restores / cleanup actions
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS actor         TEXT;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS action        TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS resource_type TEXT;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS resource_id   TEXT;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS payload       JSONB;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS request_id    TEXT;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at   ON public.audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource     ON public.audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action       ON public.audit_log(action);


-- =============================================================================
-- Permissions for the Supabase service role used by the backend
-- =============================================================================
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role;

-- Force PostgREST to reload its schema cache so the new tables/columns are
-- visible to the REST API immediately (otherwise PGRST205 may persist).
NOTIFY pgrst, 'reload schema';
