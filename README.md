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

Readiness: `http://localhost:8000/api/v1/readiness`

The frontend uses the same-origin API path `/api/v1` and proxies requests to the FastAPI container.
For local development, auth is disabled by default through `APP_AUTH_ENABLED=0`.

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

Use a private `.env` on the NAS for the first bootstrap values. Do not commit secrets.
Enable the private dashboard gate initially with `APP_AUTH_ENABLED=1`, `APP_AUTH_USER` and
`APP_AUTH_PASSWORD`; after the first start these Security values can be changed in `/setup` without
manually editing `.env.nas`. The frontend should stay the public entry point; the backend port binds
to `127.0.0.1` by default and is only meant for local NAS/container access.
Keep `API_RATE_LIMIT_ENABLED=1` on NAS unless you are debugging locally. The default
`API_RATE_LIMIT_REQUESTS=240` per `API_RATE_LIMIT_WINDOW_SECONDS=60` is intended as a guardrail for
direct backend access while leaving normal dashboard polling usable.
Set `API_ACCESS_LOG_ENABLED=1` on NAS to emit compact JSON request logs with `request_id`, path,
status and duration. Every API response also includes an `X-Request-ID` header.
The Settings page shows a non-blocking system status for Postgres, Alembic migrations and Redis.
The same diagnostic is available at `/api/v1/readiness` for local NAS checks.
For Pushover alerts, set `PUSHOVER_USER_KEY` and `PUSHOVER_APP_TOKEN` in `.env.nas`; the Settings
page only shows whether those env vars are configured and can start a non-blocking test job.
For deeper stock fundamentals, optionally set `FMP_API_KEY`; without it the worker keeps using
yfinance plus SEC Company Facts where available.
For real SEC/13F refreshes, set `SEC_USER_AGENT` in `.env.nas` to a project name plus a real contact
email, for example `boerse-dashboard-web name@example.com`.

Detailed NAS operations, backup and rollback notes are in `docs/nas-deployment.md`.
Use `infra/backup-postgres.sh` before major updates; it writes Postgres dumps into
`infra/backups/`, which is ignored by git.
The later VPS target is prepared in `infra/docker-compose.hetzner.yml` and documented in
`docs/hetzner-deployment.md`; it uses Caddy for HTTPS and keeps FastAPI internal.

## Market Data Bootstrap

After the NAS containers are running, populate the app through the dashboard UI. Open
`http://NAS-IP-ODER-HOSTNAME:3000/setup`. The setup page checks system readiness, portfolio import,
price cache, market breadth, RS ratings and the ATR monitor, then offers the next safe action.
No files have to be placed manually on the NAS; portfolio data is imported through
`/portfolio/imports`.

For operational refreshes open `/jobs` and use the primary assistant actions:

1. **Prüfen & fehlendes aktualisieren** checks system freshness first and runs only the missing
   or stale parts: missing/stale position prices, global market prices, breadth, RS ratings and
   the position monitor where needed.
2. **Alles initialisieren** loads the US common-stock universe, price cache, market breadth,
   RS ratings and the position monitor in one worker job.
3. **Alles aktualisieren** refreshes the same prepared data path without rebuilding the universe.

The older individual jobs remain available under the expert tools section for diagnostics.

The setup and jobs pages store only UI preferences in the browser. The market data itself is stored
in the Postgres Docker volume. You only need to repeat the full bootstrap when the database volume
is empty, after a deliberate reset, or when you want to load a different universe or longer history.
Normal updates should be handled by scheduler/worker jobs. The scheduler uses the smart refresh
path so it avoids unnecessary heavy recalculations when data is already current.

Long-running bootstrap jobs are configured for NAS runtimes: Celery has a 48 hour hard task limit
and a 72 hour Redis visibility timeout by default. The bootstrap stores checkpoints in the job
result, so if Redis redelivers the task or the worker is recreated, completed stages such as
Universe, Price Cache and Breadth are skipped instead of starting again at `Price Cache 25/5026`.

