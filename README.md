<!--
  Author: Joonyoung Ki

  Project README (English): Portfolio-Job-matching-Web (Smart Job AI), an AI-powered resume-to-job matching service.
  Every statement here was checked against the code on main. Items marked TODO(owner) need to be filled in or verified.
-->
**English** | [한국어](README.ko.md)

# Smart Job AI (Portfolio-Job-matching-Web)

Upload a PDF resume and get the top 10 North American software job postings, ranked by embedding similarity and re-ranked by an LLM, with a short match analysis in Korean and English.

Built by Joonyoung Ki, a CS undergraduate (international student in the US). Target roles: backend / general software engineering.

- Live demo: TODO(owner): URL, or "not public"
- Repo: <https://github.com/junyoungKi/Portfolio-Job-matching-Web>

## Problem

Job boards match on keywords, so a resume has to be compared with postings by hand. This project parses the resume, compares its meaning against collected postings with vector search, and explains why each result fits. It is a personal portfolio project, not a production service.

TODO(owner): adjust this paragraph if your motivation differs.

## Demo

<!-- DEMO SCREENSHOT/GIF: insert here -->
<!-- ![Dashboard demo](docs/images/demo.gif) -->
TODO(owner): add a screenshot or GIF at `docs/images/demo.gif` (upload resume, filters, results with analysis).

## What it does (shipped on `main`)

- Upload a PDF resume with a location (a single city, or "North America" for all hub cities).
- Text extraction with PyMuPDF, then a 1536-dimension embedding (`text-embedding-3-small`).
- Cosine-similarity search over stored postings (top 100 candidates), optionally filtered by experience level, employment type and skills.
- LLM re-ranking (`gpt-4o-mini`) of the candidates; the top 10 are returned.
- Per-result summary and detailed analysis in both Korean and English, generated once per resume/job pair and stored.
- Redis cache of match results (1 hour TTL); caching is skipped if Redis is unreachable.
- Background jobs: LinkedIn crawl every 6 hours with AI-based tagging, and a daily cleanup of old postings.
- React dashboard (Korean/English UI, light/dark theme) served by FastAPI; the older static UI stays at `/legacy`.

## Architecture

```mermaid
flowchart LR
    U[Browser: React dashboard] -->|POST /process-resume<br/>PDF + location| API[FastAPI]
    API -->|parse in worker thread| P[PyMuPDF]
    API -->|embed text| E[OpenAI embeddings]
    API -->|store resume as USER_UPLOAD row| DB[(PostgreSQL + pgvector)]
    U -->|GET /match/id| API
    API <-->|cache, TTL 1h| R[(Redis)]
    API -->|cosine search, top 100<br/>HNSW index on embedding| DB
    API -->|rerank candidates<br/>gpt-4o-mini| L[OpenAI chat]
    API -->|KO/EN analysis, cached in match_analyses| L
    API -->|top 10 JSON| U
```

Scheduled pipeline (APScheduler, runs inside the FastAPI process):

```mermaid
flowchart LR
    S1[Every 6 hours<br/>first run 5s after startup] --> C[Playwright: LinkedIn search + detail pages<br/>8 North American cities]
    C --> D{Same title and company<br/>already stored?}
    D -->|yes| X[Skip]
    D -->|no| T[gpt-4o-mini: type, level, top skills<br/>+ embedding]
    T --> DB[(PostgreSQL + pgvector)]
    S2[Daily at 00:00] --> CL[Delete postings older than 30 days<br/>keep USER_UPLOAD resumes]
    CL --> DB
```

Resumes and job postings share one table (`job_postings`); resumes are rows with `company = "USER_UPLOAD"`, so both live in the same embedding space.

## Tech stack and why

| Component | Used for | Why |
|---|---|---|
| FastAPI + uvicorn | REST API, serves the built dashboard | Native async, simple request handling and typed query params |
| SQLAlchemy (async) + asyncpg | Database access | Non-blocking DB calls inside async handlers |
| PostgreSQL + pgvector | Postings, resumes, embeddings, analyses | One database for relational filters and vector search, no separate vector store |
| HNSW index (`vector_cosine_ops`) | Similarity search | Approximate nearest-neighbour search that scales better than a full scan as postings grow |
| Redis | Match-result cache | Repeat requests skip the vector search and LLM calls |
| OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) | Embeddings, tagging, rerank, analysis | Hosted models; no model serving to maintain |
| Playwright (Chromium) | Crawler | LinkedIn pages need a real browser to render |
| APScheduler | Crawl and cleanup schedule | In-process scheduling, no extra service |
| PyMuPDF | PDF text extraction | Fast, no external dependency |
| React 19 + TypeScript + Vite + Tailwind | Dashboard (`frontend/`) | Typed UI with fast builds |
| Docker (multi-stage) + Docker Compose | Packaging and deployment | Node builds the frontend; only `dist` ships in the Python image |
| Locust | Load testing | Python-based, easy to script against the API |

