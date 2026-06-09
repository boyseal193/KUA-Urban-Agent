-- =============================================================================
-- K.U.A. LAUNDRY ACQUISITION ENGINE — Supabase / PostgreSQL schema
--
-- WHAT THIS DOES
--   Creates every `laundry_*` table the production laundromat vertical writes to
--   via `laundry/store.py`, `laundry/worker.py`, and `laundry/api.py`.
--
--   Also patches the SHARED pipeline tables already used by the storage vertical:
--     * scan_jobs
--     * scan_steps
--     * scan_listing_results
--     * generated_memos   (storage vertical — left untouched except grants)
--
-- HOW TO USE
--   1. Run `jobs/schema.sql` first if scan_jobs / scan_steps do not exist yet.
--   2. Supabase → SQL Editor → paste this entire file → Run.
--   3. Verify: GET /laundry/health → "laundry_schema": "ready"
--   4. Re-queue failed scans: POST /laundry/scans/{job_id}/resume
--
-- Idempotent — safe to re-run.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- updated_at helper (idempotent — also defined in jobs/schema.sql)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.kua_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- laundry_properties
-- Master row per discovered / underwritten listing.
-- Written by: store.upsert_property, store.create_partial_property
-- Read by:    store.list_properties, store.list_job_properties, pipeline
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_properties (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source                   TEXT NOT NULL DEFAULT 'scan',
    job_id                   UUID,
    listing_url              TEXT,
    dedupe_key               TEXT NOT NULL,

    address                  TEXT,
    city                     TEXT DEFAULT 'Barcelona',
    neighbourhood            TEXT,
    lat                      DOUBLE PRECISION,
    lng                      DOUBLE PRECISION,

    property_type            TEXT,
    acquisition_type         TEXT,
    floor_area_m2            DOUBLE PRECISION,
    asking_price             DOUBLE PRECISION,
    asking_rent_month        DOUBLE PRECISION,

    washer_count             INTEGER,
    dryer_count              INTEGER,

    expected_revenue_eur     DOUBLE PRECISION,
    ebitda_eur               DOUBLE PRECISION,
    operating_margin         DOUBLE PRECISION,
    payback_years            DOUBLE PRECISION,

    score                    INTEGER NOT NULL DEFAULT 0,
    verdict                  TEXT,
    classification           TEXT,
    deal_status              TEXT NOT NULL DEFAULT 'rejected',

    in_preferred_market      BOOLEAN NOT NULL DEFAULT FALSE,
    matched_neighbourhood    TEXT,

    raw_extracted            JSONB,

    deleted_at               TIMESTAMPTZ,
    deletion_reason          TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ
);

ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS source                   TEXT NOT NULL DEFAULT 'scan';
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS job_id                   UUID;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS listing_url              TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS dedupe_key               TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS address                  TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS city                     TEXT DEFAULT 'Barcelona';
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS neighbourhood            TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS lat                      DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS lng                      DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS property_type            TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS acquisition_type         TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS floor_area_m2            DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS asking_price             DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS asking_rent_month        DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS washer_count             INTEGER;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS dryer_count              INTEGER;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS expected_revenue_eur     DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS ebitda_eur               DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS operating_margin         DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS payback_years          DOUBLE PRECISION;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS score                    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS verdict                  TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS classification           TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS deal_status              TEXT NOT NULL DEFAULT 'rejected';
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS in_preferred_market      BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS matched_neighbourhood    TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS raw_extracted            JSONB;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS deleted_at               TIMESTAMPTZ;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS deletion_reason          TEXT;
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_properties ADD COLUMN IF NOT EXISTS updated_at               TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_laundry_properties_dedupe
    ON public.laundry_properties (dedupe_key)
    WHERE deleted_at IS NULL AND dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_status
    ON public.laundry_properties (deal_status)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_city_hood
    ON public.laundry_properties (city, neighbourhood)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_score
    ON public.laundry_properties (score DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_job
    ON public.laundry_properties (job_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_listing_url
    ON public.laundry_properties (listing_url)
    WHERE deleted_at IS NULL AND listing_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_laundry_properties_deleted_at
    ON public.laundry_properties (deleted_at);

DROP TRIGGER IF EXISTS trg_laundry_properties_updated ON public.laundry_properties;
CREATE TRIGGER trg_laundry_properties_updated
    BEFORE UPDATE ON public.laundry_properties
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- laundry_analyses
-- Versioned underwriting output per property (memo lives in memo_md).
-- Written by: store.insert_analysis
-- Read by:    store.get_property, store.list_job_properties
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_analyses (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id              UUID NOT NULL,
    extracted                JSONB,
    economics                JSONB,
    scoring                  JSONB,
    location                 JSONB,
    due_diligence            JSONB,
    memo_md                  TEXT,
    assumptions_version      TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ,
    deleted_at               TIMESTAMPTZ
);

ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS property_id         UUID;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS extracted           JSONB;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS economics           JSONB;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS scoring             JSONB;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS location            JSONB;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS due_diligence       JSONB;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS memo_md             TEXT;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS assumptions_version TEXT;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS updated_at         TIMESTAMPTZ;
ALTER TABLE public.laundry_analyses ADD COLUMN IF NOT EXISTS deleted_at         TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_laundry_analyses_property
    ON public.laundry_analyses (property_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_laundry_analyses_deleted_at
    ON public.laundry_analyses (deleted_at);

DROP TRIGGER IF EXISTS trg_laundry_analyses_updated ON public.laundry_analyses;
CREATE TRIGGER trg_laundry_analyses_updated
    BEFORE UPDATE ON public.laundry_analyses
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- laundry_generated_memos
-- Optional memo archive (primary memo path is laundry_analyses.memo_md).
-- Compatible with backend/app/laundry ORM and future LLM polish flows.
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_generated_memos (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id              UUID NOT NULL,
    analysis_id              UUID,
    kind                     TEXT NOT NULL DEFAULT 'ic_memo',
    markdown                 TEXT NOT NULL DEFAULT '',
    polished                 BOOLEAN NOT NULL DEFAULT FALSE,
    token_count              INTEGER,
    model                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ,
    deleted_at               TIMESTAMPTZ
);

ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS property_id  UUID;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS analysis_id  UUID;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS kind         TEXT NOT NULL DEFAULT 'ic_memo';
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS markdown     TEXT NOT NULL DEFAULT '';
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS polished     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS token_count  INTEGER;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS model        TEXT;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ;
ALTER TABLE public.laundry_generated_memos ADD COLUMN IF NOT EXISTS deleted_at  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_laundry_generated_memos_property
    ON public.laundry_generated_memos (property_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_laundry_generated_memos_analysis
    ON public.laundry_generated_memos (analysis_id);

CREATE INDEX IF NOT EXISTS idx_laundry_generated_memos_deleted_at
    ON public.laundry_generated_memos (deleted_at);

DROP TRIGGER IF EXISTS trg_laundry_generated_memos_updated ON public.laundry_generated_memos;
CREATE TRIGGER trg_laundry_generated_memos_updated
    BEFORE UPDATE ON public.laundry_generated_memos
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- laundry_exports
-- Export artefact ledger (Excel / PDF paths written by export jobs).
-- job_id references shared scan_jobs (job_type = 'laundry_scan').
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_exports (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                   UUID,
    property_id              UUID,
    format                   TEXT NOT NULL DEFAULT 'xlsx',
    file_path                TEXT NOT NULL,
    size_bytes               INTEGER NOT NULL DEFAULT 0,
    created_by               TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ,
    deleted_at               TIMESTAMPTZ
);

ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS job_id      UUID;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS property_id UUID;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS format      TEXT NOT NULL DEFAULT 'xlsx';
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS file_path   TEXT;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS size_bytes  INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS created_by  TEXT;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE public.laundry_exports ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_laundry_exports_job_id
    ON public.laundry_exports (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_laundry_exports_property_id
    ON public.laundry_exports (property_id);

CREATE INDEX IF NOT EXISTS idx_laundry_exports_deleted_at
    ON public.laundry_exports (deleted_at);

DROP TRIGGER IF EXISTS trg_laundry_exports_updated ON public.laundry_exports;
CREATE TRIGGER trg_laundry_exports_updated
    BEFORE UPDATE ON public.laundry_exports
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- laundry_duplicates
-- Records collapsed duplicate listings (dedupe_key collisions).
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_duplicates (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dedupe_key               TEXT NOT NULL,
    property_id              UUID NOT NULL,
    listing_url              TEXT,
    primary_property_id      UUID,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ
);

ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS dedupe_key          TEXT;
ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS property_id         UUID;
ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS listing_url         TEXT;
ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS primary_property_id UUID;
ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_duplicates ADD COLUMN IF NOT EXISTS updated_at         TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_laundry_duplicates_dedupe_key
    ON public.laundry_duplicates (dedupe_key);

CREATE INDEX IF NOT EXISTS idx_laundry_duplicates_property_id
    ON public.laundry_duplicates (property_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_duplicates'
           AND constraint_name = 'uq_laundry_dup_key_pid'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_duplicates
                ADD CONSTRAINT uq_laundry_dup_key_pid
                UNIQUE (dedupe_key, property_id);
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped uq_laundry_dup_key_pid: %', SQLERRM;
        END;
    END IF;
END$$;

DROP TRIGGER IF EXISTS trg_laundry_duplicates_updated ON public.laundry_duplicates;
CREATE TRIGGER trg_laundry_duplicates_updated
    BEFORE UPDATE ON public.laundry_duplicates
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();


-- =============================================================================
-- laundry_audit_logs
-- Operator actions: delete, restore, rescore, settings change.
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_audit_logs (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor                    TEXT,
    action                   TEXT NOT NULL,
    entity_type              TEXT NOT NULL,
    entity_id                TEXT,
    payload                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id               TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS actor       TEXT;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS action      TEXT;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS entity_type TEXT;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS entity_id   TEXT;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS payload     JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS request_id  TEXT;
ALTER TABLE public.laundry_audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_laundry_audit_logs_created_at
    ON public.laundry_audit_logs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_laundry_audit_logs_entity
    ON public.laundry_audit_logs (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_laundry_audit_logs_action
    ON public.laundry_audit_logs (action);


-- =============================================================================
-- laundry_errors
-- Structured pipeline errors (per scan job / listing URL).
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_errors (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                   UUID,
    listing_url              TEXT,
    error_type               TEXT NOT NULL DEFAULT 'unknown',
    message                  TEXT NOT NULL DEFAULT '',
    traceback                TEXT,
    retryable                BOOLEAN NOT NULL DEFAULT TRUE,
    attempt                  INTEGER NOT NULL DEFAULT 1,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS job_id      UUID;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS listing_url TEXT;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS error_type  TEXT;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS message     TEXT;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS traceback   TEXT;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS retryable   BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS attempt     INTEGER NOT NULL DEFAULT 1;
ALTER TABLE public.laundry_errors ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_laundry_errors_job_id
    ON public.laundry_errors (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_laundry_errors_listing_url
    ON public.laundry_errors (listing_url);


-- =============================================================================
-- laundry_settings
-- Persisted assumption overrides (see laundry/assumptions.py).
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.laundry_settings (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id              TEXT NOT NULL DEFAULT 'default',
    overrides                JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.laundry_settings ADD COLUMN IF NOT EXISTS operator_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.laundry_settings ADD COLUMN IF NOT EXISTS overrides  JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.laundry_settings ADD COLUMN IF NOT EXISTS notes      TEXT;
ALTER TABLE public.laundry_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.laundry_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS idx_laundry_settings_operator
    ON public.laundry_settings (operator_id);

DROP TRIGGER IF EXISTS trg_laundry_settings_updated ON public.laundry_settings;
CREATE TRIGGER trg_laundry_settings_updated
    BEFORE UPDATE ON public.laundry_settings
    FOR EACH ROW EXECUTE FUNCTION public.kua_set_updated_at();

INSERT INTO public.laundry_settings (operator_id, overrides)
VALUES ('default', '{}'::jsonb)
ON CONFLICT (operator_id) DO NOTHING;


-- =============================================================================
-- FOREIGN KEYS (guarded — safe when parent tables already exist)
-- =============================================================================

-- laundry_properties.job_id → scan_jobs
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name = 'scan_jobs'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_properties'
           AND constraint_name = 'laundry_properties_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_properties
                ADD CONSTRAINT laundry_properties_job_id_fkey
                FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_properties_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- laundry_analyses.property_id → laundry_properties
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_analyses'
           AND constraint_name = 'laundry_analyses_property_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_analyses
                ADD CONSTRAINT laundry_analyses_property_id_fkey
                FOREIGN KEY (property_id) REFERENCES public.laundry_properties(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_analyses_property_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- laundry_generated_memos → laundry_properties / laundry_analyses
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_generated_memos'
           AND constraint_name = 'laundry_generated_memos_property_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_generated_memos
                ADD CONSTRAINT laundry_generated_memos_property_id_fkey
                FOREIGN KEY (property_id) REFERENCES public.laundry_properties(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_generated_memos_property_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_generated_memos'
           AND constraint_name = 'laundry_generated_memos_analysis_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_generated_memos
                ADD CONSTRAINT laundry_generated_memos_analysis_id_fkey
                FOREIGN KEY (analysis_id) REFERENCES public.laundry_analyses(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_generated_memos_analysis_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- laundry_exports → scan_jobs / laundry_properties
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name = 'scan_jobs'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_exports'
           AND constraint_name = 'laundry_exports_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_exports
                ADD CONSTRAINT laundry_exports_job_id_fkey
                FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_exports_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_exports'
           AND constraint_name = 'laundry_exports_property_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_exports
                ADD CONSTRAINT laundry_exports_property_id_fkey
                FOREIGN KEY (property_id) REFERENCES public.laundry_properties(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_exports_property_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- laundry_duplicates → laundry_properties
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_duplicates'
           AND constraint_name = 'laundry_duplicates_property_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_duplicates
                ADD CONSTRAINT laundry_duplicates_property_id_fkey
                FOREIGN KEY (property_id) REFERENCES public.laundry_properties(id) ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_duplicates_property_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_duplicates'
           AND constraint_name = 'laundry_duplicates_primary_property_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_duplicates
                ADD CONSTRAINT laundry_duplicates_primary_property_id_fkey
                FOREIGN KEY (primary_property_id) REFERENCES public.laundry_properties(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_duplicates_primary_property_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;

-- laundry_errors → scan_jobs
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name = 'scan_jobs'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_schema = 'public'
           AND table_name = 'laundry_errors'
           AND constraint_name = 'laundry_errors_job_id_fkey'
    ) THEN
        BEGIN
            ALTER TABLE public.laundry_errors
                ADD CONSTRAINT laundry_errors_job_id_fkey
                FOREIGN KEY (job_id) REFERENCES public.scan_jobs(id) ON DELETE SET NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipped laundry_errors_job_id_fkey: %', SQLERRM;
        END;
    END IF;
END$$;


-- =============================================================================
-- SHARED PIPELINE TABLES — laundry-specific columns
-- (scan_jobs / scan_steps / scan_listing_results live in jobs/schema.sql)
-- =============================================================================

ALTER TABLE public.scan_jobs ADD COLUMN IF NOT EXISTS summary JSONB;

ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS address       TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS city          TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS neighbourhood TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS title         TEXT;
ALTER TABLE public.scan_listing_results ADD COLUMN IF NOT EXISTS description   TEXT;

CREATE INDEX IF NOT EXISTS idx_scan_jobs_job_type
    ON public.scan_jobs (job_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scan_listing_results_property_id
    ON public.scan_listing_results (property_id)
    WHERE property_id IS NOT NULL;


-- =============================================================================
-- PERMISSIONS + RLS (Supabase PostgREST)
-- =============================================================================
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_properties        TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_analyses          TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_generated_memos   TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_exports           TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_duplicates        TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_audit_logs        TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_errors            TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.laundry_settings          TO service_role;

ALTER TABLE public.laundry_properties        DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_analyses          DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_generated_memos   DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_exports           DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_duplicates        DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_audit_logs        DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_errors            DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.laundry_settings          DISABLE ROW LEVEL SECURITY;


-- =============================================================================
-- DATA MIGRATION — existing laundry scans
--
-- Scans that ran BEFORE this migration have scan_listing_results rows but no
-- laundry_properties rows. Property data cannot be reconstructed without
-- re-scraping listing detail pages — re-queue those jobs after this migration.
-- =============================================================================

-- 1) Backfill denormalized listing fields from the result JSON blob.
UPDATE public.scan_listing_results AS slr
SET
    address       = COALESCE(slr.address,       slr.result->>'address'),
    city          = COALESCE(slr.city,          slr.result->>'city', 'Barcelona'),
    neighbourhood = COALESCE(slr.neighbourhood, slr.result->>'neighbourhood'),
    title         = COALESCE(slr.title,         slr.result->>'title'),
    description   = COALESCE(slr.description,   slr.result->>'description'),
    updated_at    = NOW()
WHERE slr.deleted_at IS NULL
  AND slr.result IS NOT NULL
  AND (
        slr.address IS NULL
     OR slr.city IS NULL
     OR slr.neighbourhood IS NULL
     OR slr.title IS NULL
  );

-- 2) Link scan_listing_results.property_id where a matching laundry_properties row exists.
UPDATE public.scan_listing_results AS slr
SET
    property_id = lp.id::text,
    deal_status = COALESCE(slr.deal_status, lp.deal_status),
    updated_at  = NOW()
FROM public.laundry_properties AS lp
WHERE slr.deleted_at IS NULL
  AND lp.deleted_at IS NULL
  AND slr.job_id = lp.job_id
  AND slr.listing_url IS NOT NULL
  AND lp.listing_url IS NOT NULL
  AND slr.listing_url = lp.listing_url
  AND (slr.property_id IS NULL OR slr.property_id = '');

-- 3) Mirror existing analysis memos into laundry_generated_memos (idempotent).
INSERT INTO public.laundry_generated_memos (property_id, analysis_id, kind, markdown, created_at)
SELECT
    la.property_id,
    la.id,
    'ic_memo',
    COALESCE(la.memo_md, ''),
    la.created_at
FROM public.laundry_analyses AS la
WHERE la.deleted_at IS NULL
  AND COALESCE(la.memo_md, '') <> ''
  AND NOT EXISTS (
        SELECT 1
        FROM public.laundry_generated_memos AS lgm
        WHERE lgm.analysis_id = la.id
          AND lgm.deleted_at IS NULL
  );

-- 4) Record duplicate-key collisions already present in laundry_properties.
INSERT INTO public.laundry_duplicates (dedupe_key, property_id, listing_url, primary_property_id)
SELECT
    lp.dedupe_key,
    lp.id,
    lp.listing_url,
    lp.id
FROM public.laundry_properties AS lp
WHERE lp.deleted_at IS NULL
  AND lp.dedupe_key IS NOT NULL
  AND NOT EXISTS (
        SELECT 1
        FROM public.laundry_duplicates AS ld
        WHERE ld.dedupe_key = lp.dedupe_key
          AND ld.property_id = lp.id
  );

-- 5) Flag laundry scan jobs that have listing telemetry but zero persisted properties.
--    Re-run them via POST /laundry/scans/{job_id}/resume after deploying the worker fix.
UPDATE public.scan_jobs AS sj
SET
    error_message = COALESCE(
        sj.error_message,
        'Pre-migration scan: listing rows exist but no laundry_properties were persisted. Re-queue this job.'
    ),
    updated_at = NOW()
WHERE sj.job_type = 'laundry_scan'
  AND sj.deleted_at IS NULL
  AND COALESCE(sj.listings_done, 0) > 0
  AND NOT EXISTS (
        SELECT 1
        FROM public.laundry_properties AS lp
        WHERE lp.job_id = sj.id
          AND lp.deleted_at IS NULL
  )
  AND EXISTS (
        SELECT 1
        FROM public.scan_listing_results AS slr
        WHERE slr.job_id = sj.id
          AND slr.deleted_at IS NULL
  );


-- Force PostgREST schema cache reload (fixes "Could not find table public.laundry_properties").
NOTIFY pgrst, 'reload schema';
