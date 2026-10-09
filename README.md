<!--
  Author: Joonyoung Ki

  Project README (English): Portfolio-Job-matching-Web (Smart Job AI), an AI-powered resume-to-job matching service.
  Every statement here was checked against the code on main. Items marked TODO(owner) need to be filled in or verified.
-->

**English** | [한국어](README.ko.md)

# Smart Job AI (Portfolio-Job-matching-Web)

Upload a PDF resume and get the top 10 North American software job postings, ranked by embedding similarity and re-ranked by an LLM, with a short match analysis in Korean and English.

Built by Joonyoung Ki, a CS undergraduate (international student in the US). Target roles: backend / general software engineering.

- Live demo: <https://ai-job-matching.com>
- Repo: <https://github.com/junyoungKi/Portfolio-Job-matching-Web>

## Problem

Job boards match on keywords, so a resume has to be compared with postings by hand. This project parses the resume, compares its meaning against collected postings with vector search, and explains why each result fits. It is a personal portfolio project, not a production service.

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
- Background jobs: LinkedIn crawl every 6 hours with AI-based tagging, daily deletion of crawled postings older than 30 days, and deletion of uploaded resumes older than 1 hour.
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
    S2[Daily at 00:00] --> CL[Delete crawled postings older than 30 days]
    S3[Every 10 minutes] --> RL[Delete USER_UPLOAD resumes older than 1 hour<br/>and their match analyses]
    CL --> DB
    RL --> DB
```

Resumes and job postings share one table (`job_postings`); resumes are rows with `company = "USER_UPLOAD"`, so both live in the same embedding space.

## Tech stack and why

| Component                                        | Used for                                | Why                                                                                       |
| ------------------------------------------------ | --------------------------------------- | ----------------------------------------------------------------------------------------- |
| FastAPI + uvicorn                                | REST API, serves the built dashboard    | Native async, simple request handling and typed query params                              |
| SQLAlchemy (async) + asyncpg                     | Database access                         | Non-blocking DB calls inside async handlers                                               |
| PostgreSQL + pgvector                            | Postings, resumes, embeddings, analyses | One database for relational filters and vector search, no separate vector store           |
| HNSW index (`vector_cosine_ops`)                 | Similarity search                       | Approximate nearest-neighbour search that scales better than a full scan as postings grow |
| Redis                                            | Match-result cache                      | Repeat requests skip the vector search and LLM calls                                      |
| OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) | Embeddings, tagging, rerank, analysis   | Hosted models; no model serving to maintain                                               |
| Playwright (Chromium)                            | Crawler                                 | LinkedIn pages need a real browser to render                                              |
| APScheduler                                      | Crawl and cleanup schedule              | In-process scheduling, no extra service                                                   |
| PyMuPDF                                          | PDF text extraction                     | Fast, no external dependency                                                              |
| React 19 + TypeScript + Vite + Tailwind          | Dashboard (`frontend/`)                 | Typed UI with fast builds                                                                 |
| Docker (multi-stage) + Docker Compose            | Packaging and deployment                | Node builds the frontend; only `dist` ships in the Python image                           |
| Locust                                           | Load testing                            | Python-based, easy to script against the API                                              |

## Key design decisions and trade-offs

- **Async end to end.** The DB layer uses SQLAlchemy's async engine with asyncpg, OpenAI calls use `AsyncOpenAI`, and the match cache uses one `redis.asyncio` client created during application startup. PDF parsing is synchronous, so it runs in a thread executor to keep the event loop free. A semaphore (10) limits concurrent parse/embed work. Cache commands use a 5 second socket timeout so a stalled Redis cannot hold a request open indefinitely.
- **HNSW index.** Declared in `app/models.py` with `m=16`, `ef_construction=64` and cosine ops. HNSW is approximate and uses more memory and build time than a plain scan; it pays off only with many postings. Whether the planner uses it for the current `/match` query (it orders by a computed `1 - cosine_distance` score) is not confirmed: TODO(owner): run `EXPLAIN ANALYZE` and record the result.
- **Retrieve, then rerank.** Vector search narrows to 100 candidates cheaply; the LLM then orders them using the resume's first 500 characters and each job's title, company and skills. If the LLM call fails, the vector-similarity order is used. Trade-off: extra latency and cost per request, and the rerank sees only a short resume excerpt.
- **Redis cache plus stored analyses.** Match results are cached for 1 hour per resume and filter combination. KO/EN analyses are stored in `match_analyses` so each pair is generated only once. Trade-off: cached results can be up to an hour stale.
- **Resume de-duplication.** An MD5 of resume text + location is stored in `search_keyword`; re-uploading the same combination while that row still exists returns the existing record without re-embedding. After the row is deleted, a later upload is embedded again. Crawled postings still store the crawl keyword (for example "Software Engineer") in that column.
- **Single table for resumes and postings.** Simple to compare; the cost is that every query on postings must exclude `USER_UPLOAD` rows.

## Performance

The load test (`locustfile.py`) sends two request types: `GET /stats` (weight 2) and `POST /process-resume` (weight 1) with `test_resume.pdf` and `location=North America`, with 1-3 s wait between tasks. It does **not** call `/match/{id}`.

Because every upload uses the same file and location, requests after the first should hit the content-hash de-duplication path and skip the embedding call. The numbers below therefore reflect parsing, DB access and the upload path, not repeated OpenAI calls.

<!-- LOCUST GRAPH: insert here (path: docs/images/locust-after-async.png) -->

![Locust report, async version](docs/images/locust-after-async.jpeg)

TODO(owner): confirm this image is the run you want to publish for the async version (it was previously `job_matching_web_locustReport.jpeg` in the repo root). If you prefer a different graph, save it as `docs/images/locust-after-async.png` and update the line above.

| Metric (async version, 100 users)                             | Result      |
| ------------------------------------------------------------- | ----------- |
| Requests per second                                           | TODO(owner) |
| p50 latency                                                   | TODO(owner) |
| p95 latency                                                   | TODO(owner) |
| Failure rate                                                  | TODO(owner) |
| Test environment (machine, where the server ran, DB location) | TODO(owner) |
| Locust version, run duration, spawn rate                      | TODO(owner) |

<!-- The report image appears to show: 100 users, 3431 requests, 0 failures, ~44.9 aggregated RPS, p50 57 ms, p95 430 ms. Copy into the table only after confirming the run. -->

**Baseline not measured.** There is no load-test result for the pre-async version, so this README makes no before/after improvement claim.

Other numbers not measured yet:

| Item                                   | Result                     |
| -------------------------------------- | -------------------------- |
| Recommendation quality (Hit@10 / NDCG) | TODO(owner)                |
| `/match` latency (cold, cached)        | TODO(owner)                |
| Vector query time with/without HNSW    | TODO(owner)                |
| Stored postings count (`GET /stats`)   | TODO(owner)                |
| Users                                  | TODO(owner) (none claimed) |

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
# .env as above, but DATABASE_URL must point to a reachable PostgreSQL with pgvector.
# The Caddy proxy needs the origin certificate files in deploy/certs/ (see Deployment).
# Without those files, start only the app:
#   docker compose up -d --build web redis
docker compose up -d --build
# http://localhost:8000 reaches the app directly
# http://localhost redirects to HTTPS; https://localhost is the Caddy proxy
```

