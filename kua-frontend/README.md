# K.U.A. — KLAVE URBAN AGENT · Frontend

Institutional, AI-native acquisitions command surface for Barcelona commercial
real estate and self-storage conversion opportunities. Connects to the
existing **TruTrastero FastAPI** backend (scoring, underwriting, IC memo
generation, Excel export).

---

## Stack

| Layer        | Choice                                                    |
| ------------ | --------------------------------------------------------- |
| Framework    | **Next.js 15** (App Router · React 19 · Server Components) |
| Language     | **TypeScript** (strict)                                   |
| Styling      | **TailwindCSS** + custom design tokens + shadcn primitives |
| Animation    | **Framer Motion**                                         |
| Data fetch   | **TanStack Query v5**                                     |
| State        | **Zustand** (filters)                                     |
| Forms        | **react-hook-form** + **Zod**                             |
| Charts       | **Recharts**                                              |
| Maps         | **Leaflet** + **react-leaflet** + cluster plugin (CARTO Dark Matter tiles, no API key) |
| Icons        | **lucide-react**                                          |
| Auth         | **Custom JWT** via **jose** with HTTP-only cookies + Next.js middleware |
| Notifications| **sonner**                                                |

---

## Architecture

```
kua-frontend/
├─ Dockerfile                 production multi-stage build (Next.js standalone)
├─ vercel.json                Vercel deployment config
├─ railway.json               Railway deployment config
├─ render.yaml                Render IaC config
├─ next.config.ts             output: standalone, security headers
├─ tailwind.config.ts         design tokens (matte black, neon accents, glows)
├─ components.json            shadcn CLI config
├─ src/
│  ├─ middleware.ts                  edge auth guard — protects all routes
│  ├─ app/
│  │  ├─ layout.tsx                  fonts, providers, grid overlays
│  │  ├─ globals.css                 design system + Leaflet overrides
│  │  ├─ page.tsx                    smart redirect: → /dashboard or /login
│  │  ├─ not-found.tsx               cinematic 404
│  │  ├─ error.tsx                   cinematic 500
│  │  ├─ (auth)/
│  │  │  ├─ layout.tsx               animated tactical background
│  │  │  └─ login/page.tsx           AI-terminal style login portal
│  │  ├─ (dashboard)/                ALL protected routes
│  │  │  ├─ layout.tsx               sidebar + topbar + status ticker
│  │  │  ├─ dashboard/page.tsx       Command (KPIs, radar, system activity)
│  │  │  ├─ pipeline/page.tsx        Kanban + table pipeline view
│  │  │  ├─ scan/page.tsx            Live scan launcher + feed
│  │  │  ├─ map/page.tsx             Tactical Leaflet map
│  │  │  ├─ intelligence/page.tsx    Portfolio analytics
│  │  │  └─ deals/[id]/page.tsx      Deal dossier (memo, economics, score, map, notes)
│  │  └─ api/
│  │     ├─ auth/
│  │     │  ├─ login/route.ts        POST credentials → sets HTTP-only JWT cookie
│  │     │  ├─ logout/route.ts       Clears cookie
│  │     │  └─ session/route.ts      Returns current operator
│  │     └─ proxy/[...path]/route.ts Universal authenticated reverse-proxy → FastAPI
│  ├─ components/
│  │  ├─ ui/         shadcn-style primitives (button, card, dialog, …)
│  │  ├─ auth/       LoginForm, AuthGuard, AuthBackground, SessionIndicator
│  │  ├─ layout/     Sidebar, Topbar, StatusTicker, MobileSidebar
│  │  ├─ common/     AnimatedCounter, GlassCard, PageHeader, GridOverlay, …
│  │  ├─ dashboard/  KpiWidget, ScoreBadge, AcquisitionRadar, charts, …
│  │  ├─ deals/      ICMemoViewer, EconomicsTable, ScoreBreakdown, RiskFlags, …
│  │  ├─ map/        PropertyMap (Leaflet), PropertyMap-dynamic (no-SSR wrapper)
│  │  ├─ filters/    FilterSidebar (district, price, m², yield, status, …)
│  │  └─ scan/       ScanLauncher, ScanProgress, LiveScanFeed
│  ├─ hooks/         use-deals, use-scan, use-kpis, use-filters, use-websocket
│  ├─ lib/
│  │  ├─ api/        client (browser), serverApi (RSC), deals, scan, types
│  │  ├─ auth/       jwt, session, config (server-only)
│  │  ├─ format.ts   money / pct / num / timeAgo
│  │  └─ constants.ts verdict + status metadata, district list, nav
│  └─ providers/     QueryProvider, AuthProvider, TooltipProvider, Toaster
└─ public/           favicon, fonts, static assets
```

