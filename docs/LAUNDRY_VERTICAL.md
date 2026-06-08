# K.U.A. Laundry Acquisition Engine — Deployment Guide

The laundry vertical is a **completely independent** second division inside
the K.U.A. platform. It coexists with self‑storage and shares only the
following infrastructure with the storage vertical:

- FastAPI app (`backend/app/main.py`) — adds the `/laundry` router; the
  existing `/api/v1` and `/ws/live` storage routes are unchanged.
- ARQ worker (`backend/app/workers/settings.py`) — registers
  `run_laundry_scan_job` alongside `run_idealista_scan_job` so a single
  worker process handles both pipelines.
- PostgreSQL instance — new tables are all prefixed `laundry_*` and never
  reference any storage table.
- Redis instance — used both as ARQ broker and the WebSocket pub/sub
  fan‑out for `/ws/laundry/{job_id}`.
- Auth (Supabase JWT) — every laundry endpoint depends on
  `get_current_user`, the same dependency the storage endpoints use.

Nothing else is shared. There are no cross‑imports between the storage
modules under `backend/app/services|repositories|api/v1` and the laundry
modules under `backend/app/laundry/*`.

---

## 1. New database schema

The Alembic migration is
`backend/alembic/versions/20260601_02_laundry_vertical.py`
(`down_revision = 20260216_01`). It creates ten tables; all of them are
independent and can be dropped/recreated without touching storage data.

| Table | Purpose |
|---|---|
| `laundry_properties` | Master record per discovered listing (address, geocoded coords, asking price/rent, floor area, machine counts, raw listing snapshot, dedupe hash, soft‑delete flag). |
| `laundry_analyses` | Result of the underwriter pass: score, sub‑scores, verdict, economics JSON blob, location intel JSON blob, SWOT/red flags/checklist arrays, confidence, model versions. One‑to‑many with property (history of re‑scores). |
| `laundry_scan_jobs` | Background scan lifecycle (status, totals, request payload, error counts, started/finished timestamps, ARQ job id). |
| `laundry_scan_steps` | Per‑listing audit row inside a scan job: stage, status, message, duration, optional property id. |
| `laundry_generated_memos` | Persisted IC memos & rejection notes (Markdown + optional LLM polish + token counts). |
| `laundry_exports` | Artefact ledger (format, file path on disk, size, originating property/scan). |
| `laundry_audit_logs` | Operator/admin actions (delete, restore, rescore, purge, settings change). |
| `laundry_duplicates` | Records of duplicate listings collapsed into a primary property. |
| `laundry_errors` | Structured error log emitted by the laundry pipeline. |
| `laundry_settings` | Singleton row that stores tunable assumption overrides + notes. |

All tables carry `id UUID PK`, `created_at`, `updated_at`; relevant tables
also carry `deleted_at` for the soft‑delete subsystem.

### Migration SQL (apply once)

```bash
cd backend
alembic upgrade head
```

To roll back **only** the laundry vertical (keeps the storage tables
intact):

```bash
cd backend
alembic downgrade 20260216_01
```

---

## 2. Backend module map

```
backend/app/laundry/
├── __init__.py
├── assumptions.py              # Tunable defaults (machine ft², cycles, OPEX, scoring weights/thresholds)
├── economics.py                # Deterministic financial model (CAPEX, OPEX, revenue, EBITDA, payback, IRR, yield)
├── scoring.py                  # 0‑100 opportunity score + verdict (reject / manual_review / approved_candidate)
├── models.py                   # SQLAlchemy ORM models for the ten laundry_* tables
├── repository.py               # CRUD + KPIs + dedupe + soft delete + settings access
├── ai/
│   ├── __init__.py             # No eager imports — keeps openai/anthropic optional
│   ├── extraction.py           # LLM extraction with regex fallback
│   ├── due_diligence.py        # SWOT / red flags / verification list generator
│   └── memo.py                 # Markdown IC memo (deterministic) + optional LLM polish
├── scanners/
│   └── web.py                  # URL scraping + area search discovery
├── services/
│   ├── normalization.py        # clean / validate / dedupe key / status mapping
│   ├── location_service.py     # Nominatim geocode + Overpass intel (no API keys)
│   ├── pipeline.py             # End‑to‑end underwriter for a single listing
│   └── scan_service.py         # Job orchestration + WS fan‑out + resume support
├── exports/
│   └── builders.py             # Excel / CSV / JSON / ZIP / Markdown memo / full package
├── workers/
│   ├── tasks.py                # `run_laundry_scan_job` ARQ task
│   └── settings.py             # Optional dedicated WorkerSettings (not required if reusing main worker)
└── api/
    ├── schemas.py              # Pydantic IO models for /laundry/*
    └── router.py               # All HTTP endpoints
```

