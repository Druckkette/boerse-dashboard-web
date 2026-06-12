#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.nas.yml}"
ENV_FILE="${ENV_FILE:-.env.nas}"
BACKUP_FILE="${1:-}"
RESTORE_CONFIRM="${RESTORE_CONFIRM:-}"
RUN_MIGRATIONS_AFTER_RESTORE="${RUN_MIGRATIONS_AFTER_RESTORE:-1}"
START_SERVICES_AFTER_RESTORE="${START_SERVICES_AFTER_RESTORE:-1}"

echo "== boerse-dashboard-web Postgres restore =="
echo "Compose file: ${COMPOSE_FILE}"
echo "Env file:     ${ENV_FILE}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing ${ENV_FILE}. Copy .env.nas.example to .env.nas and set secrets first." >&2
  exit 1
fi

if [ -z "${BACKUP_FILE}" ]; then
  echo "Usage: RESTORE_CONFIRM=I_UNDERSTAND_THIS_OVERWRITES_DATABASE ./restore-postgres.sh ./backups/file.dump" >&2
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

if [ "${RESTORE_CONFIRM}" != "I_UNDERSTAND_THIS_OVERWRITES_DATABASE" ]; then
  echo "Refusing to restore without explicit confirmation." >&2
  echo "Set RESTORE_CONFIRM=I_UNDERSTAND_THIS_OVERWRITES_DATABASE and rerun." >&2
  exit 1
fi

echo "Backup file:  ${BACKUP_FILE}"
echo "== Stopping app services before restore =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop frontend backend worker scheduler || true

echo "== Restoring database objects =="
case "${BACKUP_FILE}" in
  *.sql)
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
      sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "${BACKUP_FILE}"
    ;;
  *)
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
      sh -c 'pg_restore --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "${BACKUP_FILE}"
    ;;
esac

if [ "${RUN_MIGRATIONS_AFTER_RESTORE}" = "1" ]; then
  echo "== Running migrations after restore =="
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile migrate run --rm migrate
fi

if [ "${START_SERVICES_AFTER_RESTORE}" = "1" ]; then
  echo "== Starting services =="
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d
fi

echo "== Restore complete =="
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