### Why a universal proxy?

The browser calls **`/api/proxy/<anything>`** (same origin). The Next.js
Route Handler validates the session cookie and forwards the request to
`BACKEND_API_URL` (server-only env var). This means:

- the FastAPI URL is **never exposed** to the browser
- CORS becomes a non-issue
- one auth model regardless of where FastAPI runs (Render, Railway, VPC…)
- audit logging, rate-limiting and caching can be layered in one place

---

## Quick start (local dev)

### 1. Install Node.js 20+

```bash
node -v   # ≥ 20.x
```

### 2. Install dependencies

```bash
cd kua-frontend
npm ci
```

### 3. Configure environment

```bash
cp .env.example .env.local
```

Then edit `.env.local`:

```bash
BACKEND_API_URL=http://127.0.0.1:8000

AUTH_SECRET="$(openssl rand -base64 48)"

AUTH_OPERATOR_USERNAME=operator
AUTH_OPERATOR_DISPLAY_NAME="Acquisitions Operator"
AUTH_OPERATOR_CLEARANCE=tier-1
AUTH_OPERATOR_PASSWORD_HASH="$(node -e "console.log(require('bcryptjs').hashSync('ChangeMeNow!',10))")"
```

> **Important:** never commit `.env.local`. It's already gitignored.

### 4. Start the FastAPI backend (in another terminal)

```bash
cd ..                  # back to the backend dir
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### 5. Start the frontend

```bash
cd kua-frontend
npm run dev
```

Open **http://localhost:3000** → you'll be redirected to `/login`.
Sign in with the operator credentials above.

---

## Production deployment

The frontend can run anywhere Node.js runs. Pick your platform.

### Option A — Vercel (recommended for the frontend)

1. Push this repo to GitHub.
2. Import the repo into [Vercel](https://vercel.com/new). Set the **Root
   Directory** to `kua-frontend`.
3. Configure environment variables (Project → Settings → Environment Variables):

   | Variable                          | Value                                                  |
   | --------------------------------- | ------------------------------------------------------ |
   | `BACKEND_API_URL`                 | `https://api.your-domain.com`                          |
   | `AUTH_SECRET`                     | A 48-byte random string (`openssl rand -base64 48`)    |
   | `AUTH_OPERATOR_USERNAME`          | `operator`                                             |
   | `AUTH_OPERATOR_PASSWORD_HASH`     | bcrypt hash (see `.env.example`)                       |
   | `AUTH_OPERATOR_DISPLAY_NAME`      | `Acquisitions Operator`                                |
   | `AUTH_OPERATOR_CLEARANCE`         | `tier-1`                                               |
   | `BACKEND_AUTH_URL` *(optional)*   | `https://api.your-domain.com/auth/login` once you enable `kua_auth.py` |

4. Deploy. HTTPS is automatic.

### Option B — Railway / Render (frontend Docker)

```bash
# Build & run locally
docker build -t kua-frontend ./kua-frontend
docker run -p 3000:3000 \
  -e BACKEND_API_URL="https://api.your-domain.com" \
  -e AUTH_SECRET="$(openssl rand -base64 48)" \
  -e AUTH_OPERATOR_USERNAME=operator \
  -e AUTH_OPERATOR_PASSWORD_HASH='$2a$10$...' \
  kua-frontend
```

Both Railway (`railway.json`) and Render (`render.yaml`) ship with this
repo and use the supplied `Dockerfile` directly.

### Option C — Full Docker stack (frontend + backend)

From the project root:

```bash
docker compose up --build
```

This starts both services on a private bridge network. Only port 3000 is
exposed publicly; the backend is internal-only.

### Putting it behind HTTPS

- **Vercel / Render / Railway**: automatic HTTPS on `*.vercel.app` /
  `*.onrender.com` / `*.up.railway.app`, plus auto-cert on custom domains.