### Endpoint surface — `/laundry/*`

```
GET    /laundry/kpis
GET    /laundry/deals/top                ?limit
GET    /laundry/deals/approved           ?limit
GET    /laundry/deals/manual-review      ?limit
GET    /laundry/deals/rejected           ?limit
GET    /laundry/deals/all                ?limit&status
GET    /laundry/deals/map                ?limit
GET    /laundry/property/{id}
DELETE /laundry/property/{id}            (soft delete)
POST   /laundry/property/{id}/restore
POST   /laundry/property/{id}/memo       (rebuild)
POST   /laundry/property/{id}/rescore    (re‑run economics + scoring)
POST   /laundry/analyse                  (inline URL or raw text)
POST   /laundry/scan                     (launch scan job)
GET    /laundry/scan/jobs                ?limit
GET    /laundry/scan/{job_id}
POST   /laundry/scan/{job_id}/resume
POST   /laundry/exports                  (create artefact)
GET    /laundry/exports                  ?limit
GET    /laundry/exports/formats
GET    /laundry/exports/{export_id}/download
GET    /laundry/admin/stats
POST   /laundry/admin/purge-test         (deletes only rows flagged source='test')
POST   /laundry/admin/bulk-rescore
GET    /laundry/settings
PUT    /laundry/settings
GET    /laundry/location/preview         ?address=...
WS     /ws/laundry/{job_id}              (live progress stream)
```

The router is registered in `backend/app/main.py`:

```python
from app.laundry.api import laundry_router
app.include_router(laundry_router)
```

---

## 3. Frontend module map

```
kua-frontend/src/
├── lib/
│   ├── vertical.ts                       # Vertical metadata + helpers
│   └── api/laundry.ts                    # Typed laundry API client (re‑exported from lib/api/index.ts)
├── hooks/
│   └── use-laundry.ts                    # React Query hooks for every endpoint
├── components/
│   ├── layout/
│   │   ├── sidebar.tsx                   # Refactored: vertical switcher + dynamic nav tree
│   │   └── vertical-switcher.tsx         # NEW
│   └── laundry/
│       ├── laundry-status.tsx            # Status pill (laundry palette)
│       ├── laundry-score-badge.tsx       # Score pill
│       ├── laundry-deal-card.tsx         # Property card (matches storage aesthetic, violet accent)
│       ├── laundry-deal-list.tsx         # List wrapper with loading / empty state
│       ├── laundry-map.tsx               # Leaflet map (cluster + violet markers)
│       └── laundry-map-dynamic.tsx       # SSR‑safe loader
└── app/(dashboard)/laundry/
    ├── page.tsx                          # → /laundry/dashboard
    ├── dashboard/page.tsx
    ├── pipeline/page.tsx
    ├── manual-review/page.tsx
    ├── approved/page.tsx
    ├── rejected/page.tsx
    ├── map/page.tsx
    ├── scan/page.tsx                     # Launcher (property/acq/search type + async toggle)
    ├── scans/page.tsx                    # Job history
    ├── scans/[id]/page.tsx               # Job detail w/ steps + errors
    ├── property/[id]/page.tsx            # Memo + economics + DD + location + exports
    ├── exports/page.tsx                  # Artefact ledger
    └── settings/page.tsx                 # Assumption overrides + bulk rescore + purge
```

The vertical switcher lives in the top of the sidebar; clicking
`Self Storage` or `Laundromats` navigates to the respective landing page
(`/dashboard` or `/laundry/dashboard`). The active vertical is computed
from `pathname` so refreshes and direct links stay in sync.

---

## 4. Worker

The existing ARQ worker started by `arq app.workers.settings.WorkerSettings`
now processes **both** verticals:

```python
# backend/app/workers/settings.py
functions = [run_idealista_scan_job, run_laundry_scan_job]
```

If you want to run the laundry queue on a dedicated process (e.g. on
Railway), use the alternative settings class
`app.laundry.workers.settings.LaundryWorkerSettings`. The two settings
classes can run side‑by‑side because each only registers the tasks it
needs.

Resumability: a scan job stores its full request payload in
`laundry_scan_jobs.request_payload`. The `/laundry/scan/{job_id}/resume`
endpoint re‑enqueues the same payload, so jobs survive Railway restarts,
browser closes, and worker crashes (ARQ also retries transient failures
up to `max_tries = 3`).

---

## 5. Environment variables

No **new** variables are required. The laundry vertical reuses:

| Variable | Used for |
|---|---|
| `DATABASE_URL` | Postgres (async driver) |
| `REDIS_URL` | ARQ broker + WS pub/sub |
| `SECRET_KEY` / Supabase keys | Auth (unchanged) |
| `LLM_PROVIDER` | `openai` / `anthropic` / `local` (optional — falls back to deterministic memos) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM (optional) |
| `EXPORT_DIR` (default `exports/`) | Where artefacts are written; the laundry exports live under `exports/laundry/` |

