**English** | [한국어](README.ko.md)

# Smart Job AI (Portfolio-Job-matching-Web)

Upload a PDF resume and get the top 10 North American software job postings, ranked by embedding similarity and re-ranked by an LLM, with a short match analysis in Korean and English.

Built by Joonyoung Ki, a CS undergraduate (international student in the US). Target roles: backend / general software engineering. This is a personal portfolio project, not a production service.

- Live demo: <https://ai-job-matching.com>
- Repo: <https://github.com/junyoungKi/Portfolio-Job-matching-Web>

Job boards match on keywords, so a resume has to be compared with postings by hand. This project parses the resume, compares its meaning against collected postings with vector search, and explains why each result fits.

## What is implemented

- Upload a PDF resume with a location (one city, or "North America" for every hub city).
- Text extraction with PyMuPDF, then a 1536-dimension embedding (`text-embedding-3-small`).
- Cosine-distance search over stored postings (top 100 candidates), optionally filtered by experience level, employment type, and skills. The query orders by the distance operator, which is the form the HNSW index can use. `hnsw.ef_search` is set to 100 for that transaction. This README does not include an `EXPLAIN` from the live database.
- LLM re-ranking (`gpt-4o-mini`) using the resume's first 500 characters and each job's title, company, and skills. If that call fails, the vector-similarity order is used. The response is the first 10 of that order.
- Per-result summary and analysis in Korean and English. A pair that is not already stored is generated once (both languages in one concurrent batch, resume and job text truncated to 1000 characters) and saved in `match_analyses`.
- Redis cache of match results (1 hour TTL). If Redis is unreachable, the request skips the cache and still runs the search.
- Background jobs, in the FastAPI process: LinkedIn crawl every 6 hours (first run about 5 seconds after startup), daily deletion of crawled postings older than 30 days, and deletion of uploaded resumes older than 1 hour (every 10 minutes), including their match analyses.
- React dashboard (Korean/English UI, light/dark theme) served by FastAPI. The older static UI stays at `/legacy`.

Resumes and job postings share `job_postings`. Resumes are rows with `company = "USER_UPLOAD"`.

## Architecture

```mermaid
flowchart LR
    U[Browser: React dashboard] -->|POST /process-resume<br/>PDF + location| API[FastAPI]
    API -->|parse in worker thread| P[PyMuPDF]
    API -->|embed text| E[OpenAI embeddings]
    API -->|store resume as USER_UPLOAD row| DB[(PostgreSQL + pgvector)]
    U -->|GET /match/id| API
    API <-->|cache, TTL 1h| R[(Redis)]
    API -->|cosine distance, top 100<br/>HNSW index on embedding| DB
    API -->|rerank candidates<br/>gpt-4o-mini| L[OpenAI chat]
    API -->|KO/EN analysis, stored in match_analyses| L
    API -->|top 10 JSON| U
```

Scheduled pipeline (APScheduler):

```mermaid
flowchart LR
    S1[Every 6 hours<br/>first run 5s after startup] --> C[Playwright: LinkedIn search + detail pages<br/>8 North American cities]
    C --> D{Same LinkedIn job id,<br/>or legacy title + company + location?}
    D -->|yes| X[Skip]
    D -->|no| T[gpt-4o-mini: type, level, top skills<br/>+ embedding]
    T --> DB[(PostgreSQL + pgvector)]
    S2[Daily at 00:00<br/>process local time] --> CL[Delete crawled postings older than 30 days]
    S3[Every 10 minutes] --> RL[Delete USER_UPLOAD resumes older than 1 hour<br/>and their match analyses]
    CL --> DB
    RL --> DB
```

`GET /stats` counts rows with `company != "USER_UPLOAD"`. Uploaded resumes are not in that number.

## Tech stack

