#!/usr/bin/env bash
# Container smoke: build the CI image, run manage.py check + migrate inside it.

set -euo pipefail

COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-compose.ci.yaml}"

cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    docker compose -f "${COMPOSE_FILE_PATH}" logs --no-color || true
  fi
  docker compose -f "${COMPOSE_FILE_PATH}" down -v --remove-orphans || true
  exit "${exit_code}"
}

trap cleanup EXIT

docker compose -f "${COMPOSE_FILE_PATH}" config --quiet
docker compose -f "${COMPOSE_FILE_PATH}" build app

# Bring up db + redis (needed for migrate)
docker compose -f "${COMPOSE_FILE_PATH}" up -d --wait db redis

# Run Django check (uses test settings — sqlite, no real services)
docker compose -f "${COMPOSE_FILE_PATH}" run --rm --no-deps app \
  python manage.py check --settings=config.settings.test

# Run migrations against the CI postgres
docker compose -f "${COMPOSE_FILE_PATH}" run --rm app \
  python manage.py migrate --noinput --settings=config.settings.test

echo "Container validation passed."