Geocoding + competition data use the **free** Nominatim + Overpass APIs
(`https://nominatim.openstreetmap.org`, `https://overpass-api.de`).
You should set a custom `User‑Agent` in `app/laundry/services/location_service.py`
if you intend to send heavy production traffic — the current default is
already conservative.

---

## 6. Deployment steps

1. **Pull** the new branch on Railway / your host.
2. **Install** the existing requirements — no new packages required
   (`requirements.txt` is unchanged; `httpx`, `bs4`, `openpyxl` are already
   in the storage dependency set).
3. **Migrate**:
   ```bash
   cd backend
   alembic upgrade head
   ```
4. **Create** the export sub‑directory:
   ```bash
   mkdir -p exports/laundry
   ```
5. **Restart** the API service (gunicorn / uvicorn) and the ARQ worker.
6. **Verify**:
   - `GET /healthz` returns 200.
   - `GET /laundry/kpis` returns a zeroed payload (auth required).
   - The frontend sidebar shows the vertical switcher and the `Laundry
     Intelligence` nav tree when navigating to `/laundry/dashboard`.
7. **Frontend deploy**:
   ```bash
   cd kua-frontend
   pnpm install            # or npm install — no new packages added
   pnpm build && pnpm start
   ```

---

## 7. Testing checklist

### Backend
- [ ] `alembic upgrade head` applies the `20260601_02` revision without
  touching storage tables.
- [ ] `GET /laundry/kpis` returns zeros on a fresh DB.
- [ ] `POST /laundry/analyse` with a manual URL or raw `text` payload
  creates a property + analysis + memo and writes one
  `laundry_audit_logs` row.
- [ ] `POST /laundry/scan` with `async_mode=true` enqueues an ARQ job,
  populates `laundry_scan_steps`, and emits WebSocket events on
  `/ws/laundry/{job_id}`.
- [ ] Re‑running the same listing creates a `laundry_duplicates` row
  instead of a second property.
- [ ] `DELETE /laundry/property/{id}` flips `deleted_at`; the property
  vanishes from KPIs/maps and reappears after
  `POST /laundry/property/{id}/restore`.
- [ ] `POST /laundry/property/{id}/rescore` recomputes economics and
  produces a new `laundry_analyses` row.
- [ ] `POST /laundry/exports` produces a file under
  `exports/laundry/...` and returns a download URL that serves it.
- [ ] `POST /laundry/admin/purge-test` only deletes rows where
  `source = 'test'`.
- [ ] **Storage regression**: `GET /api/v1/properties/kpis`,
  `POST /api/v1/scan/idealista`, and `/ws/live/{scan_id}` still work
  unchanged.

### Frontend
- [ ] Vertical switcher in the sidebar toggles between Self Storage and
  Laundromats without a full reload artifact (router push).
- [ ] `/laundry/dashboard` renders KPI tiles, top approved deals, and
  manual review queue — no React/hydration errors in the console.
- [ ] `/laundry/pipeline` shows three columns (Approved / Manual Review /
  Rejected).
- [ ] `/laundry/scan` launches a scan and, in async mode, navigates to
  `/laundry/scans/{id}` which then live‑updates progress.
- [ ] `/laundry/map` renders Leaflet clusters with violet markers.
- [ ] `/laundry/property/{id}` renders the IC memo, economics tab, due
  diligence tab, location tab, and the export buttons all produce
  downloadable artefacts.
- [ ] `/laundry/settings` saves overrides JSON, bulk rescore updates the
  approved/manual review queues, and purge test data removes test rows.

### Scoring sanity
- [ ] A premium urban listing (high pop density, low competition, low
  rent / m², ≥ 80 m², visible street) lands in 75‑100 → Approved
  Candidate or upper Manual Review.
- [ ] A listing with missing area, missing rent, or no demographics
  lands in Manual Review (NOT auto‑rejected).
- [ ] A loss‑making listing (negative EBITDA, payback > 15 y) lands in
  0‑49 Reject.

---

## 8. Code quality notes

- All laundry modules are typed end‑to‑end, no `Any` in public
  signatures, no `# TODO` markers, no placeholder stubs.
- The LLM provider is imported lazily so the platform works without
  OpenAI / Anthropic configured — the system falls back to the
  deterministic memo + regex extraction path.
- All assumptions (machine footprint, cycles/day, OPEX, scoring
  weights / thresholds) live in `app/laundry/assumptions.py` and can be
  overridden per‑deployment from `laundry_settings.overrides` (UI:
  `/laundry/settings`).
