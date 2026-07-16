#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.nas.yml}"
ENV_FILE="${ENV_FILE:-.env.nas}"
DOCKER_WAIT_SECONDS="${DOCKER_WAIT_SECONDS:-300}"

cd "${SCRIPT_DIR}"

echo "== boerse-dashboard-web NAS start =="
echo "Directory:    ${SCRIPT_DIR}"
echo "Compose file: ${COMPOSE_FILE}"
echo "Env file:     ${ENV_FILE}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing ${ENV_FILE}. Copy .env.nas.example to .env.nas and set secrets first." >&2
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
elif [ -x /usr/local/bin/docker ]; then
  DOCKER_BIN=/usr/local/bin/docker
elif [ -x /usr/bin/docker ]; then
  DOCKER_BIN=/usr/bin/docker
else
  echo "docker command not found. Make sure Synology Container Manager/Docker is installed and started." >&2
  exit 1
fi

elapsed=0
until "${DOCKER_BIN}" info >/dev/null 2>&1; do
  if [ "${elapsed}" -ge "${DOCKER_WAIT_SECONDS}" ]; then
    echo "Docker daemon was not ready after ${DOCKER_WAIT_SECONDS}s." >&2
    exit 1
  fi
  echo "Docker daemon not ready yet; waiting..."
  sleep 10
  elapsed=$((elapsed + 10))
done

echo "== Starting services =="
"${DOCKER_BIN}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d

echo "== Current service status =="
"${DOCKER_BIN}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps

echo "== Start command finished =="
