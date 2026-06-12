# boerse-dashboard-web

API-first migration scaffold for the existing `boerse-dashboard` Streamlit app.

The old Streamlit repository remains a read-only reference for business logic, data models, rules and tests. This repository is a separate target architecture: Next.js frontend, FastAPI backend, Postgres, Redis and isolated worker processes. There is intentionally no Streamlit dependency here.

## Goal

The new app is built for a fast trading and portfolio workflow:

- React UI updates instantly for small settings.
- Backend endpoints return JSON with stable contracts.
- Heavy market refreshes, RS ratings, yfinance loads, SEC/13F work and ATR monitoring run in workers.
- Docker Compose can run locally and later on a Synology NAS or Hetzner host.

## Local Start

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

Frontend: `http://localhost:3000`

Backend: `http://localhost:8000`

OpenAPI: `http://localhost:8000/docs`

Run migrations explicitly when using a fresh Postgres volume:

```bash
docker compose -f infra/docker-compose.yml --profile migrate run --rm migrate
```

## Development Without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Worker:

```bash
cd backend
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency=1
```

Scheduler:

```bash
cd backend
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app beat --loglevel=INFO
```

## NAS Target

`infra/docker-compose.nas.yml` is prepared for GHCR images:

- `ghcr.io/druckkette/boerse-dashboard-web-backend:latest`
- `ghcr.io/druckkette/boerse-dashboard-web-frontend:latest`

Worker, scheduler and migrations use the same backend image. Copy `infra/.env.nas.example` to
`infra/.env.nas`, set secrets and run:

```bash
cd infra
./update-nas.sh
```

Use a private `.env` on the NAS for database passwords, API keys and future notification credentials. Do not commit secrets.
For Pushover alerts, set `PUSHOVER_USER_KEY` and `PUSHOVER_APP_TOKEN` in `.env.nas`; the Settings
page only shows whether those env vars are configured and can start a non-blocking test job.

Detailed NAS operations, backup and rollback notes are in `docs/nas-deployment.md`.

## Market Data Bootstrap

After the NAS containers are running, populate the market cache through the dashboard UI. Open
`http://NAS-IP-ODER-HOSTNAME:3000/jobs`, use **Marktdaten initial laden**, set the desired range,
lookback windows and optional custom ticker list, then start the jobs in this order:

1. `Market Prices`
2. `Market Breadth`
3. `RS Ratings`
4. `Positionsmonitor` after importing a portfolio

The UI stores these bootstrap values in the browser so you do not have to retype them on the next
visit from the same browser. The market data itself is stored in the Postgres Docker volume. You
only need to repeat the full bootstrap when the database volume is empty, after a deliberate reset,
or when you want to load a different universe or longer history. Normal updates should be handled
by scheduler/worker jobs.

`refresh_prices` loads the starter universe plus the volatility tickers `SPY`, `^VIX` and `VIXY`.
It also loads the SPDR sector ETFs used by `/sectors`. With a custom universe, the UI also includes
the RS benchmark and volatility tickers in the price refresh so market overview and RS calculations
have the required support data.

`/stocks/ratings/rs` and `/stocks/<ticker>/rs` read the persisted `rs_ratings` table. They do not
run yfinance or Pandas recomputes in the click path.

`/market/overview` and `/market/breadth` read prepared database snapshots. If no snapshots exist
yet, they return fallback data rather than blocking the UI.

The monitor evaluates open imported positions against cached bars, stores recommendation state and
reports ATR/health/signal status through the Jobs page. It does not run yfinance in the request path.

The same jobs can still be started through `POST /api/v1/jobs` for automation, but manual NAS
operation should use the dashboard.

## Portfolio Import

Open `http://NAS-IP-ODER-HOSTNAME:3000/portfolio/imports` and import a CSV position snapshot.
The CSV is selected or dropped in the browser and sent to the backend API; no file has to be copied
to a NAS folder. Preview and persistence are separate actions.

After saving, `/portfolio` reads the imported positions from Postgres and `/sell-monitor` uses those
positions for ranking. The built-in demo portfolio is only used while the database has no imported
open positions.

Required columns:

- `Ticker`
- `Shares`
- `Entry_Price`

Optional columns:

- `Name`
- `Current_Price`
- `Currency`
- `Buy_Date`
- `Broker`
- `Account`
- `Note`

German aliases such as `Stück`, `Einstandskurs`, `Währung` and `Kaufdatum` are accepted. If
`Current_Price` is present, it is stored as a `portfolio_import` price bar so the portfolio view can
show a realistic valuation before the next yfinance refresh.

## GHCR Publishing

`.github/workflows/docker-publish.yml` publishes on push to `main`:

- `ghcr.io/<owner>/boerse-dashboard-web-backend:latest`
- `ghcr.io/<owner>/boerse-dashboard-web-backend:<commit-sha>`
- `ghcr.io/<owner>/boerse-dashboard-web-frontend:latest`
- `ghcr.io/<owner>/boerse-dashboard-web-frontend:<commit-sha>`

Repository settings required:

- Actions permission to read contents and write packages.
- Workflow permission `packages: write` is declared in the workflow.
- For private GHCR packages, the NAS needs `docker login ghcr.io` with a token that has `read:packages`.

## Why UI And Jobs Are Separate

Streamlit reruns the app after widget changes, which can block the entire UI if a click triggers data loading or recalculation. This scaffold separates concerns:

- Frontend state handles immediate interactions.
- API requests are short and return cached or precomputed JSON.
- Long-running market and portfolio calculations run in worker containers.
- Job status is exposed through `/api/v1/jobs`.

This prevents small controls, such as ATR threshold changes, from starting a full data refresh or blocking the screen.

## NAS Performance Guardrails

- `WORKER_CONCURRENCY=1` is the default.
- The Jobs API rejects a second active heavy job.
- SEC/13F jobs are scheduled monthly and should not be run frequently.
- Price refreshes are designed as incremental jobs.
- Redis uses a memory cap in Compose.
- API endpoints should read prepared snapshots, not run live Pandas recomputes.
