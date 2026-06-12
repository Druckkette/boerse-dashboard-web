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

Set `POSTGRES_PASSWORD`, `DATABASE_URL`, `NEXT_PUBLIC_API_BASE_URL` and `CORS_ORIGINS`.
Optional Pushover secrets go into the same private file:

```bash
PUSHOVER_USER_KEY=...
PUSHOVER_APP_TOKEN=...
PUSHOVER_DRY_RUN=0
```

After restart, open `/settings` and run **Pushover-Testjob**. If either secret is missing, the job is
marked `skipped` instead of crashing the app.

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

## NAS Performance Rules

- Keep `WORKER_CONCURRENCY=1` on DS220+ until measured otherwise.
- Do not run multiple full refresh jobs in parallel; the API rejects a second active heavy job.
- Keep 13F jobs monthly or manual. They are large and rarely time-critical.
- Price refreshes must stay incremental; full backfills belong in a planned maintenance window.
- Redis is capped with `REDIS_MAXMEMORY` and `allkeys-lru`.
- API endpoints should return prepared snapshots from Postgres/cache, not live Pandas recomputes.
- Worker logs and backend cache use separate volumes and can be pruned independently of Postgres.
