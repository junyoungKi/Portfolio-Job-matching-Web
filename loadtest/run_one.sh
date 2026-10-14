#!/usr/bin/env bash
# One load-test run against one checkout, from a clean state, using the stub LLM.
#
#   loadtest/run_one.sh <label> <app_dir>
#
#   <label>    name for the result files, e.g. baseline-warm or fixed-cold
#   <app_dir>  checkout of the code to test (a `git worktree`, or this repository)
#
# Run it from the checkout that contains this script (the fixed commit). The script itself,
# locustfile.py, the fake OpenAI server and the seed script always come from that checkout, so
# the baseline and the fixed commit are driven by identical tooling; only <app_dir> differs.
#
# Every run: reseeds the database (deterministic data), flushes Redis db 0, starts the fake OpenAI
# server and the backend (crawl disabled, one uvicorn process), runs an unrecorded warm-up, then
# the measured Locust run, and writes results/<label>_stats.csv, <label>.html and a summary.
#
# Settings (environment variables, defaults in brackets):
#   DATABASE_URL        asyncpg URL of a disposable database (required; it is TRUNCATED)
#   REDIS_HOST          [127.0.0.1]  Redis db 0 on this host is FLUSHED
#   REDIS_PORT          [6379]
#   LOAD_MODE           [warm] or cold, see locustfile.py
#   USERS               [20]    SPAWN_RATE [2]    DURATION [5m]    WARMUP [1m]
#   SEED_JOBS           [400]   job postings seeded before each run
#   CHAT_LATENCY_MS     [400]   EMBED_LATENCY_MS [100]   fixed latency of the fake OpenAI server
#   PORT                [8000]  FAKE_PORT [9999]
#   PYTHON              [python3]
set -euo pipefail

LABEL="${1:?usage: run_one.sh <label> <app_dir>}"
APP_DIR="$(cd "${2:?usage: run_one.sh <label> <app_dir>}" && pwd)"
TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATABASE_URL:?set DATABASE_URL to a disposable asyncpg database URL}"

PYTHON="${PYTHON:-python3}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}" REDIS_PORT="${REDIS_PORT:-6379}"
export LOAD_MODE="${LOAD_MODE:-warm}"
USERS="${USERS:-20}" SPAWN_RATE="${SPAWN_RATE:-2}" DURATION="${DURATION:-5m}" WARMUP="${WARMUP:-1m}"
SEED_JOBS="${SEED_JOBS:-400}"
CHAT_LATENCY_MS="${CHAT_LATENCY_MS:-400}" EMBED_LATENCY_MS="${EMBED_LATENCY_MS:-100}"
PORT="${PORT:-8000}" FAKE_PORT="${FAKE_PORT:-9999}"
RESULTS="$TOOLS_DIR/loadtest/results"
mkdir -p "$RESULTS"

PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_for() {  # wait_for <url> <seconds>
  for _ in $(seq 1 "$2"); do curl -fsS -o /dev/null "$1" 2>/dev/null && return 0; sleep 1; done
  echo "timed out waiting for $1" >&2; return 1
}

echo "== [$LABEL] code under test: $APP_DIR ($(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown))"
echo "== [$LABEL] mode=$LOAD_MODE users=$USERS spawn=$SPAWN_RATE duration=$DURATION warmup=$WARMUP jobs=$SEED_JOBS chat=${CHAT_LATENCY_MS}ms embed=${EMBED_LATENCY_MS}ms"

echo "== reseed database and flush Redis"
(cd "$TOOLS_DIR" && OPENAI_API_KEY=stub "$PYTHON" loadtest/seed_load_data.py --jobs "$SEED_JOBS" --reset)
"$PYTHON" - <<PY
import redis
redis.Redis(host="$REDIS_HOST", port=int("$REDIS_PORT"), db=0).flushdb()
PY

echo "== start fake OpenAI on :$FAKE_PORT"
"$PYTHON" "$TOOLS_DIR/loadtest/fake_openai.py" --port "$FAKE_PORT" \
  --chat-latency-ms "$CHAT_LATENCY_MS" --embed-latency-ms "$EMBED_LATENCY_MS" &
PIDS+=($!)
wait_for "http://127.0.0.1:$FAKE_PORT/stub-stats" 30

echo "== start backend on :$PORT (one uvicorn process, crawl disabled)"
(cd "$APP_DIR" && OPENAI_BASE_URL="http://127.0.0.1:$FAKE_PORT/v1" OPENAI_API_KEY=stub PYTHONPATH="$APP_DIR" \
  exec "$PYTHON" "$TOOLS_DIR/loadtest/serve_no_crawl.py" --port "$PORT") &
PIDS+=($!)
wait_for "http://127.0.0.1:$PORT/stats" 90

LOCUST=("$PYTHON" -m locust -f "$TOOLS_DIR/locustfile.py" --headless --host "http://127.0.0.1:$PORT" -u "$USERS" -r "$SPAWN_RATE")

if [ "$WARMUP" != "0" ]; then
  echo "== warm-up ($WARMUP, not recorded)"
  "${LOCUST[@]}" -t "$WARMUP" --only-summary >/dev/null 2>&1 || true
fi

echo "== measured run ($DURATION)"
"${LOCUST[@]}" -t "$DURATION" --csv "$RESULTS/$LABEL" --html "$RESULTS/$LABEL.html" --only-summary

curl -fsS "http://127.0.0.1:$FAKE_PORT/stub-stats" > "$RESULTS/$LABEL-stub-stats.json" || true
echo "== fake OpenAI calls served (warm-up + run): $(cat "$RESULTS/$LABEL-stub-stats.json" 2>/dev/null)"
"$PYTHON" "$TOOLS_DIR/loadtest/summarize.py" "$RESULTS/${LABEL}_stats.csv"
