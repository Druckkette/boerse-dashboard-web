# NAS Deployment

This deployment target runs the same backend image for API, worker, scheduler and migrations.

## GHCR Login

Create a GitHub personal access token with `read:packages`. On the NAS:

```bash
echo "GHCR_TOKEN" | docker login ghcr.io -u GITHUB_USER --password-stdin
```

For public packages, login may not be required. Private packages require the token.

## First Setup

```bash
cd /volume1/docker/boerse-dashboard-web
cd infra
cp .env.nas.example .env.nas
vi .env.nas
docker compose --env-file .env.nas -f docker-compose.nas.yml pull
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile migrate run --rm migrate
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d
```

Set at least `POSTGRES_PASSWORD`, `DATABASE_URL`, `APP_AUTH_USER` and `APP_AUTH_PASSWORD` for the
first start. Later Security/Auth changes can be made in `/setup`. Keep `APP_AUTH_ENABLED=1` for NAS
use. Browser API traffic goes through the protected Next.js
frontend at `/api/v1`; the internal FastAPI target `http://backend:8000` is set centrally in
`docker-compose.nas.yml` and does not need to be configured in `.env.nas`.
Keep `API_RATE_LIMIT_ENABLED=1` for NAS use. The default example allows 240 backend requests per
60 seconds per client and excludes health/docs endpoints, which is enough for normal dashboard
polling but helps if the backend port is accidentally exposed.
Set `API_ACCESS_LOG_ENABLED=1` to add compact JSON request logs. Each response also carries
`X-Request-ID`, which makes browser/network errors easier to match with container logs.

`BACKEND_BIND=127.0.0.1` keeps FastAPI reachable only from the NAS host itself. Change it to
`0.0.0.0` only for deliberate temporary debugging, for example to open `/docs` from another machine.
If the backend port is exposed publicly, it is outside the frontend Basic Auth gate.

Set `CORS_ORIGINS` to the NAS frontend origin if you intentionally use direct backend calls.
Optional Pushover secrets go into the same private file:

```bash
PUSHOVER_USER_KEY=...
PUSHOVER_APP_TOKEN=...
PUSHOVER_DRY_RUN=0
FMP_API_KEY=...
```

`FMP_API_KEY` is optional. When present, the Fundamentals worker uses it for deeper quarterly EPS
and revenue history; when absent, the worker still uses yfinance and configured SEC data.

After restart, open `/settings` and run **Pushover-Testjob**. If either secret is missing, the job is
marked `skipped` instead of crashing the app.

Open `http://NAS-IP-ODER-HOSTNAME:3000/jobs` for the first data bootstrap and click
**Alles initialisieren**. This one worker job loads the US common-stock universe, price cache,
market breadth, RS ratings and the ATR position monitor path. For later refreshes click
**Alles aktualisieren**. You do not have to copy CSV files into a container or run `curl` commands
manually.

The bootstrap does not have to be repeated after normal container restarts. Postgres data lives in
the Docker volume; repeat the full setup only after an empty/reset database, after restoring a clean
volume, or when you deliberately want a different universe or longer history.

The `/settings` page also shows **Systemstatus**. It checks Postgres, Alembic migration revision and
Redis without blocking the UI. From the NAS shell you can inspect the same status with:

```bash
curl http://127.0.0.1:8000/api/v1/readiness
```

## 502 Bad Gateway

`API request failed: 502 Bad Gateway` means the Next.js frontend proxy could not reach FastAPI.
Check this from the NAS in `.../boerse-dashboard-web/infra`:

```bash
docker compose --env-file .env.nas -f docker-compose.nas.yml ps
docker compose --env-file .env.nas -f docker-compose.nas.yml logs --tail=120 backend
docker compose --env-file .env.nas -f docker-compose.nas.yml logs --tail=120 frontend
docker compose --env-file .env.nas -f docker-compose.nas.yml exec frontend wget -qO- http://backend:8000/api/v1/health
```

Expected frontend env values are provided by `docker-compose.nas.yml`:

```bash
API_INTERNAL_BASE_URL=http://backend:8000
NEXT_PUBLIC_API_BASE_URL=/api/v1
```

Do not set `API_INTERNAL_BASE_URL` to `http://127.0.0.1:8000` inside the frontend container. Inside
Docker, `127.0.0.1` would point to the frontend container itself, not the backend service.
If `.env.nas` still contains older `API_INTERNAL_BASE_URL` or `NEXT_PUBLIC_API_BASE_URL` lines, remove
them; the compose file now owns those non-secret defaults.

Prefer the web setup page for runtime integration secrets:

1. Open `http://NAS-IP-ODER-HOSTNAME:3000/setup`.
2. In `Konfiguration & Secrets`, enter `SEC_USER_AGENT`, optional `FMP_API_KEY`, optional
   Pushover credentials, Security/Basic-Auth values, or an optional Neon/Postgres URL.
3. Use the field-level `Testen` button before saving. For Neon, this runs a real database
   connection test from the backend container.
4. Click `Speichern`.

Backend and worker read SEC/FMP/Pushover values from Postgres; the setup flow also mirrors editable
runtime secrets into the generated runtime env file. No `.env.nas` edit or worker restart is needed
for those runtime-applied values during normal operation. Security/Basic Auth and Neon/Postgres use
the same setup flow, but they apply after the affected containers restart because Next.js and
SQLAlchemy read those values at process start.

As an environment fallback, set `SEC_USER_AGENT` before running real 13F/SEC jobs:

