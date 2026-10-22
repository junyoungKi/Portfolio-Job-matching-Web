#!/usr/bin/env bash
# Runs deploy/lightsail.sh the way .github/workflows/deploy.yml does
# (`bash -s < deploy/lightsail.sh`) against fake docker, docker-compose, git,
# curl and sleep. The fake docker keeps container state in a directory and
# reproduces the two behaviours that broke past deploys:
#   - docker-compose prints 64-char ids, plain `docker ps` prints 12-char ids
#     unless --no-trunc is given;
#   - removing a container that is already being removed fails.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

export HOME="${work}/home"
mkdir -p "${HOME}/Portfolio-Job-matching-Web" "${work}/bin" "${work}/state"
export STATE="${work}/state"
export PATH="${work}/bin:${PATH}"
export LIGHTSAIL_HEALTH_ATTEMPTS=3
export LIGHTSAIL_HEALTH_SLEEP=0

cat >"${work}/bin/git" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat >"${work}/bin/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat >"${work}/bin/curl" <<'EOF'
#!/usr/bin/env bash
if [ -e "${STATE}/up_done" ]; then
  echo 200
  exit 0
fi
exit 22
EOF

cat >"${work}/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -u
cmd="$1"; shift
case "${cmd}" in
  ps)
    notrunc=0
    for a in "$@"; do [ "${a}" = "--no-trunc" ] && notrunc=1; done
    for f in "${STATE}"/c_*; do
      [ -e "${f}" ] || continue
      id="$(basename "${f}")"; id="${id#c_}"
      if [ "${notrunc}" -eq 1 ]; then echo "${id}"; else echo "${id:0:12}"; fi
    done
    ;;
  rm)
    shift # -f
    target="$1"
    if [ -e "${STATE}/removing_${target}" ]; then
      echo "Error response from daemon: removal of container ${target} is already in progress" >&2
      exit 1
    fi
    matched=""
    for f in "${STATE}"/c_*; do
      [ -e "${f}" ] || continue
      id="$(basename "${f}")"; id="${id#c_}"
      case "${id}" in "${target}"*) matched="${id}" ;; esac
    done
    if [ -z "${matched}" ]; then
      echo "Error: No such container: ${target}" >&2
      exit 1
    fi
    rm -f "${STATE}/c_${matched}"
    echo "${target}"
    ;;
  *) exit 0 ;;
esac
EOF

cat >"${work}/bin/docker-compose" <<'EOF'
#!/usr/bin/env bash
set -u
case "$1" in
  build) exit 0 ;;
  ps)
    for f in "${STATE}"/c_*; do
      [ -e "${f}" ] || continue
      id="$(basename "${f}")"; echo "${id#c_}"
    done
    ;;
  up)
    # compose v1 cannot recreate an existing container.
    if ls "${STATE}"/c_* >/dev/null 2>&1; then
      echo "KeyError: 'ContainerConfig'" >&2
      exit 1
    fi
    for s in web caddy redis; do
      touch "${STATE}/c_$(printf '%s' "${s}" | sha256sum | cut -c1-64)"
    done
    touch "${STATE}/up_done"
    ;;
  *) exit 0 ;;
esac
EOF
chmod +x "${work}"/bin/*

seed() {
  rm -f "${STATE}"/c_* "${STATE}"/up_done
  for s in web caddy redis; do
    touch "${STATE}/c_$(printf 'old-%s' "${s}" | sha256sum | cut -c1-64)"
  done
  touch "${STATE}/c_$(printf 'renamed-redis' | sha256sum | cut -c1-64)"
}

fail() { echo "FAIL: $*" >&2; exit 1; }

seed
bash -s <"${root}/deploy/lightsail.sh" >"${work}/out" 2>"${work}/err" ||
  { cat "${work}/out" "${work}/err" >&2; fail "piped deploy exited non-zero"; }
[ -e "${STATE}/up_done" ] || fail "docker-compose up -d never ran"
[ "$(ls "${STATE}"/c_* | wc -l)" -eq 3 ] || fail "expected exactly three new containers"
grep -q "unbound variable" "${work}/err" && fail "unbound variable under bash -s"

seed
bash "${root}/deploy/lightsail.sh" >/dev/null 2>&1 || fail "direct run exited non-zero"
[ -e "${STATE}/up_done" ] || fail "direct run: up -d never ran"

echo "deploy/test_lightsail_e2e.sh: ok"