| Component | Used for | Why |
| --- | --- | --- |
| FastAPI + uvicorn | REST API, serves the built dashboard | Async handlers and typed query params |
| SQLAlchemy (async) + asyncpg | Database access | Non-blocking DB calls |
| PostgreSQL + pgvector | Postings, resumes, embeddings, analyses | Relational filters and vector search in one database |
| HNSW index (`vector_cosine_ops`, `m=16`, `ef_construction=64`) | Similarity search | Approximate nearest-neighbour search as the table grows |
| Redis | Match-result cache | Repeat requests skip the vector search and LLM calls |
| OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) | Embeddings, tagging, rerank, analysis | Hosted models |
| Playwright (Chromium) | Crawler | LinkedIn pages need a browser to render |
| APScheduler | Crawl and cleanup | In-process scheduling |
| PyMuPDF | PDF text extraction | No separate parser service |
| React 19 + TypeScript + Vite + Tailwind | Dashboard (`frontend/`) | Typed UI |
| Docker (multi-stage) + Docker Compose | Packaging and deployment | Node builds the frontend; the Python image ships `dist` only |
| Locust | Manual load script | Scripted against the API |

## Design choices

- **Async I/O.** The database uses SQLAlchemy's async engine, OpenAI uses `AsyncOpenAI`, and the match cache uses one `redis.asyncio` client created at startup. PDF parsing is synchronous, so it runs in a worker thread. A semaphore of 10 wraps each upload's parse and embedding. Korean/English match analyses and the crawler's metadata and embedding calls share a semaphore of 8. The rerank call is not under that semaphore. Cache commands use a 5 second socket timeout.
- **Retrieve, then rerank.** Vector search returns up to 100 candidates. The LLM reorders them. The rerank sees a short resume excerpt, which costs less and can miss detail later in the file.
- **Cache plus stored analyses.** Match JSON is cached for 1 hour per resume and filter set, so a cached response can be up to an hour old. Stored analyses are reused until the resume row is deleted.
- **Resume de-duplication.** An MD5 of resume text plus location is stored in `search_keyword`. Re-uploading the same combination while that row exists returns the existing id and does not embed again. After the row is deleted, a later upload is embedded again. Crawled postings store the crawl keyword in that column (currently `Software Engineer`).
- **One table for resumes and postings.** Comparisons stay in one embedding space. Queries for jobs exclude `USER_UPLOAD`.

## Run locally

Requirements: Python 3.11 (the Dockerfile version), PostgreSQL with the `vector` extension, an OpenAI API key, and Node 22 to build the dashboard. Redis is optional.

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

On startup the app enables the `vector` extension, creates missing tables, and the first crawl starts about 5 seconds later.

```bash
python run.py               # http://127.0.0.1:8000  (or: uvicorn app.main:app --port 8000)
```

Dashboard:

```bash
# A) Development: Vite proxies the API (http://localhost:5173)
cd frontend && npm ci && npm run dev

# B) Production-like: build, then FastAPI serves frontend/dist at /
cd frontend && npm ci && npm run build && cd .. && python run.py
```

Without `frontend/dist`, `/` serves the legacy UI. API docs: `/docs`.

`seed_jobs.py` imports `SessionLocal`, which is not defined in `app/database.py` (`AsyncSessionLocal` is). It does not run on `main`. Wait for the crawler, or insert postings another way.

Tests in `test_cleanup.py`, `test_crawl_batch.py`, `test_crawl_dedup.py`, `test_crawl_timeout.py`, `test_match_hnsw.py`, and `test_match_redis.py` exercise cleanup SQL, crawl dedup and deadlines, and the match query and cache with fakes. They do not need a live database. Nothing in `.github/workflows/` runs them; the only workflow deploys `main`. `python test_concurrent.py` and `locust -f locustfile.py` are manual and expect a running server.

The Locust file sends `GET /stats` (weight 2) and `POST /process-resume` (weight 1) with `test_resume.pdf` and `location=North America`, waiting 1–3 seconds between tasks. It does not call `/match/{id}`. The same file and location hit resume-hash de-duplication after the first upload, so the script does not repeat the embedding call. A screenshot of one async-version run is at `docs/images/locust-after-async.jpeg`. This README does not quote request rate or latency from that image, and there is no measured pre-async baseline.

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

`docker-compose.yml` starts `web`, `redis`, and `caddy`. It does not start PostgreSQL. `caddy` publishes `80:80` and `443:443`, redirects port 80 to HTTPS, and reverse-proxies to `web:8000`. `web` publishes `8000:8000`. The Dockerfile is multi-stage: Node 22 builds the React app, and Python 3.11 runs FastAPI with uvicorn. Chromium is installed for the crawler. The image is how the same toolchain runs on another machine; the host still needs Docker, and Postgres stays at `DATABASE_URL`. `.env` and `deploy/certs/` are not baked into the image.

