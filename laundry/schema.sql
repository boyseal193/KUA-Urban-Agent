-- ============================================================================
-- K.U.A. LAUNDRY ACQUISITION ENGINE — Supabase schema
--
-- Run this in the Supabase SQL editor (or `psql`) on the same database the
-- storage pipeline already uses. It only ADDS new objects; it never touches
-- the existing `properties`, `analyses`, `scan_jobs`, or `scan_steps` tables
-- used by the self-storage vertical.
--
-- Idempotent — safe to re-run.
-- ============================================================================

create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
-- laundry_properties
-- ----------------------------------------------------------------------------
create table if not exists public.laundry_properties (
    id                       uuid primary key default gen_random_uuid(),
    source                   text not null default 'scan',
    job_id                   uuid,
    listing_url              text,
    dedupe_key               text not null,

    address                  text,
    city                     text default 'Barcelona',
    neighbourhood            text,
    lat                      double precision,
    lng                      double precision,

    property_type            text,                  -- existing_laundromat | empty_commercial | retail | mixed_use
    acquisition_type         text,                  -- buy | rent
    floor_area_m2            double precision,
    asking_price             double precision,
    asking_rent_month        double precision,

    washer_count             integer,
    dryer_count              integer,

    expected_revenue_eur     double precision,
    ebitda_eur               double precision,
    operating_margin         double precision,
    payback_years            double precision,

    score                    integer not null default 0,
    verdict                  text,
    classification           text,
    deal_status              text not null default 'rejected',

    in_preferred_market      boolean not null default false,
    matched_neighbourhood    text,

    raw_extracted            jsonb,

    deleted_at               timestamptz,
    deletion_reason          text,
    created_at               timestamptz not null default now(),
    updated_at               timestamptz
);

create unique index if not exists idx_laundry_properties_dedupe
    on public.laundry_properties (dedupe_key)
    where deleted_at is null;

create index if not exists idx_laundry_properties_status
    on public.laundry_properties (deal_status)
    where deleted_at is null;

create index if not exists idx_laundry_properties_city_hood
    on public.laundry_properties (city, neighbourhood)
    where deleted_at is null;

create index if not exists idx_laundry_properties_score
    on public.laundry_properties (score desc)
    where deleted_at is null;

create index if not exists idx_laundry_properties_job
    on public.laundry_properties (job_id);


-- ----------------------------------------------------------------------------
-- laundry_analyses (one row per underwriting run — keep history)
-- ----------------------------------------------------------------------------
create table if not exists public.laundry_analyses (
    id                       uuid primary key default gen_random_uuid(),
    property_id              uuid not null references public.laundry_properties(id) on delete cascade,
    extracted                jsonb,
    economics                jsonb,
    scoring                  jsonb,
    location                 jsonb,
    due_diligence            jsonb,
    memo_md                  text,
    assumptions_version      text,
    created_at               timestamptz not null default now(),
    deleted_at               timestamptz
);

create index if not exists idx_laundry_analyses_property
    on public.laundry_analyses (property_id, created_at desc);


-- ----------------------------------------------------------------------------
-- laundry_settings (optional persisted assumption overrides per operator)
-- ----------------------------------------------------------------------------
create table if not exists public.laundry_settings (
    id            uuid primary key default gen_random_uuid(),
    operator_id   text not null default 'default',
    overrides     jsonb not null default '{}'::jsonb,
    updated_at    timestamptz not null default now()
);

create unique index if not exists idx_laundry_settings_operator
    on public.laundry_settings (operator_id);


-- ----------------------------------------------------------------------------
-- scan_jobs: ensure the shared job table is laundry-friendly.
--
-- We re-use the storage `scan_jobs` table by writing rows with
-- job_type = 'laundry_scan'. The columns below already exist in production;
-- the ALTER statements are guarded with IF NOT EXISTS for clean re-runs.
-- ----------------------------------------------------------------------------
alter table public.scan_jobs add column if not exists summary jsonb;

-- (Storage pipeline already creates: id, job_type, status, created_by,
--  search_url, filters, payload, listing_limit, generate_excel, request_id,
--  started_at, finished_at, worker_id, progress_pct, listings_total,
--  listings_processed, error_message, created_at, heartbeat_at.)
