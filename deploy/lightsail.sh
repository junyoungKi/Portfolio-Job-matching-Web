#!/usr/bin/env bash
# Deploy this repo on the Lightsail host.
# .github/workflows/deploy.yml runs this script over SSH as the instance user.
# git reset --hard updates tracked files only. It does not delete gitignored
# files, so deploy/certs/ stays in place. Do not git clean. Do not run
# docker-compose down (with or without -v); that can remove volumes.
#
# Redis is only the /match cache (app/main.py keys match_results:*, TTL 3600s).
# The compose file gives it no volume. Removing the container clears that cache.
# Job rows stay in Postgres.

set -euo pipefail

repo="${HOME}/Portfolio-Job-matching-Web"
# compose v1 container names for ~/Portfolio-Job-matching-Web. A failed recreate
# renames the old container to <id>_<project>_<service>_1, which
# `docker-compose ps` no longer lists.
compose_project="portfolio-job-matching-web"
health_attempts="${LIGHTSAIL_HEALTH_ATTEMPTS:-30}"
health_sleep="${LIGHTSAIL_HEALTH_SLEEP:-2}"

remove_project_containers() {
  local compose_ids docker_ids ids id remaining
  # web, caddy, and redis. Leaving redis in place makes `up` recreate it when
  # its compose config changes, and docker-compose 1.29.2 then raises
  # KeyError: 'ContainerConfig', stops after renaming redis, and never creates
  # the services this script already removed. A future compose-config change
  # on redis repeats that unless redis is still removed here.
  if ! compose_ids="$(docker-compose ps -q -a web caddy redis)"; then
    return 1
  fi
  # --no-trunc: `docker-compose ps -q` prints 64-character ids and plain
  # `docker ps -q` prints 12-character ones. Mixed, the same container is listed
  # twice and the second `docker rm` fails with "removal ... already in progress".
  if ! docker_ids="$(docker ps -aq --no-trunc --filter "name=${compose_project}")"; then
    return 1
  fi
  ids="$(printf '%s\n%s\n' "${compose_ids}" "${docker_ids}" | awk 'NF && !seen[$0]++')"
  # One container per call: a container that is already going away must not stop
  # the rest. The check below decides whether anything is really left.
  for id in ${ids}; do
    docker rm -f "${id}" || echo "docker rm -f ${id} failed; checking whether it is gone" >&2
  done
  if [ -n "${ids}" ]; then
    if ! remaining="$(docker ps -aq --no-trunc --filter "name=${compose_project}")"; then
      return 1
    fi
    if [ -n "${remaining}" ]; then
      sleep 2
      if ! remaining="$(docker ps -aq --no-trunc --filter "name=${compose_project}")"; then
        return 1
      fi
    fi
    if [ -n "${remaining}" ]; then
      echo "Containers still present after removal: ${remaining}" >&2
      return 1
    fi
  fi
}

print_recovery() {
  cat >&2 <<EOF
deploy/lightsail.sh failed. The site may be down.

docker-compose 1.29.2 raises KeyError: 'ContainerConfig' when it recreates an
existing container. A failed recreate stops and renames that container (the
#24 deploy log shows 80209f74697e_portfolio-job-matching-web_redis_1), and
services this script already removed stay down until up creates them again.

Redis is only the match-result cache (match_results:* in app/main.py, one-hour
TTL, no compose volume). Removing its container clears that cache. Postgres
and deploy/certs stay. Do not run docker-compose down or docker-compose down -v.

A future compose-config change on redis hits the same KeyError unless this
script still removes the redis container before up.

From ${repo}, recover with:

  docker ps -a
  docker rm -f \$(docker ps -aq --filter name=${compose_project})
  docker-compose up -d
  curl -sf http://127.0.0.1:8000/stats
EOF
}

deploy_main() {
  if ! command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose is not installed or not on PATH" >&2
    exit 1
  fi

  cd "${repo}"

  git fetch origin
  git checkout main
  git reset --hard origin/main

  docker-compose build web

  if ! remove_project_containers; then
    print_recovery
    exit 1
  fi

  if ! docker-compose up -d; then
    print_recovery
    exit 1
  fi

  # up -d returns before uvicorn is listening. Retry the health check, then
  # fail the script if /stats never succeeds.
  local healthy=0 attempt
  for ((attempt = 1; attempt <= health_attempts; attempt++)); do
    if curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/stats; then
      healthy=1
      break
    fi
    sleep "${health_sleep}"
  done

  if [ "${healthy}" -ne 1 ]; then
    echo "Deploy health check failed: http://127.0.0.1:8000/stats did not return success" >&2
    print_recovery
    exit 1
  fi
}

# The workflow pipes this file to `bash -s`, where BASH_SOURCE is empty. Run the deploy when
# executed directly or piped; stay quiet only when another script sources it (tests).
if [ -z "${BASH_SOURCE[0]:-}" ] || [ "${BASH_SOURCE[0]}" = "$0" ]; then
  deploy_main
fi