`refresh_prices` loads the starter universe plus the Streamlit-compatible market indexes `^GSPC`,
`^IXIC`, `^RUT`, the equal-weight ETFs `RSP`/`QQEW`, and the volatility tickers `SPY`, `^VIX` and
`VIXY`. It also loads the SPDR sector ETFs used by `/sectors`. With a custom universe, the UI also
includes the RS benchmark and volatility tickers in the price refresh so market overview and RS
calculations have the required support data.

`/stocks/ratings/rs` and `/stocks/<ticker>/rs` read the persisted `rs_ratings` table. They do not
run yfinance or Pandas recomputes in the click path.

`/market/overview` and `/market/breadth` read prepared database snapshots. If no snapshots exist
yet, they return explicit missing-data states rather than blocking the UI.

The monitor evaluates open imported positions against cached bars, stores recommendation state and
reports ATR/health/signal status through the Jobs page. It does not run yfinance in the request path.
After a monitor run, `/sell-monitor` reads the precomputed ranking snapshot from Postgres and only
falls back to live Sell-Engine evaluation when no snapshot exists yet.

The 13F/SEC job downloads official SEC Form-13F quarterly data sets in the worker, caches ZIP files
under the backend cache volume and persists aggregate ticker trends. It requires `SEC_USER_AGENT`;
run it manually or monthly, not as part of the normal daily bootstrap. The preferred path is now
`/setup` > `Konfiguration & Secrets`: enter `SEC_USER_AGENT` there and the backend/worker will read it
from Postgres without editing `.env.nas`.

As a fallback, set it in `/volume1/docker/boerse-dashboard-web/infra/.env.nas`:

```bash
SEC_USER_AGENT=boerse-dashboard-web name@example.com
```

After changing `.env.nas`, recreate the affected services so the new environment is loaded:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d --force-recreate frontend worker scheduler backend
```

FMP, Pushover, Security/Basic Auth and Neon/Postgres credentials can also be entered and tested in `/setup`.
Saving the Neon URL does not switch the running database. Use the database target controls to choose
between local Postgres and Neon, then click **Dienste neu starten** so `frontend`, `backend`,
`worker` and `scheduler` reload the generated runtime env file. General Compose defaults such as Redis stay
hard-coded in the repository and are not shown as setup fields.

The Fundamentals job stores a compact yfinance snapshot and, when configured, enriches quarterly
EPS/revenue growth and acceleration with FMP and SEC Company Facts. `FMP_API_KEY` is optional and
belongs only in `.env.nas` or your local private `.env`.

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

## Private Access

The NAS deployment uses a lightweight Basic Auth gate in the Next.js frontend. Set these values in
the private NAS environment file for the first start, then manage them under `/setup` in the
collapsible **Security** section:

- `APP_AUTH_ENABLED=1`
- `APP_AUTH_USER=<your-user>`
- `APP_AUTH_PASSWORD=<long-random-password>`
- `API_RATE_LIMIT_ENABLED=1`
- `API_RATE_LIMIT_REQUESTS=240`
- `API_RATE_LIMIT_WINDOW_SECONDS=60`
- `API_ACCESS_LOG_ENABLED=1`

Normal browser traffic should go to `http://NAS-IP-ODER-HOSTNAME:3000`. The frontend serves pages and
forwards `/api/v1/*` to the internal FastAPI service. On NAS, these proxy values are set centrally
in `infra/docker-compose.nas.yml`; `.env.nas` should not override `API_INTERNAL_BASE_URL` or
`NEXT_PUBLIC_API_BASE_URL`. Keep `BACKEND_BIND=127.0.0.1` unless you intentionally need temporary
direct access to `http://NAS-IP:8000/docs`.

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
- Smart refresh checks freshness first and only runs the required price, breadth, RS and monitor steps.
- Redis uses a memory cap in Compose.
- API endpoints should read prepared snapshots, not run live Pandas recomputes.