## Key design decisions and trade-offs

- **Async end to end.** The DB layer uses SQLAlchemy's async engine with asyncpg, and OpenAI calls use `AsyncOpenAI`. PDF parsing is synchronous, so it runs in a thread executor to keep the event loop free. A semaphore (10) limits concurrent parse/embed work. Trade-off: the Redis client in `app/main.py` is the synchronous `redis` package, so cache calls still block the event loop briefly.
- **HNSW index.** Declared in `app/models.py` with `m=16`, `ef_construction=64` and cosine ops. HNSW is approximate and uses more memory and build time than a plain scan; it pays off only with many postings. Whether the planner uses it for the current `/match` query (it orders by a computed `1 - cosine_distance` score) is not confirmed: TODO(owner): run `EXPLAIN ANALYZE` and record the result.
- **Retrieve, then rerank.** Vector search narrows to 100 candidates cheaply; the LLM then orders them using the resume's first 500 characters and each job's title, company and skills. If the LLM call fails, the vector-similarity order is used. Trade-off: extra latency and cost per request, and the rerank sees only a short resume excerpt.
- **Redis cache plus stored analyses.** Match results are cached for 1 hour per resume and filter combination. KO/EN analyses are stored in `match_analyses` so each pair is generated only once. Trade-off: cached results can be up to an hour stale.
- **Resume de-duplication.** An MD5 of resume text + location is stored in `search_keyword`; re-uploading the same combination returns the existing record without re-embedding. Crawled postings still store the crawl keyword (for example "Software Engineer") in that column.
- **Single table for resumes and postings.** Simple to compare; the cost is that every query on postings must exclude `USER_UPLOAD` rows.

## Performance

The load test (`locustfile.py`) sends two request types: `GET /stats` (weight 2) and `POST /process-resume` (weight 1) with `test_resume.pdf` and `location=North America`, with 1-3 s wait between tasks. It does **not** call `/match/{id}`.

Because every upload uses the same file and location, requests after the first should hit the content-hash de-duplication path and skip the embedding call. The numbers below therefore reflect parsing, DB access and the upload path, not repeated OpenAI calls.

<!-- LOCUST GRAPH: insert here (path: docs/images/locust-after-async.png) -->
![Locust report, async version](docs/images/locust-after-async.jpeg)

TODO(owner): confirm this image is the run you want to publish for the async version (it was previously `job_matching_web_locustReport.jpeg` in the repo root). If you prefer a different graph, save it as `docs/images/locust-after-async.png` and update the line above.

| Metric (async version, 100 users) | Result |
|---|---|
| Requests per second | TODO(owner) |
| p50 latency | TODO(owner) |
| p95 latency | TODO(owner) |
| Failure rate | TODO(owner) |
| Test environment (machine, where the server ran, DB location) | TODO(owner) |
| Locust version, run duration, spawn rate | TODO(owner) |

<!-- The report image appears to show: 100 users, 3431 requests, 0 failures, ~44.9 aggregated RPS, p50 57 ms, p95 430 ms. Copy into the table only after confirming the run. -->

**Baseline not measured.** There is no load-test result for the pre-async version, so this README makes no before/after improvement claim.

Other numbers not measured yet:

| Item | Result |
|---|---|
| Recommendation quality (Hit@10 / NDCG) | TODO(owner) |
| `/match` latency (cold, cached) | TODO(owner) |
| Vector query time with/without HNSW | TODO(owner) |
| Stored postings count (`GET /stats`) | TODO(owner) |
| Users | TODO(owner) (none claimed) |

## Run locally

Requirements: Python 3.11 (as in the Dockerfile), PostgreSQL with the `pgvector` extension, an OpenAI API key, Node 20.19+ or 22 (only to build the dashboard). Redis is optional.

