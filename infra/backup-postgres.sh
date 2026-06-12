#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.nas.yml}"
ENV_FILE="${ENV_FILE:-.env.nas}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/boerse-dashboard-postgres-${TIMESTAMP}.dump"

echo "== boerse-dashboard-web Postgres backup =="
echo "Compose file: ${COMPOSE_FILE}"
echo "Env file:     ${ENV_FILE}"
echo "Backup file:  ${TARGET}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing ${ENV_FILE}. Copy .env.nas.example to .env.nas and set secrets first." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "== Creating pg_dump custom-format backup =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --no-owner --no-acl' \
  > "${TARGET}.tmp"

mv "${TARGET}.tmp" "${TARGET}"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${TARGET}" > "${TARGET}.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${TARGET}" > "${TARGET}.sha256"
fi

echo "== Backup complete =="
ls -lh "${TARGET}"
if [ -f "${TARGET}.sha256" ]; then
  echo "Checksum: ${TARGET}.sha256"
fi