- **Docker VPS**: front the container with [Caddy](https://caddyserver.com/) —
  e.g.:

  ```Caddyfile
  app.your-domain.com {
      reverse_proxy localhost:3000
  }
  api.your-domain.com {
      reverse_proxy localhost:8000
  }
  ```

  Caddy auto-issues Let's Encrypt certificates.

---

## Backend deployment (TruTrastero FastAPI)

The repo root already ships a `Dockerfile` and `requirements.txt` for the
backend.

### Railway / Render quickstart

1. Create a new service from the repo root (NOT `kua-frontend`).
2. Use the Dockerfile builder.
3. Set environment variables: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`,
   `FRONTEND_ORIGINS=https://your-frontend.vercel.app`.
4. Deploy. Take note of the public URL (e.g. `https://api-xxx.up.railway.app`)
   and set it as `BACKEND_API_URL` on the frontend.

### CORS

The backend allows origins from the `FRONTEND_ORIGINS` env var
(comma-separated). For the production deployment, set this to your real
frontend domain:

```bash
FRONTEND_ORIGINS=https://app.your-domain.com,https://kua-frontend.vercel.app
```

Note that the Next.js proxy means CORS is rarely needed in practice — but
it lets you reach the API directly from tooling (Postman, curl, etc.).

---

## Authentication architecture

There are two layered auth paths:

1. **Local operator (default)** — credentials are validated against
   environment-configured bcrypt hashes inside the Next.js Route Handler. JWT
   is signed with `AUTH_SECRET` (HS256, jose) and set as an HTTP-only,
   Secure, SameSite=Lax cookie. The middleware (`src/middleware.ts`)
   enforces auth on every route except `/login` and `/api/auth/*`.

2. **Backend auth proxy (production)** — set `BACKEND_AUTH_URL` and enable
   `kua_auth.py` in the FastAPI app. The Next.js login handler will then
   delegate to FastAPI, which validates credentials against a real
   `operators` table (Supabase / Postgres) and returns the operator
   profile. The frontend still mints its own session cookie, which keeps
   the cookie purely first-party (no JS token storage).

### Why HTTP-only cookies, not localStorage?

- Immune to XSS token theft.
- Sent automatically on `fetch(..., { credentials: 'include' })`.
- No client-side token management.

---

## Component reference

| Component            | Location                                              | Notes                                                       |
| -------------------- | ----------------------------------------------------- | ----------------------------------------------------------- |
| `DealCard`           | `components/dashboard/deal-card.tsx`                  | Animated, hover-glow card with score, verdict, stats, flags |
| `ScoreBadge`         | `components/dashboard/score-badge.tsx`                | Radial-progress score (0-100) with tier glow                |
| `YieldWidget`        | `components/dashboard/yield-widget.tsx`               | True yield with trend delta and tier colouring              |
| `ScanProgress`       | `components/scan/scan-progress.tsx`                   | Multi-step pipeline visualiser                              |
| `KpiWidget`          | `components/dashboard/kpi-widget.tsx`                 | KPI card with animated counter + sparkline                  |
| `PropertyMap`        | `components/map/property-map.tsx`                     | Leaflet + cluster + cinematic CARTO Dark Matter tiles       |
| `ICMemoViewer`       | `components/deals/ic-memo-viewer.tsx`                 | GFM markdown renderer with regenerate action                |
| `DealTable`          | `components/dashboard/deal-table.tsx`                 | Sortable, dense table                                       |
| `FilterSidebar`      | `components/filters/filter-sidebar.tsx`               | Full filter set (district, price, m², yield, type, …)       |
| `AnimatedMetricCard` | `components/dashboard/animated-metric-card.tsx`       | Sparse metric tile                                          |
| `LiveScanFeed`       | `components/scan/live-scan-feed.tsx`                  | Real-time tracer-style ingestion feed                       |
| `DealStatusIndicator`| `components/dashboard/deal-status-indicator.tsx`      | Color-coded status pill                                     |
| `AcquisitionRadar`   | `components/dashboard/acquisition-radar.tsx`          | Rotating tactical radar with deal dots                      |
| `LoginForm`          | `components/auth/login-form.tsx`                      | Operator authentication form                                |
| `AuthGuard`          | `components/auth/auth-guard.tsx`                      | Belt-and-suspenders client redirect                         |
| `SessionIndicator`   | `components/auth/session-indicator.tsx`               | Topbar identity menu                                        |

---

## Common operations

```bash
# type-check
npm run typecheck

# lint
npm run lint

# build for production
npm run build

# serve the production build locally
npm run start

# hash a new operator password
node -e "console.log(require('bcryptjs').hashSync('YourNewPassword',10))"
```

---

## Security checklist before going live

- [ ] `AUTH_SECRET` rotated to a 48-byte random value
- [ ] `AUTH_OPERATOR_PASSWORD_HASH` is a real bcrypt hash (not the example)
- [ ] Backend `FRONTEND_ORIGINS` whitelisted to the production frontend domain
- [ ] HTTPS terminated upstream of both services (Vercel / Caddy / Cloudflare)
- [ ] `BACKEND_API_URL` points at the **server-internal** backend URL, not the
      public one when possible
- [ ] Supabase service-role key kept on the backend only
- [ ] OpenAI key kept on the backend only
- [ ] Run `npm audit` periodically

---

## License

Proprietary · KLAVE.
