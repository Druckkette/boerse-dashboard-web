#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.nas.yml}"
ENV_FILE="${ENV_FILE:-.env.nas}"

echo "== boerse-dashboard-web NAS update =="
echo "Compose file: ${COMPOSE_FILE}"
echo "Env file:     ${ENV_FILE}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing ${ENV_FILE}. Copy .env.nas.example to .env.nas and set secrets first." >&2
  exit 1
fi

echo "== Pulling GHCR images =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull

echo "== Running database migrations =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile migrate run --rm migrate

echo "== Starting updated services =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans

if [ "${PRUNE_OLD_IMAGES:-0}" = "1" ]; then
  echo "== Pruning dangling/unused images only =="
  docker image prune -f
else
  echo "== Image pruning skipped. Set PRUNE_OLD_IMAGES=1 to enable docker image prune -f. =="
fi

echo "== Current service status =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