The certificate on 443 is a Cloudflare Origin Certificate. Cloudflare trusts it. Browsers and curl do not, so an on-host check uses `curl -k`. Visitors see Cloudflare's public certificate.

## Deployment (AWS Lightsail)

Production runs on an AWS Lightsail instance with docker-compose 1.29.2. Compose starts `web`, `redis`, and `caddy`. Public site: <https://ai-job-matching.com>.

Cloudflare proxies the domain and redirects HTTP to HTTPS. SSL/TLS mode is Full (strict): Cloudflare terminates the public certificate, and the origin serves a Cloudflare Origin Certificate on port 443. Switching Cloudflare to Full (strict) before origin port 443 answers causes error 525. Do these steps in order:

1. Put the origin certificate on the server.
2. Start the proxy.
3. Confirm `https://127.0.0.1` works.
4. Open Lightsail TCP 443.
5. Set Cloudflare SSL/TLS to Full (strict).

After step 2, host port 80 redirects to HTTPS. While Cloudflare is still on Flexible it connects to the origin over HTTP, so the public site can redirect-loop until step 5.

### Origin certificate

In the Cloudflare dashboard: SSL/TLS → Origin Server → Create Certificate.

- Hostnames: `ai-job-matching.com` and `*.ai-job-matching.com`.
- Certificate key format: PEM.
- Cloudflare shows the private key once.

On the server, from the repo root:

```bash
mkdir -p deploy/certs
# Paste the Origin Certificate into origin.pem and the Private Key into origin-key.pem.
# Both paths are gitignored: deploy/certs/origin.pem, deploy/certs/origin-key.pem
chmod 644 deploy/certs/origin.pem
chmod 600 deploy/certs/origin-key.pem
```

`deploy/certs/` is gitignored except `.gitignore` and `README.txt`. If the PEM files are missing, Docker creates directories at those paths; remove the directories and put the files back.

### Deploy

A push to `main` runs `.github/workflows/deploy.yml`. The job SSHs to the instance and runs `deploy/lightsail.sh`. The script checks out `origin/main`, removes the `web`, `caddy`, and `redis` containers, then runs `docker-compose up -d --build`. It does not run `git clean` or `docker-compose down`, so gitignored certs and Postgres stay. Redis has no volume; removing it clears the match cache only (`match_results:*`, one-hour TTL).

docker-compose 1.29.2 raises `KeyError: 'ContainerConfig'` when it recreates an existing container. The script removes `web`, `caddy`, and `redis` before `up` so Compose creates them instead of recreating them. Do not use `docker-compose down` or `down -v`.

