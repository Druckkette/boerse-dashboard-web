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
cp .env.nas.example .env.nas
vi .env.nas
docker compose --env-file .env.nas -f docker-compose.nas.yml pull
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile migrate run --rm migrate
docker compose --env-file .env.nas -f docker-compose.nas.yml up -d
```

Set at least `POSTGRES_PASSWORD`, `DATABASE_URL`, `APP_AUTH_USER` and `APP_AUTH_PASSWORD`.
Keep `APP_AUTH_ENABLED=1` for NAS use and keep `NEXT_PUBLIC_API_BASE_URL=/api/v1` so browser API
traffic goes through the protected Next.js frontend. The frontend forwards `/api/v1/*` to
`API_INTERNAL_BASE_URL=http://backend:8000` inside Docker.
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

Set `SEC_USER_AGENT` before running real 13F/SEC jobs:

```bash
SEC_USER_AGENT=boerse-dashboard-web your-email@example.com
```

This is not a secret, but it should contain a real contact email. Without it, the worker fails the
13F job before making SEC requests.

## Updates

Use Synology Task Scheduler to run:

```bash
cd /volume1/docker/boerse-dashboard-web/infra
./update-nas.sh
```

The script pulls GHCR images, runs Alembic migrations and restarts services without deleting volumes.

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

Back up the `postgres_data` volume before major updates:

```bash
docker compose --env-file .env.nas -f docker-compose.nas.yml exec postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > boerse-dashboard-$(date +%F).sql
```

For Synology Hyper Backup, include the Docker project directory and the Docker volume location used by Container Manager.

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
Those credentials are:

```bash
APP_AUTH_USER=...
APP_AUTH_PASSWORD=...
```

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
