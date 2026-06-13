#!/bin/sh
set -eu

RUNTIME_ENV_FILE="${APP_RUNTIME_ENV_FILE:-/app/runtime/runtime.env}"
if [ -f "$RUNTIME_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$RUNTIME_ENV_FILE"
  set +a
fi

exec "$@"