Repository Actions secrets (and the matching public key in the server user's `~/.ssh/authorized_keys`):

- `LIGHTSAIL_HOST`: public IP or DNS of the instance
- `LIGHTSAIL_USER`: `ubuntu`
- `LIGHTSAIL_SSH_KEY`: private key PEM

Do not commit the private key, the public IP, or any secret value.

To update the instance by hand, from the repo directory, remove the project containers and then start them. Unquoted ids so every id from the filter is removed:

```bash
cd ~/Portfolio-Job-matching-Web
git fetch origin && git checkout main && git pull
ids=$(docker ps -aq --filter name=portfolio-job-matching-web)
if [ -n "$ids" ]; then docker rm -f $ids; fi
docker-compose up -d --build
docker-compose logs -f web             # wait for "Application startup complete"
curl -sf http://127.0.0.1:8000/stats
```

Confirm origin TLS before changing Cloudflare:

```bash
curl -s localhost:8000/stats                 # {"total_jobs": N}
curl -sI localhost:8000/ | head -1           # 200, direct to uvicorn
curl -skI https://127.0.0.1/ | head -1       # 200 via Caddy (-k: Origin CA is not publicly trusted)
curl -sI http://127.0.0.1/ | head -1         # 301 to https://127.0.0.1/
```

Open Lightsail TCP 443 (Networking → IPv4 Firewall → HTTPS). Leave TCP 80 open so the proxy can redirect it. Do not open host port 8000.

Then set Cloudflare SSL/TLS → Overview to Full (strict).

```bash
curl -sI https://ai-job-matching.com/ | head -1    # 200
curl -sI http://ai-job-matching.com/ | head -1     # 301 to https://ai-job-matching.com/
curl -s https://ai-job-matching.com/stats          # {"total_jobs": N}
```

Rollback: check out a previous commit, `docker rm -f` the current `web` and `caddy` container ids, then `up -d --build`. Do not use `docker-compose down -v`. An older compose file publishes port 80 on `web`, so `caddy` has to be gone before that `up`. If Cloudflare is already Full (strict), set it back to Flexible only after origin port 80 serves HTTP again.

`web`, `redis`, and `caddy` use `restart: unless-stopped`. `faulthandler` is enabled for all threads at import, and `PYTHONUNBUFFERED=1` is set. `UVICORN_LOOP` defaults to `uvloop` (`asyncio` selects the other loop). `DB_TCP_KEEPALIVE` defaults to on (`0` skips the keepalive socket option). On 2026-10-22 the `web` container exited once with SIGSEGV in `libcrypto.so.3` (`OOMKilled` was false). The cause is not known. Those switches are not a demonstrated fix, and this README does not claim a later crash has exercised the restart policy.

## Job catalog

The crawler searches LinkedIn for `Software Engineer` in eight cities: Vancouver, Toronto, Seattle, San Francisco, Austin, New York, Los Angeles, and Montreal. Each city is one results page (the URL steps by 25, with `f_TPR=r604800`, the past week). Detail pages are opened for the description. A card is stored only when its LinkedIn job id is not already stored. A card with no id, and a row stored with no id, fall back to normalized title, company, and location. The same title at the same company in another city is stored when the ids differ. `created_at` is set once, when the row is inserted. A later duplicate does not refresh it. Salary is always the placeholder `Competitive Salary`.

One crawl at a time (`max_instances=1`). Each city has a deadline of 1200 seconds and the whole run has a deadline of 18000 seconds (both overridable by env). A timed-out or failed city does not stop the next city. The scheduler prints a `[BATCH]` line per city with collected, saved, skipped, and failed counts, then a run total. This README does not claim a specific live run finished every city.

Once a day, at midnight in the process timezone, crawled rows with `created_at` older than 30 days are deleted. `USER_UPLOAD` rows are not part of that delete. Because duplicates do not reset `created_at`, a posting leaves the table 30 days after it was first saved even if LinkedIn still shows it. It can be inserted again only if a later crawl still sees it on that one past-week page. When most cards on the page are already stored, daily inserts are small. If the rows turning 30 days old outnumber those inserts, `total_jobs` falls. That is the retention rule, not a second delete path.

## Limitations

- No authentication. Resumes are stored as full text, `/match/{id}` uses sequential integer ids, and CORS allows all origins. Do not upload sensitive resumes.
- Uploaded resumes and their match analyses are deleted after 1 hour. Crawled postings are deleted after 30 days.
- The crawler covers one keyword, eight cities, and one past-week results page per city. Scraping LinkedIn can be blocked or break when the HTML changes, and it may conflict with LinkedIn's terms.
- Recommendation quality has not been measured. There is no Hit@10 or NDCG, no rate limit, no accounts, no wishlist, and no structured salary. Postgres is not a Compose service.
- PDF only. A scanned PDF with no text layer produces no usable text. A parse error returns an empty string.
- An uncached `/match` makes one rerank call, then two analysis calls (Korean and English) for each top result that has no stored analysis. Those analysis calls run concurrently, up to the semaphore of 8.
- `GET /stats` is the crawled-row count only. It moves as rows age out and as new cards are inserted.

## Project layout

```
app/            FastAPI app, models, services (ai, collector, parser)
frontend/       React + Vite dashboard (see frontend/README.md)
static/         Legacy UI served at /legacy
Caddyfile       Origin TLS reverse proxy (Cloudflare Origin Certificate)
deploy/certs/   origin.pem and origin-key.pem (gitignored; see README.txt)
deploy/lightsail.sh  Lightsail deploy script run by GitHub Actions
locustfile.py   Manual load script
docs/images/    Locust screenshot
```
