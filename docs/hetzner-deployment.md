# Hetzner Deployment

This profile runs the same GHCR images as the NAS setup, with Caddy as the public TLS reverse proxy.
The FastAPI backend is not published to the host; browser traffic enters through HTTPS and the
Next.js frontend proxy.

## Server Prerequisites

- A small Hetzner VPS with Docker Engine and Docker Compose plugin.
- DNS `A`/`AAAA` record for `APP_DOMAIN` pointing to the server.
- Firewall open for ports `80` and `443`; keep Postgres, Redis and backend ports private.
- GHCR login if the package is private:

```bash
echo "GHCR_TOKEN" | docker login ghcr.io -u GITHUB_USER --password-stdin
```

## First Setup

```bash
mkdir -p /opt/boerse-dashboard-web
cd /opt/boerse-dashboard-web
# copy the infra directory from this repo to the server
cd infra
cp .env.hetzner.example .env.hetzner
vi .env.hetzner
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml pull
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml --profile migrate run --rm migrate
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml up -d
```

Set at least:

- `APP_DOMAIN`
- `ACME_EMAIL`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `APP_AUTH_USER`
- `APP_AUTH_PASSWORD`
- `SEC_USER_AGENT`

Keep `APP_AUTH_ENABLED=1`, `API_RATE_LIMIT_ENABLED=1` and `API_ACCESS_LOG_ENABLED=1` unless another
trusted access layer sits in front of Caddy.

## Updates

```bash
cd /opt/boerse-dashboard-web/infra
COMPOSE_FILE=docker-compose.hetzner.yml ENV_FILE=.env.hetzner ./backup-postgres.sh
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml pull
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml --profile migrate run --rm migrate
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml up -d --remove-orphans
```

## Backup And Restore

The NAS backup scripts also work for Hetzner by overriding compose/env names:

```bash
cd /opt/boerse-dashboard-web/infra
COMPOSE_FILE=docker-compose.hetzner.yml ENV_FILE=.env.hetzner ./backup-postgres.sh
RESTORE_CONFIRM=I_UNDERSTAND_THIS_OVERWRITES_DATABASE \
  COMPOSE_FILE=docker-compose.hetzner.yml \
  ENV_FILE=.env.hetzner \
  ./restore-postgres.sh ./backups/boerse-dashboard-postgres-YYYYMMDDTHHMMSSZ.dump
```

## Rollback

Images are tagged with `latest` and commit SHA. Set `IMAGE_TAG=<commit-sha>` in `.env.hetzner`,
restore a matching DB backup when needed, then pull and restart:

```bash
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml pull
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml up -d
```

## Logs

```bash
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml logs -f caddy
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml logs -f backend
docker compose --env-file .env.hetzner -f docker-compose.hetzner.yml logs -f worker
```

Backend responses include `X-Request-ID`; with `API_ACCESS_LOG_ENABLED=1`, backend logs include the
same request id in compact JSON lines.
