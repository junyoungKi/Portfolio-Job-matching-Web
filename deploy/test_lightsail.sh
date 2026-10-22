#!/usr/bin/env bash
# Exercise deploy/lightsail.sh without docker, git, or the network.
# Stubs record the commands the deploy would run.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

log="${tmpdir}/calls"
err="${tmpdir}/err"
export HOME="${tmpdir}/home"
mkdir -p "${HOME}/Portfolio-Job-matching-Web"
export LIGHTSAIL_HEALTH_ATTEMPTS=2
export LIGHTSAIL_HEALTH_SLEEP=0

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_file_has_no_down_invocation() {
  # The recovery text may name `docker-compose down` only to forbid it.
  awk '
    /^[[:space:]]*#/ { next }
    /docker-compose[[:space:]]+down/ && !/Do not run/ { found = 1 }
    END { exit found ? 1 : 0 }
  ' "${root}/deploy/lightsail.sh" || fail "script invokes docker-compose down"
}

# shellcheck disable=SC2317
git() { echo "git $*" >> "${log}"; }
# shellcheck disable=SC2317
curl() { echo "curl $*" >> "${log}"; return "${curl_rc:-0}"; }
# shellcheck disable=SC2317
sleep() { echo "sleep $*" >> "${log}"; }
# shellcheck disable=SC2317
docker() { echo "docker $*" >> "${log}"; }
# shellcheck disable=SC2317
docker-compose() { echo "compose $*" >> "${log}"; }

# shellcheck source=deploy/lightsail.sh
source "${root}/deploy/lightsail.sh"

reset_stubs() {
  : > "${log}"
  : > "${err}"
  curl_rc=0
  curl() { echo "curl $*" >> "${log}"; return "${curl_rc:-0}"; }
  docker() { echo "docker $*" >> "${log}"; }
  docker-compose() { echo "compose $*" >> "${log}"; }
}

remove_unions_compose_ps_and_renamed_leftovers() {
  reset_stubs
  docker-compose() {
    echo "compose $*" >> "${log}"
    if [ "$1" = "ps" ]; then
      printf '%s\n' "webid" "caddyid" "redisid"
    fi
  }
  docker() {
    echo "docker $*" >> "${log}"
    if [ "$1" = "ps" ]; then
      printf '%s\n' "redisid" "80209f74697e"
    fi
  }
  remove_project_containers
  grep -q "compose ps -q -a web caddy redis" "${log}" || fail "compose ps missed redis"
  grep -q "docker ps -aq --filter name=portfolio-job-matching-web" "${log}" || fail "name filter missing"
  grep -q "docker rm -f webid caddyid redisid 80209f74697e" "${log}" || fail "rm ids: $(cat "${log}")"
  if grep -q "down" "${log}"; then
    fail "down was invoked"
  fi
}

remove_skips_rm_when_nothing_is_running() {
  reset_stubs
  docker() {
    echo "docker $*" >> "${log}"
    if [ "$1" = "rm" ]; then
      fail "rm called with no containers"
    fi
  }
  remove_project_containers
  if grep -q "docker rm" "${log}"; then
    fail "rm ran: $(cat "${log}")"
  fi
}

up_failure_prints_recovery_and_stops() {
  reset_stubs
  cd "${root}"
  docker-compose() {
    echo "compose $*" >> "${log}"
    if [ "$1" = "up" ]; then
      echo "KeyError: 'ContainerConfig'" >> "${log}"
      return 1
    fi
    if [ "$1" = "ps" ]; then
      echo "redisid"
    fi
  }
  docker() {
    echo "docker $*" >> "${log}"
    if [ "$1" = "ps" ]; then
      echo "80209f74697e"
    fi
  }
  curl() { fail "curl ran after up failed"; }
  # deploy_main calls exit, so run it in a subshell.
  if (deploy_main > "${tmpdir}/out" 2> "${err}"); then
    fail "deploy_main succeeded after up failed"
  fi
  grep -q "KeyError: 'ContainerConfig'" "${err}" || fail "recovery missed KeyError"
  grep -q "docker rm -f \$(docker ps -aq --filter name=portfolio-job-matching-web)" "${err}" || fail "recovery command missing"
  grep -q "docker-compose up -d" "${err}" || fail "recovery up missing"
  grep -q "curl -sf http://127.0.0.1:8000/stats" "${err}" || fail "recovery stats missing"
  grep -q "match_results" "${err}" || fail "recovery did not name the cache"
  grep -q "future compose-config change on redis" "${err}" || fail "future-change warning missing"
  if grep -E "docker-compose down( |$)" "${err}" | grep -v "Do not run" >/dev/null; then
    fail "recovery told the operator to run down"
  fi
  rm_line="$(grep -n "docker rm -f" "${log}" | head -n 1 | cut -d: -f1)"
  up_line="$(grep -n "compose up -d" "${log}" | head -n 1 | cut -d: -f1)"
  if [ -z "${rm_line}" ] || [ -z "${up_line}" ] || [ "${rm_line}" -gt "${up_line}" ]; then
    fail "redis was not removed before up: $(cat "${log}")"
  fi
}

health_failure_prints_recovery() {
  reset_stubs
  cd "${root}"
  curl_rc=1
  curl() { echo "curl $*" >> "${log}"; return 1; }
  if (deploy_main > "${tmpdir}/out" 2> "${err}"); then
    fail "deploy_main succeeded without /stats"
  fi
  grep -q "Deploy health check failed" "${err}" || fail "health failure was quiet"
  grep -q "docker-compose up -d" "${err}" || fail "health failure omitted recovery"
  sleeps="$(grep -c "^sleep " "${log}" || true)"
  if [ "${sleeps}" -ne 2 ]; then
    fail "expected 2 health sleeps, got ${sleeps}"
  fi
}

success_removes_redis_then_checks_stats() {
  reset_stubs
  cd "${root}"
  docker-compose() {
    echo "compose $*" >> "${log}"
    if [ "$1" = "ps" ]; then
      printf '%s\n' "webid" "caddyid" "redisid"
    fi
  }
  if ! (deploy_main > "${tmpdir}/out" 2> "${err}"); then
    fail "deploy_main failed on the success path: $(cat "${err}")"
  fi
  grep -q "docker rm -f webid caddyid redisid" "${log}" || fail "success path did not remove redis"
  grep -q "compose up -d" "${log}" || fail "success path did not up"
  grep -q "curl -sf -o /dev/null -w %{http_code}" "${log}" || fail "success path skipped /stats"
  if grep -q "down" "${log}"; then
    fail "success path invoked down"
  fi
}

assert_file_has_no_down_invocation
remove_unions_compose_ps_and_renamed_leftovers
remove_skips_rm_when_nothing_is_running
up_failure_prints_recovery_and_stops
health_failure_prints_recovery
success_removes_redis_then_checks_stats
echo "deploy/test_lightsail.sh: ok"
