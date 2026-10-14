# Load testing: comparing before and after fairly

This guide explains how to measure the backend before and after the async hardening change
(concurrent `/match` LLM calls, batched analysis lookup, explicit pool and OpenAI settings) so
that the two numbers are comparable. **No measured results are published here.** The tables below
are empty templates; fill them in from your own runs.

Contents: [What is measured](#what-is-measured) | [Rules for a fair comparison](#rules-for-a-fair-comparison) | [Stub LLM or real OpenAI](#stub-llm-or-real-openai) | [One-time setup](#one-time-setup) | [Run the comparison](#run-the-comparison) | [Reading the numbers](#reading-the-numbers) | [Results template](#results-template) | [Configuration reference](#configuration-reference) | [Single worker and multi-worker risk](#single-worker-and-multi-worker-risk)

## What is measured

`locustfile.py` exercises all three endpoints:

| Locust row | Endpoint | What it costs the server |
|---|---|---|
| `/stats` | `GET /stats` | one cheap count query |
| `/process-resume`, `/process-resume (warm setup)`, `/process-resume (cold setup)` | `POST /process-resume` | PDF parse in a thread, one embedding call (skipped when the same resume text and location is already stored), one insert |
| `/match/[id] (warm)` or `/match/[id] (cold)` | `GET /match/{id}` | Redis lookup; on a miss: vector search, 1 re-rank LLM call, then up to 10 jobs x 2 (KO, EN) analysis LLM calls, then writes |

Two modes (`LOAD_MODE`):

- `warm` (default): each user uploads one resume from a fixed, deterministic pool of 20 and then repeats `/match` with 6 filter combinations. After the first pass most requests are Redis cache hits. This measures the steady state, where `/match` is mostly a cache read.
- `cold`: every `/match` request is made on a brand-new resume (a unique upload first), so it misses Redis, has no stored analyses and runs the full LLM pipeline. The setup upload is its own row (`/process-resume (cold setup)`); read the `/match/[id] (cold)` row for cold `/match` numbers. This is the mode where the concurrency change matters.

Run both modes on both commits. Warm and cold numbers answer different questions and must not be mixed into one aggregate.

## Rules for a fair comparison

1. **Same machine, same conditions.** Run baseline and fixed on the same host, one after the other, with nothing else heavy running. Prefer a machine that is not a laptop on battery, and keep Locust, the fake LLM, Redis, Postgres and the backend all on it (or all in the same fixed topology both times).
2. **Same data.** Every run starts with `loadtest/seed_load_data.py --reset` (deterministic postings, deterministic stub embeddings, fixed seed), which also truncates uploaded resumes and stored analyses, followed by `ANALYZE`. `run_one.sh` does this for you.
3. **Same Locust parameters.** Same users (`-u`), spawn rate (`-r`), duration (`-t`), `LOAD_MODE`, `LOCUST_SEED` and wait times for every run. Write them in the results table.
4. **Warm-up.** Each run does an unrecorded warm-up phase (default 1 minute) before the measured run, so connection pools, imports and (in warm mode) caches are in the same state. Cold mode still needs the warm-up for pools and imports; its `/match` requests stay cold because every resume is new.
5. **Cold vs cached are separate runs.** For a cold run Redis db 0 is flushed and the database is reseeded. For a warm run the warm-up fills the cache and the measured run reuses it. Never compare a cold baseline against a warm fixed run.
6. **Same LLM behavior.** Use the same stub LLM with the same latency for both commits (see below). Do not compare a stub run against a real-OpenAI run.
7. **Same server configuration.** One uvicorn process, same environment variables, same Postgres and Redis settings. The pool defaults are unchanged by the fix (5 + 10 connections, as in SQLAlchemy), so the comparison isolates the code change; tune pool and concurrency settings in a separate experiment.
8. **No crawl.** The app schedules a LinkedIn crawl 5 seconds after startup. `loadtest/serve_no_crawl.py` replaces the scraper with a no-op so it cannot launch Chromium or hit LinkedIn during the test. It works on any commit without changing application code.
9. **Repeat and interleave.** Run each configuration at least 3 times in the order baseline, fixed, baseline, fixed, ... and compare medians of the runs. A single run is only an anecdote; judge noise by how much repeated runs of the same commit differ.
10. **Compare only runs with the same failure behavior.** A run with failures is not comparable to one without. Look at the failure column first.

## Stub LLM or real OpenAI

### Recommended: the fake OpenAI server

`loadtest/fake_openai.py` is a small OpenAI-compatible server for the two endpoints the backend uses (`/v1/embeddings`, `/v1/chat/completions`). It returns deterministic content in the shape the app expects (metadata JSON, a re-rank index list, KO/EN analysis JSON) after a fixed delay (default 400 ms per chat call and 100 ms per embedding, set with `CHAT_LATENCY_MS` and `EMBED_LATENCY_MS`). The backend is pointed at it with `OPENAI_BASE_URL` (read by the OpenAI SDK itself) and a dummy `OPENAI_API_KEY`. It needs no key, has no cost and no rate limits.

Why a separate server instead of an in-app `LLM_STUB` switch: the baseline commit does not contain any such switch, so an in-app flag could only stub the fixed commit and would make the comparison unfair. The fake server is configured purely through environment variables, so the baseline and the fixed commit talk to exactly the same stub.

Remember what the stub does and does not model: it models a fixed LLM latency, not real OpenAI behavior (variable latency, rate limiting, 429/5xx retries, timeouts). Results show how the server code copes with slow external calls, not how fast the real service would be. Pick the latency to represent the situation you care about, and state it with the results.

The confirmation that the stub was used is the `fake OpenAI calls served` line printed at the end of each run (also saved to `loadtest/results/<label>-stub-stats.json`); it must be non-zero.

### Optional: real OpenAI

If you do run against the real API, be aware of cost and limits first:

- One cold `/match` makes 1 re-rank call plus up to 20 analysis calls (10 jobs x KO and EN), and the upload before it makes 1 embedding call. A 5-minute cold run with 20 users can issue thousands of calls.
- `gpt-4o-mini` and `text-embedding-3-small` are billed per token; check the current pricing page and multiply by the call counts above before starting.
- The account has per-minute request and token limits. If you hit them the SDK retries (`OPENAI_MAX_RETRIES`), and failed analyses fall back to placeholder text that is then stored, which makes results meaningless. Keep users low, keep runs short, and expect run-to-run variance from OpenAI's own latency. Seeded stub embeddings are not valid for real embeddings, so reseed the data with real embeddings if you go this way.

For before/after comparisons, prefer the stub.

## One-time setup

Requirements: Python 3.11+, PostgreSQL with the `pgvector` extension, Redis, and the Python dependencies.

```bash
pip install -r requirements-dev.txt       # app, Locust and test dependencies

# Use a throwaway database. The load test TRUNCATES job_postings and match_analyses
# and FLUSHES Redis db 0 on every run.
export DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/job_match_loadtest
export REDIS_HOST=127.0.0.1
```

Find the two commits and create a separate checkout for the baseline, so you never have to switch branches while measuring and the tooling always comes from the same place. The baseline is the commit this change branched from (`529e2a1`, the head of `main` at that time; confirm with `git log`):

```bash
git fetch origin
git switch cursor/async-hardening-load-testing-f311      # the fixed commit, which contains the tooling
export FIXED_SHA=$(git rev-parse HEAD)
export BASE_SHA=529e2a1                                   # pre-fix commit
git worktree add ../jm-baseline "$BASE_SHA"               # equivalent of `git checkout $BASE_SHA` in its own directory
git -C ../jm-baseline log --oneline -1
```

If you prefer a plain `git checkout <sha>` in the same directory, copy `locustfile.py` and `loadtest/` somewhere outside the repository first and run the tooling from there, because they do not exist on the baseline commit.

## Run the comparison

`loadtest/run_one.sh <label> <app_dir>` performs one complete run from a clean state: reseed the database, flush Redis, start the fake OpenAI server and the backend (single uvicorn process, crawl disabled), run the unrecorded warm-up, run the measured Locust test, and print a summary. It must be started from the fixed checkout, which provides the tooling; `<app_dir>` selects which code is tested.

Example parameters (use the same ones for every run; adjust to your machine):

```bash
export USERS=20 SPAWN_RATE=2 DURATION=5m WARMUP=1m SEED_JOBS=400
export CHAT_LATENCY_MS=400 EMBED_LATENCY_MS=100
```

Cold `/match` requests are slow (several LLM calls each), so with the closed-loop Locust users the cold runs finish far fewer requests than warm runs. That is expected; compare latency and failures at equal user count, and use a longer `DURATION` if the cold sample is small (aim for at least a few hundred `/match` requests per run).

### Baseline (pre-fix commit)

```bash
# from the fixed checkout (contains loadtest/ and the new locustfile.py)
LOAD_MODE=warm loadtest/run_one.sh baseline-warm-1 ../jm-baseline
LOAD_MODE=cold loadtest/run_one.sh baseline-cold-1 ../jm-baseline
```

### Fixed commit

```bash
LOAD_MODE=warm loadtest/run_one.sh fixed-warm-1 .
LOAD_MODE=cold loadtest/run_one.sh fixed-cold-1 .
```

Repeat with `-2` and `-3` suffixes, interleaving baseline and fixed. The results land in `loadtest/results/` (git-ignored): `<label>_stats.csv`, `<label>.html` and `<label>-stub-stats.json`. Print any set of runs as one markdown table:

```bash
python3 loadtest/summarize.py loadtest/results/baseline-cold-*_stats.csv loadtest/results/fixed-cold-*_stats.csv
```

### The same thing by hand (what the script does)

```bash
# 0. clean state (run from the fixed checkout)
python3 loadtest/seed_load_data.py --jobs 400 --reset
python3 -c "import redis; redis.Redis(host='127.0.0.1').flushdb()"

# 1. fake LLM in one terminal
python3 loadtest/fake_openai.py --port 9999 --chat-latency-ms 400 --embed-latency-ms 100

# 2. backend in a second terminal: baseline checkout shown; use the fixed checkout for the other run
cd ../jm-baseline
OPENAI_BASE_URL=http://127.0.0.1:9999/v1 OPENAI_API_KEY=stub PYTHONPATH=. \
  python3 /path/to/fixed/loadtest/serve_no_crawl.py --port 8000

# 3. Locust in a third terminal, from the fixed checkout: warm-up (discard), then the measured run
LOAD_MODE=cold python3 -m locust -f locustfile.py --headless --host http://127.0.0.1:8000 -u 20 -r 2 -t 1m --only-summary
LOAD_MODE=cold python3 -m locust -f locustfile.py --headless --host http://127.0.0.1:8000 -u 20 -r 2 -t 5m \
  --csv loadtest/results/baseline-cold-1 --html loadtest/results/baseline-cold-1.html
```

Stop and restart everything (and redo step 0) between runs.

### Finding where it saturates (optional)

A single user count shows latency under one load. To see where each version degrades, repeat the same procedure at increasing user counts (for example `USERS=5, 10, 20, 40, 80`) on both commits, and watch for the point where failures appear or p95 jumps. With the default pool (5 + 10 connections) and 8 concurrent LLM calls, the limits you hit first are the ones you set; change `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` and `LLM_MAX_CONCURRENCY` one at a time in a separate series and record them.

## Reading the numbers

- **p50 (median)**: half of the requests were faster than this. It describes the typical request. For `/match (warm)` it mostly shows cache-hit cost; for `/match (cold)` it shows the full pipeline.
- **p95**: 95% of requests were faster. It describes the slow tail, which is what users notice under load and what usually degrades first when something queues (the DB pool, the LLM concurrency limit, the event loop). Do not average it across endpoints.
- **RPS** (`Requests/s`): completed requests per second over the run. Locust users are closed-loop: each waits for its response, then thinks for 1 to 3 seconds. A slower server therefore completes fewer requests at the same user count, so RPS and latency move together. Use RPS to compare how much work finished, and latency to compare how long each request took; neither alone is enough. For a throughput ceiling use the saturation series above.
- **Failure rate**: failed requests divided by total requests. HTTP errors count, and so do empty `/match` results (that means the database was not seeded) and uploads without an id. Any non-zero failure rate must be explained before you compare latency: failed requests are often fast and flatter the numbers.
- **Read rows, not only the aggregate.** The aggregate mixes a 3 ms `/stats` with a multi-second cold `/match`; its p50 mostly reflects the request mix. Compare each endpoint row between commits.
- **Interpreting a difference.** Compare medians across the repeated runs and look at how far repeats of the same commit differ. A difference smaller than that spread is noise. Do not extrapolate a stub-LLM result to real OpenAI latency.
- **Sanity checks** per run: failures are zero or equal; the stub call count is non-zero; the `/match` row has a reasonable number of requests; the same Locust parameters were used.

## Results template

Copy this table into your notes or PR and fill it from your own runs. Leave a cell empty rather than guessing.

Environment (same for every row):

| Item | Value |
|---|---|
| Machine (CPU, RAM, OS) | |
| Postgres / Redis versions and where they run | |
| Python and Locust versions | |
| Baseline commit | `529e2a1` (or yours) |
| Fixed commit | |
| Seed jobs, Locust users, spawn rate, duration, warm-up | |
| Stub latency (chat / embedding) or real OpenAI | |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `LLM_MAX_CONCURRENCY` | defaults: 5 / 10 / 8 |

Results (median of 3 interleaved runs, or list each run):

| Mode | Endpoint | Commit | Requests | Failure rate | p50 (ms) | p95 (ms) | RPS |
|---|---|---|---:|---:|---:|---:|---:|
| warm | `/match/[id] (warm)` | baseline | | | | | |
| warm | `/match/[id] (warm)` | fixed | | | | | |
| warm | `/process-resume` | baseline | | | | | |
| warm | `/process-resume` | fixed | | | | | |
| warm | `/stats` | baseline | | | | | |
| warm | `/stats` | fixed | | | | | |
| cold | `/match/[id] (cold)` | baseline | | | | | |
| cold | `/match/[id] (cold)` | fixed | | | | | |
| cold | `/process-resume (cold setup)` | baseline | | | | | |
| cold | `/process-resume (cold setup)` | fixed | | | | | |
| cold | `/stats` | baseline | | | | | |
| cold | `/stats` | fixed | | | | | |

## Configuration reference

Environment variables read by the backend (all optional):

| Variable | Default | Effect |
|---|---|---|
| `DB_POOL_SIZE` | `5` | persistent DB connections per process |
| `DB_MAX_OVERFLOW` | `10` | extra connections allowed under load, per process |
| `DB_POOL_TIMEOUT` | `30` | seconds a request waits for a free connection before failing |
| `OPENAI_TIMEOUT_SECONDS` | `30` | timeout of one OpenAI request attempt (the SDK default is 600) |
| `OPENAI_MAX_RETRIES` | `2` | SDK retries per request; worst case for one call is about timeout x (retries + 1) |
| `LLM_MAX_CONCURRENCY` | `8` | OpenAI chat calls in flight at once, across all requests in the process |
| `MAX_UPLOAD_MB` | `10` | largest accepted resume upload; larger files get HTTP 413 |
| `OPENAI_BASE_URL` | unset | read by the OpenAI SDK; used here to point the backend at the fake server |
| `REDIS_HOST`, `REDIS_PORT` | `redis`, `6379` | match cache location (falls back to host `redis` if unreachable) |

Redis errors never fail a request: a cache read or write error is logged and the response is served without the cache.

## Single worker and multi-worker risk

The backend runs as one uvicorn process (`Dockerfile`, `run.py`), and all measurements above assume that. Do not add `--workers N` to the load test, or to production, without first changing the scheduler:

- The APScheduler jobs are started inside the application lifespan, so every worker would start its own scheduler. The LinkedIn crawl (every 6 hours and 5 seconds after each start) and the cleanup jobs would run N times in parallel, launching N Chromium instances against LinkedIn and competing with API traffic.
- Pool, semaphore and Redis client are per process. N workers can open up to N x (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) database connections (keep this below Postgres `max_connections`) and N x `LLM_MAX_CONCURRENCY` simultaneous OpenAI calls.
- The in-process crawl is also a reason results with the crawl enabled are not comparable; the load-test wrapper disables it.

To scale out, move the scheduler into its own process (or guard it so exactly one process runs it) first, then add workers and re-measure.