`docker-compose.yml` starts `web`, `redis`, and `caddy`. It does not start PostgreSQL; you supply the database through `DATABASE_URL`. `caddy` publishes `"80:80"` and `"443:443"`, redirects port 80 to HTTPS, and reverse-proxies to the `web` service on port 8000 over the compose network. `web` publishes `"8000:8000"` for on-host checks and does not publish `"80:8000"`. The Dockerfile is multi-stage: Node 22 builds the React app into the image, and Python 3.11 runs FastAPI with uvicorn (Chromium is included for the crawler).

The certificate mounted on 443 is a Cloudflare Origin Certificate. Cloudflare trusts it. Browsers and curl do not, so an on-host check uses `curl -k`. Visitors see Cloudflare's public certificate, not this one.

## Deployment (AWS Lightsail)

Production runs on an AWS Lightsail instance with docker-compose 1.29.2. Compose starts `web`, `redis`, and `caddy`. `web` is FastAPI served by uvicorn, and the React app is built into the image. `caddy` terminates TLS with a Cloudflare Origin Certificate and proxies to `web`. Instance size and region: TODO(owner).

Public site: <https://ai-job-matching.com>

Cloudflare proxies the domain (orange-cloud A record for `https://ai-job-matching.com`) and redirects HTTP to HTTPS (Always Use HTTPS). Visitors use HTTPS. Cloudflare terminates the public certificate. The origin uses a Cloudflare Origin Certificate on port 443, and the hop from Cloudflare to Lightsail is HTTPS. The SSL/TLS mode is Full (strict).

Resumes and similar personal data are sent to the server, so the public site needs HTTPS even before accounts exist. HTTPS is also there so a later login feature can protect credentials and sessions. Full (strict) keeps that encryption on the Lightsail hop as well.

Do these steps in order. Switching Cloudflare to Full (strict) before origin port 443 answers causes error 525.

1. Put the origin certificate on the server.
2. Start the proxy.
3. Confirm `https://127.0.0.1` (origin port 443) works.
4. Open Lightsail TCP 443.
5. Set Cloudflare SSL/TLS to Full (strict).

After step 2, host port 80 redirects to HTTPS. While Cloudflare is still on Flexible it connects to the origin over HTTP, so the public site can redirect-loop until step 5. Finish steps 3–5 as soon as the on-host HTTPS check passes.

### Origin certificate

In the Cloudflare dashboard for this zone: SSL/TLS → Origin Server → Create Certificate.

- Hostnames: `ai-job-matching.com` and `*.ai-job-matching.com` (that pair covers www and the apex; listing `ai-job-matching.com` and `www.ai-job-matching.com` is enough if you do not need other names).
- Certificate key format: PEM.
- Keep the default validity unless you need a shorter one. Cloudflare shows the private key once.

On the server, from the repo root:

```bash
mkdir -p deploy/certs
# Paste the Origin Certificate into origin.pem and the Private Key into origin-key.pem.
# Example filenames (both gitignored): deploy/certs/origin.pem, deploy/certs/origin-key.pem
chmod 644 deploy/certs/origin.pem
chmod 600 deploy/certs/origin-key.pem
```

`deploy/certs/` is gitignored except `.gitignore` and `README.txt`. Do not commit the certificate or the private key. The files have to exist before `up`. If they are missing, Docker creates directories at those paths; remove the directories and put the PEM files back.

### Deploy

Merging to `main` deploys via GitHub Actions. `.github/workflows/deploy.yml` runs on a GitHub-hosted runner, SSHs to the Lightsail instance, and runs `deploy/lightsail.sh`. The job fails if that script fails. One-time setup is three repository Actions secrets, plus the matching public key in the server user's `~/.ssh/authorized_keys`:

- `LIGHTSAIL_HOST`: public IP or DNS of the instance
- `LIGHTSAIL_USER`: `ubuntu`
- `LIGHTSAIL_SSH_KEY`: private key PEM

Do not commit the private key, the public IP, or any secret value.

```bash
cd ~/Portfolio-Job-matching-Web
git fetch origin && git checkout main && git pull

# docker-compose 1.29.2 raises KeyError: 'ContainerConfig' when it recreates an
# existing container. Remove the web container (and caddy, if it already exists)
# with docker rm before up. Do not use `docker-compose down -v` (that deletes volumes).
# `docker-compose ps -q` targets the service, so the directory name "Web" is not a problem.
for svc in web caddy; do
  id=$(docker-compose ps -q "$svc")
  if [ -n "$id" ]; then docker rm -f "$id"; fi
done
docker-compose up -d --build
docker-compose logs -f web             # wait for "Application startup complete"
```

Confirm origin TLS on the instance before changing Cloudflare:

```bash
curl -s localhost:8000/stats                 # {"total_jobs": N}
curl -sI localhost:8000/ | head -1           # 200, direct to uvicorn
curl -skI https://127.0.0.1/ | head -1       # 200 via Caddy (-k: Origin CA is not publicly trusted)
curl -sI http://127.0.0.1/ | head -1         # 301 to https://127.0.0.1/
```

Open Lightsail TCP 443: instance → Networking → IPv4 Firewall → add HTTPS, TCP 443. Leave TCP 80 open so the proxy can redirect it. Do not open host port 8000; that mapping is only for checks on the instance.

Then set Cloudflare SSL/TLS → Overview to Full (strict).

Verify the public site:

```bash
curl -sI https://ai-job-matching.com/ | head -1    # 200
curl -sI http://ai-job-matching.com/ | head -1     # 301 to https://ai-job-matching.com/
curl -s https://ai-job-matching.com/stats          # {"total_jobs": N}
```

Rollback: `git log --oneline -n 10`. While this compose file is still checked out, note the container ids (`docker-compose ps -q web` and `docker-compose ps -q caddy`), check out the previous good commit, `docker rm -f` those ids, then `up -d --build`. Do not use `docker-compose down -v`. The previous compose publishes port 80 on `web`, so caddy must be gone before that `up`. If Cloudflare is already Full (strict), set it back to Flexible only after origin port 80 serves HTTP again; Full (strict) against an HTTP origin returns error 525. `/legacy/` stays available to compare against the old UI.

## Limitations

- No authentication. Resumes are stored as full text, `/match/{id}` uses sequential integer ids, and CORS allows all origins. Do not upload sensitive resumes.
- Uploaded resumes and their match analyses are deleted after 1 hour. The 30-day cleanup applies to crawled postings only.
- The crawler searches only for "Software Engineer" in 8 cities and reads one result page (25 cards) per city per run. Matching uses the resume embedding, location, and the level, type, and skill filters.
- De-duplication matches on exact title and company, so the same role in two cities counts as one posting.
- Salary is not collected: every crawled posting is stored with the placeholder "Competitive Salary".
- Scraping LinkedIn can be blocked or break when its HTML changes, and may conflict with its terms of use.
- PDF only; scanned PDFs without a text layer produce no usable text.
- Recommendation quality has not been evaluated (no Hit@10 / NDCG), and there are no automated unit tests; `test_concurrent.py` and `locustfile.py` are manual load scripts.
- Each uncached result triggers two LLM calls (KO and EN), made sequentially.

## Roadmap

- Login / sign-up and a job wishlist (PR #7)
- Structured salary data and extra job sources (PR #8)
- PostgreSQL service in Docker Compose (PR #2) and a Redis connection fix for local runs (PR #1)

Not started: an evaluation set for recommendation quality, rate limiting.

## Project layout

```
app/            FastAPI app, models, services (ai, collector, parser)
frontend/       React + Vite dashboard (see frontend/README.md)
static/         Legacy UI served at /legacy
Caddyfile       Origin TLS reverse proxy (Cloudflare Origin Certificate)
deploy/certs/   origin.pem and origin-key.pem (gitignored; see README.txt)
deploy/lightsail.sh  Lightsail deploy script run by GitHub Actions
locustfile.py   Load test
docs/images/    README images
```