```bash
SEC_USER_AGENT=boerse-dashboard-web your-email@example.com
```

This is not a secret, but it should contain a real contact email. Without it, the worker fails the
13F job before making SEC requests.
On Synology, this belongs in `/volume1/docker/boerse-dashboard-web/infra/.env.nas`. After editing it,
recreate the containers that read the variable:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d --force-recreate frontend worker scheduler backend
```

Saving a Neon URL only stores and tests the candidate. It does not switch the app. Use the
**Datenbank-Ziel** controls in `/setup`:

1. Click **Neon verwenden** or **Lokale Postgres verwenden**.
2. Click **Dienste neu starten**.

The button restarts `worker`, `scheduler`, `frontend` and then `backend` through the Docker socket. This replaces
running the following command manually for normal runtime database switches:

```bash
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d --force-recreate frontend worker scheduler backend
```

For Neon/Postgres and Security/Basic Auth, the setup screen writes `/app/runtime/runtime.env` into
the persistent `backend_runtime` volume. Backend, worker, scheduler and frontend mount that file so
saved runtime settings survive normal container pulls/recreates. A switch to an empty Neon database
can still require re-entering values because the active database is the source of truth.

The restart button needs Docker socket access. In `docker-compose.nas.yml` the backend mounts
`/var/run/docker.sock` and `NAS_CONTROL_ENABLED=1` by default. Disable it with
`NAS_CONTROL_ENABLED=0` if you prefer to run the compose command manually.

Redis and image/deployment values remain Compose defaults and are intentionally not shown in setup.

## Updates

Use Synology Task Scheduler to run:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
./update-nas.sh
```

The script pulls GHCR images, runs Alembic migrations and restarts services without deleting volumes.
Run a database backup before major updates:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
./backup-postgres.sh
./update-nas.sh
```

## Rollback

Images are published as `latest` and commit-SHA tags. To roll back:

```bash
vi .env.nas
# set IMAGE_TAG=<commit-sha>
docker compose --env-file .env.nas -f docker-compose.nas.yml pull
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d
```

Database downgrades are not automatic. Restore a Postgres backup if the rollback crosses an incompatible migration.

## Backups

Back up Postgres before major updates or before testing a new migration:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
./backup-postgres.sh
```

The script writes `./backups/boerse-dashboard-postgres-<timestamp>.dump` plus a SHA-256 checksum
when the host has `sha256sum` or `shasum`. It uses `pg_dump --format=custom` and does not stop
containers or delete volumes.

For Synology Hyper Backup, include the Docker project directory and the Docker volume location used by Container Manager.

## Restore Test / Disaster Restore

Restore is intentionally guarded because it overwrites database objects. Stop app services, restore
the dump, run migrations and restart services with:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
RESTORE_CONFIRM=I_UNDERSTAND_THIS_OVERWRITES_DATABASE ./restore-postgres.sh ./backups/boerse-dashboard-postgres-YYYYMMDDTHHMMSSZ.dump
```

The restore script does not remove Docker volumes. It supports the custom `.dump` files created by
`backup-postgres.sh` and plain `.sql` files. For a rollback to a specific image plus database state,
set `IMAGE_TAG=<commit-sha>` in `.env.nas`, run the restore command, then run `./update-nas.sh`.

## Pause Worker Or Scheduler

```bash
docker compose --env-file .env.nas -f docker-compose.nas.yml stop worker
docker compose --env-file .env.nas -f docker-compose.nas.yml stop scheduler
```

The frontend and backend continue to run. The Jobs page will still show stored job state.

## Logs

```bash
docker compose --env-file .env.nas -f docker-compose.nas.yml logs -f backend
docker compose --env-file .env.nas -f docker-compose.nas.yml logs -f worker
docker compose --env-file .env.nas -f docker-compose.nas.yml logs -f scheduler
```

## Private Dashboard Access

The normal NAS URL is:

```text
http://NAS-IP-ODER-HOSTNAME:3000
```

The browser receives a Basic Auth challenge from the Next.js frontend when `APP_AUTH_ENABLED=1`.
Bootstrap credentials can be set in `.env.nas` for the first start:

```bash
APP_AUTH_USER=...
APP_AUTH_PASSWORD=...
```

After the first start, change them in `/setup` under **Konfiguration & Secrets > Security**,
save, then click **Dienste neu starten**. The Security section is collapsed by default.

The FastAPI backend still runs on port `8000` for container health checks and local diagnostics, but
it is bound to `127.0.0.1` by default. That keeps personal depot, settings and job APIs behind the
frontend route `/api/v1`.
The backend also has an optional in-memory rate limit controlled by:

```bash
API_RATE_LIMIT_ENABLED=1
API_RATE_LIMIT_REQUESTS=240
API_RATE_LIMIT_WINDOW_SECONDS=60
API_ACCESS_LOG_ENABLED=1
```

## NAS Performance Rules

- Keep `WORKER_CONCURRENCY=1` on DS220+ until measured otherwise.
- Do not run multiple full refresh jobs in parallel; the API rejects a second active heavy job.
- Keep 13F jobs monthly or manual. They are large and rarely time-critical.
- Price refreshes must stay incremental; full backfills belong in a planned maintenance window.
- Redis is capped with `REDIS_MAXMEMORY` and `allkeys-lru`.
- API endpoints should return prepared snapshots from Postgres/cache, not live Pandas recomputes.
- Worker logs and backend cache use separate volumes and can be pruned independently of Postgres.
