# Whale Sharks — Setup

## Architecture

- `backend/` — FastAPI, scans Polymarket's public APIs every ~15 minutes, computes
  whale consensus, persists to Postgres, serves the latest result from an
  in-process cache. See `.claude/plans` or the code comments in
  `backend/app/core/scan_service.py` for the scan pipeline.
- `frontend/` — Vite + React + TypeScript + Tailwind dashboard.

**Single-instance constraint:** the scheduler and cache are in-process (no Redis,
no cross-process coordination). Run exactly one backend process — one
`uvicorn` worker, one deployed instance. A Postgres advisory lock
(`app/db/repository.py::try_acquire_scan_lock`) guards against a second
process double-writing a scan if this constraint is ever violated, but it
doesn't make multi-instance deployment correct or supported.

## 1. Create a Supabase project

1. Create a project at [supabase.com](https://supabase.com).
2. In **Project Settings → Database**, copy two connection strings:
   - **Direct connection** (port 5432) — used only by Alembic migrations.
   - **Connection pooling** (port 6543, transaction mode) — used by the app at runtime.

## 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `DATABASE_URL` — the pooled (6543) connection string, with `postgresql+asyncpg://` scheme.
- `DATABASE_URL_DIRECT` — the direct (5432) connection string, same scheme.
- `CORS_ORIGINS` — `http://localhost:5173` for local dev.

Run the migration:

```bash
alembic upgrade head
```

Populate the first dataset (don't wait 15 minutes for the scheduler):

```bash
python -m scripts.run_scan_once
```

This hits live Polymarket APIs and can take 30–90 seconds depending on how many
distinct markets the current top traders hold. Check `backend/app/core/scan_service.py`
if it's consistently slower — `SCAN_TIMEOUT_SECONDS` caps it at 8 minutes.

Start the server:

```bash
uvicorn app.main:app --reload --port 8000
```

`/api/health` should report `"ready": true` once the manual scan (or the
lifespan's own background scan) completes. The scheduler then re-scans every
`SCAN_INTERVAL_MINUTES` (default 15).

Run the unit tests:

```bash
pytest
```

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`. The dev server proxies `/api/*` to
`http://localhost:8000` (see `vite.config.ts`) — no env var needed locally.
For a production build pointing at a deployed backend, set
`VITE_API_BASE_URL` (see `.env.example`).

## Known limitations (by design, for MVP)

- **Gamma metadata gaps.** Not every `conditionId` returned by `/positions`
  has a matching Gamma market (older/delisted markets, indexing lag). Those
  rows render with an empty market title/category rather than failing the
  scan — cosmetic, not a crash.
- **Hedged positions double-count.** A trader holding both YES and NO on the
  same market appears as a "consensus holder" on both outcome groups
  independently, since grouping is by market+outcome per the product spec.
- **Dust filtered out.** Positions under `MIN_POSITION_VALUE` (env-configurable,
  default $100) are excluded from consensus entirely — real conviction, not
  every $1 leftover position.
