#!/usr/bin/env bash
# Deploy this repo on the Lightsail host.
# .github/workflows/deploy.yml runs this script over SSH as the instance user.
# git reset --hard updates tracked files only. It does not delete gitignored
# files, so deploy/certs/ stays in place. Do not git clean. Do not run
# docker-compose down (with or without -v); that can remove volumes.

set -euo pipefail

repo="${HOME}/Portfolio-Job-matching-Web"

if ! command -v docker-compose >/dev/null 2>&1; then
  echo "docker-compose is not installed or not on PATH" >&2
  exit 1
fi

cd "${repo}"

git fetch origin
git checkout main
git reset --hard origin/main

docker-compose build web

# docker-compose 1.29.2 raises KeyError: 'ContainerConfig' when it recreates
# an existing container. Remove web and caddy, including stopped ones, before
# up. Leave the redis container and its volume running.
for svc in web caddy; do
  id="$(docker-compose ps -q -a "${svc}")"
  if [ -n "${id}" ]; then
    # Container ids are hex. Unquoted so every id from ps is removed.
    # shellcheck disable=SC2086
    docker rm -f ${id}
  fi
done

docker-compose up -d

# up -d returns before uvicorn is listening. Retry the health check, then
# fail the script if /stats never succeeds.
healthy=0
for ((attempt = 1; attempt <= 30; attempt++)); do
  if curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/stats; then
    healthy=1
    break
  fi
  sleep 2
done

if [ "${healthy}" -ne 1 ]; then
  echo "Deploy health check failed: http://127.0.0.1:8000/stats did not return success" >&2
  exit 1
fi
