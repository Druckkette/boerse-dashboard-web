#!/bin/sh
set -eu

runtime_env_file="${APP_RUNTIME_ENV_FILE:-/app/runtime/runtime.env}"
if [ -f "$runtime_env_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$runtime_env_file"
  set +a
fi

exec "$@"