```bash
git clone https://github.com/junyoungKi/Portfolio-Job-matching-Web.git
cd Portfolio-Job-matching-Web
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                          # only needed for the crawler
```

Create `.env` in the repo root:

```bash
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/job_match
REDIS_HOST=localhost        # optional; the default host name is "redis" (Docker Compose)
```

Start the backend. On startup it enables the `vector` extension, creates tables, and the first crawl starts about 5 seconds later.

```bash
python run.py               # http://127.0.0.1:8000  (or: uvicorn app.main:app --port 8000)
```

Dashboard, either mode:

```bash
# A) Development: Vite dev server proxies the API (http://localhost:5173)
cd frontend && npm ci && npm run dev

# B) Production-like: build, then FastAPI serves frontend/dist at /
cd frontend && npm ci && npm run build && cd .. && python run.py
```

Without `frontend/dist`, `/` falls back to the legacy UI. API docs: `/docs`. Load test: `locust -f locustfile.py`.

Note: `seed_jobs.py` imports a `SessionLocal` that no longer exists in `app/database.py`, so it does not run on `main`; wait for the crawler or insert postings another way.

## Run with Docker Compose

```bash
# .env as above, but DATABASE_URL must point to a reachable PostgreSQL with pgvector
docker compose up -d --build
# open http://localhost:8000
```

`docker-compose.yml` on `main` starts only `web` and `redis`. It does not start PostgreSQL; you supply the database through `DATABASE_URL`. The Dockerfile is multi-stage (Node 22 builds the dashboard, Python 3.11 runs the API with Chromium for the crawler).

## Deployment (AWS Lightsail)

The service is deployed on an AWS Lightsail instance with docker-compose v1 (details of the instance size and region: TODO(owner)).

```bash
cd ~/Portfolio-Job-matching-Web
git fetch origin && git checkout main && git pull
docker-compose down && docker-compose up -d --build
docker-compose logs -f web             # wait for "Application startup complete"
```

Always run `down` before `up -d --build`; the old `docker-compose` can fail with `KeyError: 'ContainerConfig'` otherwise. If it persists, remove the leftover container: `docker rm -f $(docker ps -aq --filter name=web)`.

Verify:

```bash
curl -s localhost:8000/stats           # {"total_jobs": N}
curl -sI localhost:8000/ | head -1     # 200
```

Rollback: `git log --oneline -n 10`, check out the previous good commit, then `down` and `up -d --build` again. `/legacy/` stays available to compare against the old UI. The documented setup serves plain HTTP on port 8000 (HTTPS is only a roadmap item below).

## Limitations

- No authentication. Resumes are stored as full text, `/match/{id}` uses sequential integer ids, and CORS allows all origins. Do not upload sensitive resumes.
- Uploaded resumes are never deleted; the 30-day cleanup applies to crawled postings only.
- The crawler searches only for "Software Engineer" in 8 cities and reads one result page (25 cards) per city per run. Matching uses the resume embedding, location, and the level, type, and skill filters.
- De-duplication matches on exact title and company, so the same role in two cities counts as one posting.
- Salary is not collected: every crawled posting is stored with the placeholder "Competitive Salary".
- Scraping LinkedIn can be blocked or break when its HTML changes, and may conflict with its terms of use.
- PDF only; scanned PDFs without a text layer produce no usable text.
- Recommendation quality has not been evaluated (no Hit@10 / NDCG), and there are no automated unit tests; `test_concurrent.py` and `locustfile.py` are manual load scripts.
- Each uncached result triggers two LLM calls (KO and EN), made sequentially.

## Roadmap

These exist only in open, unmerged pull requests and are not part of `main`:

- Login / sign-up and a job wishlist (PR #7)
- Structured salary data and extra job sources (PR #8)
- Opt-in HTTPS through a Caddy reverse proxy (PR #5)
- PostgreSQL service in Docker Compose (PR #2) and a Redis connection fix for local runs (PR #1)
- Auto-deploy to Lightsail on merge to `main` (PR #4)

Not started: an evaluation set for recommendation quality, rate limiting, an async Redis client.

## Project layout

```
app/            FastAPI app, models, services (ai, collector, parser)
frontend/       React + Vite dashboard (see frontend/README.md)
static/         Legacy UI served at /legacy
locustfile.py   Load test
docs/images/    README images
```
