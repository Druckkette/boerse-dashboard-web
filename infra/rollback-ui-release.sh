#!/bin/sh
# Restore the complete application image pair preceding the optional UI redesign.
# Financial data, runtime settings, Redis and PostgreSQL volumes are never restored.
set -eu
umask 077
rollback_sha=f3ce8f81d67eaa49cb2605039ed7ed5013c34653
check_only=0
case "${1:-}" in --check) check_only=1;; '') :;; *) echo 'Usage: rollback-ui-release.sh [--check]' >&2; exit 2;; esac
cd "$(dirname "$0")/.."
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo 'Tracked checkout has changes; refusing rollback.' >&2; exit 1; }
# This helper is deliberately limited to this presentation release. Refuse reuse
# after backend/schema changes, where an old image could become incompatible.
git diff --quiet "$rollback_sha" HEAD -- backend infra/Dockerfile.backend || { echo 'Backend changed since UI baseline; this rollback needs a compatibility review.' >&2; exit 1; }
cd infra
[ -f .env.nas ]
docker_bin=${DOCKER_BIN:-/usr/local/bin/docker}
compose() { IMAGE_TAG="$rollback_sha" "$docker_bin" compose --env-file .env.nas -f docker-compose.nas.yml --profile beta "$@"; }
compose config --quiet
if [ "$check_only" -eq 1 ]; then
  "$docker_bin" image inspect "ghcr.io/druckkette/boerse-dashboard-web-backend:$rollback_sha" "ghcr.io/druckkette/boerse-dashboard-web-frontend:$rollback_sha" --format '{{.Id}}'
  printf 'Rollback configuration valid; local baseline images available: %s\n' "$rollback_sha"
  exit 0
fi
compose pull backend worker report-worker interactive-worker monitor scheduler frontend frontend-beta
backup_dir=$(mktemp -d /volume1/docker/boerse-dashboard-backups/ui-rollback.XXXXXX)
cp .env.nas "$backup_dir/environment.before"
awk -v revision="$rollback_sha" 'BEGIN{found=0} /^IMAGE_TAG=/{print "IMAGE_TAG=" revision;found=1;next} {print} END{if(!found) print "IMAGE_TAG=" revision}' .env.nas > .env.nas.rollback.tmp
chmod 600 .env.nas.rollback.tmp
mv .env.nas.rollback.tmp .env.nas
compose up -d --no-deps backend worker report-worker interactive-worker monitor scheduler frontend frontend-beta
printf 'Application images restored to %s. Financial data and database volumes retained.\n' "$rollback_sha"
