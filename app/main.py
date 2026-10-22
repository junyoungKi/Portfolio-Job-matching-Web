"""
Author: Joonyoung Ki

Main FastAPI application for the Smart Job AI job-matching service.

Responsibilities:
    - Connects to Redis (match-result cache) and PostgreSQL/pgvector (job postings, resumes, analyses).
    - Schedules periodic LinkedIn crawling with AI tagging, daily cleanup of stale crawled
      postings, and frequent cleanup of uploaded resumes.
    - Exposes the REST API: ``/stats``, ``/process-resume`` and ``/match/{resume_id}``.
    - Serves the React dashboard (``frontend/dist``) at ``/`` and the legacy static UI at ``/legacy``.
"""
import sys, asyncio, os, shutil, time, json, redis, hashlib
import aiofiles
import uuid
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from sqlalchemy.exc import DBAPIError, InterfaceError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, or_, text, func
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import engine, get_db, AsyncSessionLocal
from . import models
from .services.parser import resume_parser
from .services.ai import ai_service
from .services.collector import job_collector
from .accounts import auth_router, wishlist_router

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
# Bound every cache command so a stalled Redis cannot hang a request forever.
# The client is async, so the wait yields the event loop instead of blocking other requests.
REDIS_SOCKET_TIMEOUT = 5.0
REDIS_SOCKET_CONNECT_TIMEOUT = 5.0

# Shared async client, created once in the application lifespan and closed on shutdown.
# Redis is an optional cache: if it is unreachable, ``rd`` stays None and caching is skipped.
rd: Optional[redis.asyncio.Redis] = None


def build_redis_client(host: str, port: int) -> redis.asyncio.Redis:
    """Return one async Redis client for the match-result cache.

    ``socket_timeout`` and ``socket_connect_timeout`` cap how long a command or the initial
    handshake may wait. ``socket_keepalive`` enables TCP keepalives on the pooled connection.
    """
    return redis.asyncio.Redis(
        host=host,
        port=port,
        db=0,
        decode_responses=True,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_keepalive=True,
    )


async def _close_redis(client: Optional[redis.asyncio.Redis]) -> None:
    """Close a Redis client and its pool. ``aclose`` is used when this redis-py exposes it."""
    if client is None:
        return
    closer = getattr(client, "aclose", None)
    if closer is None:
        closer = client.close
    try:
        await closer()
    except Exception as e:
        print(f"Redis close error: {e}")


async def _try_connect(host: str, port: int) -> redis.asyncio.Redis:
    """Ping ``host``. Close the client before re-raising so a failed attempt does not leak a pool."""
    client = build_redis_client(host, port)
    try:
        await client.ping()
        return client
    except Exception:
        await _close_redis(client)
        raise


async def connect_redis() -> Optional[redis.asyncio.Redis]:
    """Open the optional match-result cache.

    Tries ``REDIS_HOST`` first, then the ``redis`` service name used by Docker Compose.
    Returns ``None`` when both attempts fail so request handlers skip caching.
    """
    try:
        client = await _try_connect(REDIS_HOST, REDIS_PORT)
        print(f"Redis connection established ({REDIS_HOST}:{REDIS_PORT})")
        return client
    except Exception as e:
        print(f"Redis connection failed, retrying with the fallback address: {e}")
        try:
            client = await _try_connect("redis", 6379)
            print("Redis connection established (fallback: redis)")
            return client
        except Exception as ex:
            print(f"Redis connection failed permanently: {ex}")
            return None

def _positive_int_env(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[BATCH] Ignoring invalid {name}={raw!r}; using {default}")
        return default
    if value <= 0:
        print(f"[BATCH] Ignoring non-positive {name}={value}; using {default}")
        return default
    return value


# One crawl run did not finish, and with max_instances=1 every later tick was skipped.
# Which await blocked is not known. The job deadline is under the 6-hour interval so
# this instance has released the slot before the next tick. Each city has its own
# deadline. The last "[BATCH] Step" line is the await that was in progress.
CRAWL_JOB_TIMEOUT_SECONDS = _positive_int_env("CRAWL_JOB_TIMEOUT_SECONDS", 5 * 60 * 60)
CRAWL_CITY_TIMEOUT_SECONDS = _positive_int_env("CRAWL_CITY_TIMEOUT_SECONDS", 20 * 60)


class _CrawlProgress:
    """The city and step written before each slow await, so a stall names itself."""

    def __init__(self):
        self.city = None
        self.keyword = None
        self.step = "not started"

    def note(self, step):
        self.step = step
        city = self.city or "crawl"
        keyword = self.keyword or "-"
        print(f"[BATCH] Step {city} ({keyword}): {step}")


class _CrawlCounts:
    """Posting counters for one city, or for the whole crawl."""

    def __init__(self):
        self.collected = 0
        self.saved = 0
        self.skipped = 0
        self.failed = 0

    def add(self, other):
        self.collected += other.collected
        self.saved += other.saved
        self.skipped += other.skipped
        self.failed += other.failed


def _duplicate_stmt(job):
    """Lookup used to skip a posting. The key is title + company, not location."""
    return select(models.JobPosting).filter(
        models.JobPosting.title == job["title"],
        models.JobPosting.company == job["company"],
    )


def _posting_from(job, keyword, meta, embedding):
    skills = meta.get("skills", []) if isinstance(meta, dict) else []
    if not isinstance(skills, list):
        skills = [str(skills)]
    return models.JobPosting(
        title=job["title"],
        company=job["company"],
        description=job.get("description"),
        location=job.get("location"),
        salary=job.get("salary"),
        search_keyword=keyword,
        embedding=embedding,
        employment_type=meta.get("employment_type", "Full-time") if isinstance(meta, dict) else "Full-time",
        experience_level=meta.get("experience_level", "Junior") if isinstance(meta, dict) else "Junior",
        skills=", ".join(str(skill) for skill in skills),
    )


async def _rollback_quietly(db):
    """Roll back, and do not let a closed connection escape the except handler.

    A rollback on a connection that is already closed raises ``InterfaceError``.
    That must be logged and swallowed so it cannot replace the original error or
    stop the rest of the city.
    """
    try:
        await db.rollback()
    except (InterfaceError, DBAPIError) as exc:
        print(f"[BATCH] Rollback on a closed connection was ignored: {exc}")
    except Exception as exc:
        print(f"[BATCH] Rollback failed: {exc}")


async def _already_stored(job):
    """Return whether this title and company are already stored. The session closes here."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(_duplicate_stmt(job))
            return result.scalars().first() is not None
        except (InterfaceError, DBAPIError):
            await _rollback_quietly(db)
            raise


async def _commit_posting(posting):
    """Insert one posting on a new session and commit it. The session closes here."""
    async with AsyncSessionLocal() as db:
        db.add(posting)
        try:
            await db.commit()
        except (InterfaceError, DBAPIError):
            await _rollback_quietly(db)
            raise


async def _try_once_more(action, progress, retry_step):
    """Run ``action``. On a closed connection, log it and try once with a fresh session."""
    try:
        return await action()
    except (InterfaceError, DBAPIError) as exc:
        print(f"[BATCH] Database connection failed, retrying once: {exc}")
        progress.note(retry_step)
        return await action()


async def _persist_one_posting(job, keyword, stats, progress):
    """Store one card, or skip it when the same title and company are already stored.

    The duplicate check and the commit each open a session and close it before the next
    await. OpenAI calls sit between those two sessions, so a model call does not hold a
    connection. One posting's failure does not stop the next card.
    """
    title = job.get("title")
    try:
        progress.note(f"duplicate check {title}")
        exists = await _try_once_more(
            lambda: _already_stored(job),
            progress,
            f"duplicate check retry {title}",
        )
        if exists:
            stats.skipped += 1
            print(f"Skipped (duplicate): {title} @ {job.get('company')}")
            return
        progress.note(f"OpenAI metadata {title}")
        meta = await ai_service.extract_job_metadata(job.get("description") or "")
        progress.note(f"OpenAI embedding {title}")
        embedding = await ai_service.get_embedding(job.get("description") or "")
        posting = _posting_from(job, keyword, meta, embedding)
        progress.note(f"commit {title}")
        await _try_once_more(
            lambda: _commit_posting(posting),
            progress,
            f"commit retry {title}",
        )
        stats.saved += 1
        print(f"Saved to DB: {title} @ {job.get('company')}")
    except Exception as inner_e:
        stats.failed += 1
        print(f"Failed to process an individual posting: {inner_e}")


async def _persist_scraped_jobs(jobs, keyword, stats, progress):
    for job in jobs:
        await _persist_one_posting(job, keyword, stats, progress)


async def _crawl_one_city(keyword, city, stats, progress):
    """Scrape ``city``, then store each card on its own short sessions.

    An inner ``TimeoutError`` from a single timed step is reported as a city failure.
    The city deadline in the caller stays the only ``TimeoutError`` that means
    "give up on this city and move on".
    """
    progress.city = city
    progress.keyword = keyword
    try:
        progress.note("scraping LinkedIn")
        jobs = await job_collector.scrape_linkedin(keyword, city, on_step=progress.note)
        stats.collected = len(jobs)
        await _persist_scraped_jobs(jobs, keyword, stats, progress)
    except TimeoutError as exc:
        raise RuntimeError(
            f"Timed out inside the {city} crawl before the city deadline"
        ) from exc


async def _run_crawl(totals, progress):
    """Visit every hub. A timed-out or failed city does not stop the next one."""
    target_keywords = ["Software Engineer"]
    for keyword in target_keywords:
        for city in job_collector.NA_HUBS:
            city_stats = _CrawlCounts()
            started = time.perf_counter()
            try:
                await asyncio.wait_for(
                    _crawl_one_city(keyword, city, city_stats, progress),
                    timeout=CRAWL_CITY_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                print(
                    f"[BATCH] Watchdog: {city} ({keyword}) exceeded "
                    f"{CRAWL_CITY_TIMEOUT_SECONDS}s; last step was {progress.step}. "
                    "Continuing with the next city"
                )
            except Exception as exc:
                print(f"[BATCH] City failed: {city} ({keyword}): {exc}")
            elapsed = time.perf_counter() - started
            totals.add(city_stats)
            print(
                f"[BATCH] {city}: Collected {city_stats.collected} cards, "
                f"saved {city_stats.saved}, skipped {city_stats.skipped} (duplicate), "
                f"failed {city_stats.failed}, took {elapsed:.0f} s"
            )


async def scheduled_north_america_crawl():
    """Crawl LinkedIn for every North American hub, tag new postings, and store them.

    Runs on a schedule. Postings that already exist (same title and company) are skipped.
    A failure on one posting does not stop the rest of that city. The whole job has a
    deadline, and each city has one, so this function returns even when one await does not.
    """
    started = time.perf_counter()
    print(f"[BATCH] Starting scheduled collection and AI tagging: {datetime.now()}")
    totals = _CrawlCounts()
    progress = _CrawlProgress()
    try:
        try:
            await asyncio.wait_for(
                _run_crawl(totals, progress),
                timeout=CRAWL_JOB_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            where = progress.city or "crawl"
            keyword = progress.keyword or "-"
            print(
                f"[BATCH] Watchdog: run exceeded {CRAWL_JOB_TIMEOUT_SECONDS}s; "
                f"last step was {where} ({keyword}): {progress.step}. "
                "Ending this crawl so the next run can start"
            )
        except Exception as e:
            print(f"[BATCH] Batch-level error: {e}")
    finally:
        elapsed = time.perf_counter() - started
        print(
            f"[BATCH] Finished total saved {totals.saved}, skipped {totals.skipped}, "
            f"failed {totals.failed}, took {elapsed:.0f} s"
        )

# Crawled postings stay on the 30-day clock. Uploaded resumes are personal data with no
# login, so they are removed after one hour: long enough for the same session to re-run
# /match with different filters, and short enough that abandoned uploads do not linger.
CRAWLED_POSTING_RETENTION = timedelta(days=30)
USER_RESUME_RETENTION = timedelta(hours=1)
USER_RESUME_CLEANUP_MINUTES = 10


def crawled_posting_delete_stmt(now: datetime):
    """Delete crawled postings older than 30 days. ``USER_UPLOAD`` rows are excluded."""
    cutoff = now - CRAWLED_POSTING_RETENTION
    return delete(models.JobPosting).filter(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.created_at < cutoff,
    )


def expired_user_resume_delete_stmts(now: datetime):
    """Delete ``USER_UPLOAD`` rows older than one hour, and their ``MatchAnalysis`` rows.

    Analyses are removed first, by ``resume_id``, including uploads that never called
    ``/match`` (those simply have no analysis rows). Crawled postings are not selected.
    """
    cutoff = now - USER_RESUME_RETENTION
    expired_ids = select(models.JobPosting.id).filter(
        models.JobPosting.company == "USER_UPLOAD",
        models.JobPosting.created_at < cutoff,
    )
    analyses = delete(models.MatchAnalysis).filter(
        models.MatchAnalysis.resume_id.in_(expired_ids)
    )
    resumes = delete(models.JobPosting).filter(
        models.JobPosting.company == "USER_UPLOAD",
        models.JobPosting.created_at < cutoff,
    )
    return analyses, resumes


async def cleanup_old_jobs():
    """Delete crawled postings older than 30 days.

    ``USER_UPLOAD`` resumes are not deleted here. ``cleanup_expired_resumes`` removes
    them after one hour.
    """
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(crawled_posting_delete_stmt(datetime.now()))
            await db.commit()
            deleted = result.rowcount if result.rowcount is not None else 0
            print(f"[CLEANUP] Deleted {deleted} expired postings")
        except Exception as e:
            await _rollback_quietly(db)
            print(f"[CLEANUP] Error: {e}")


async def cleanup_expired_resumes():
    """Delete uploaded resumes older than one hour, and the analyses stored for them.

    Runs on a short interval so a row does not wait for the midnight crawled-posting job.
    """
    async with AsyncSessionLocal() as db:
        try:
            analyses_stmt, resumes_stmt = expired_user_resume_delete_stmts(datetime.now())
            analysis_result = await db.execute(analyses_stmt)
            resume_result = await db.execute(resumes_stmt)
            await db.commit()
            resumes_deleted = resume_result.rowcount if resume_result.rowcount is not None else 0
            analyses_deleted = analysis_result.rowcount if analysis_result.rowcount is not None else 0
            print(
                f"[CLEANUP] Deleted {resumes_deleted} expired resumes "
                f"and {analyses_deleted} match analyses"
            )
        except Exception as e:
            await _rollback_quietly(db)
            print(f"[CLEANUP] Resume cleanup error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: connect Redis, prepare the database schema and run the scheduler.

    On startup it opens one async Redis client (the match-result cache), enables the pgvector
    extension, creates missing tables and starts the crawl (every 6 hours, first run shortly
    after startup), crawled-posting cleanup (daily at midnight), and uploaded-resume cleanup
    (every 10 minutes) jobs.
    On shutdown it stops the scheduler and closes that Redis client.
    """
    global rd
    rd = await connect_redis()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(models.Base.metadata.create_all)
            print("Database tables are ready")

        scheduler = AsyncIOScheduler()
        # max_instances stays 1 so two crawls never run together. A run that has not
        # returned by the next tick is skipped; the deadline above is what ends that run.
        # coalesce=True collapses missed ticks into one run.
        scheduler.add_job(
            scheduled_north_america_crawl,
            'interval',
            hours=6,
            next_run_time=datetime.now() + timedelta(seconds=5),
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            cleanup_old_jobs,
            'cron',
            hour=0,
            minute=0,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            cleanup_expired_resumes,
            'interval',
            minutes=USER_RESUME_CLEANUP_MINUTES,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        yield
        scheduler.shutdown()
    finally:
        # Drop the shared reference before closing so a request in shutdown skips the cache
        # instead of calling a client whose pool is going away.
        client = rd
        rd = None
        await _close_redis(client)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(wishlist_router)

@app.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Return the number of crawled job postings in the database (user resumes excluded)."""
    stmt = select(func.count(models.JobPosting.id)).filter(models.JobPosting.company != "USER_UPLOAD")
    result = await db.execute(stmt)
    total = result.scalar()
    return {"total_jobs": total}

# Limits concurrent resume parsing/embedding so that bursts of uploads cannot exhaust resources.
parse_semaphore = asyncio.Semaphore(10)

@app.post("/process-resume")
async def process_resume(
    file: UploadFile = File(...), 
    location: str = Query(...), 
    db: AsyncSession = Depends(get_db)
):
    """Receive a PDF resume, parse and embed it, and store it as a ``USER_UPLOAD`` record.

    The upload is written to a uniquely named temporary file, which is always removed afterwards.
    Identical resume/location combinations are de-duplicated through an MD5 content hash
    so the same resume is not parsed and embedded twice while that row still exists. After
    the row is deleted, a later upload of the same file is embedded again. The hash is stored
    in ``search_keyword``; crawled postings keep using that column for the crawl keyword.

    Returns the resume record id that the client passes to ``/match/{resume_id}``.
    """
    os.makedirs("temp_uploads", exist_ok=True)
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join("temp_uploads", unique_filename)
    
    try:
        async with aiofiles.open(file_path, 'wb') as buffer:
            content = await file.read()
            await buffer.write(content)
            await buffer.flush()
            
        # Right after the write, the file can be briefly locked (e.g. by antivirus on Windows),
        # so poll until it becomes readable.
        max_retries = 20
        retry_delay = 0.1
        file_ready = False
        
        for _ in range(max_retries):
            try:
                with open(file_path, 'rb') as f:
                    file_ready = True
                    break
            except PermissionError:
                await asyncio.sleep(retry_delay)
            except FileNotFoundError:
                await asyncio.sleep(retry_delay)
                
        if not file_ready:
            raise HTTPException(status_code=500, detail="The file could not be opened due to a system delay.")

        async with parse_semaphore: 
            try:
                text_content = await resume_parser.extract_text(file_path)
                content_hash = hashlib.md5(f"{text_content}{location}".encode()).hexdigest()
                
                stmt = select(models.JobPosting).filter(
                    models.JobPosting.company == "USER_UPLOAD",
                    models.JobPosting.search_keyword == content_hash
                )
                result = await db.execute(stmt)
                existing = result.scalars().first()

                if existing:
                    return {
                        "status": "success", 
                        "id": existing.id,
                        "parsed_text_length": len(text_content),
                        "parsed_text_preview": str(text_content)
                    }

                # get_embedding may return a coroutine or a plain value, so handle both.
                res = ai_service.get_embedding(text_content)
                if asyncio.iscoroutine(res):
                    resume_vector = await res
                else:
                    resume_vector = res
                
                new_resume = models.JobPosting(
                    title=f"RESUME: {file.filename}", 
                    company="USER_UPLOAD", 
                    description=str(text_content),
                    location=str(location),
                    search_keyword=str(content_hash), 
                    embedding=resume_vector
                )
                db.add(new_resume)
                await db.commit()           
                await db.refresh(new_resume) 
                
                return {
                    "status": "success", 
                    "id": new_resume.id,
                    "parsed_text_length": len(text_content),
                    "parsed_text_preview": str(text_content)
                }
                
            except Exception as e:
                traceback.print_exc()
                print(f"Parsing/saving error: {e}")
                raise HTTPException(status_code=500, detail="Analysis failed")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

@app.get("/match/{resume_id}")
async def match_jobs(
    resume_id: int, 
    db: AsyncSession = Depends(get_db),
    levels: Optional[List[str]] = Query(None),
    types: Optional[List[str]] = Query(None),
    skills: Optional[List[str]] = Query(None)
):
    """Return the top 10 job matches for a stored resume.

    Pipeline: Redis cache lookup -> vector similarity search (top 100 by cosine similarity, filtered
    by location, experience level, employment type and skills) -> LLM re-ranking -> per-job
    Korean/English match analysis (generated once and persisted) -> cache the result for one hour.
    """
    filter_tag = f"{levels}_{types}_{skills}"
    cache_key = f"match_results:v2:{resume_id}:{hashlib.md5(filter_tag.encode()).hexdigest()}"
    
    cache = rd
    if cache:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Redis read error: {e}")

    stmt = select(models.JobPosting).filter(models.JobPosting.id == resume_id)
    result = await db.execute(stmt)
    resume = result.scalars().first()
    if not resume: 
        raise HTTPException(status_code=404, detail="Resume not found")

    # "North America" (or its variants) expands to every hub city; otherwise match the exact location.
    loc_clean = str(resume.location).strip().lower() if resume.location else ""
    if loc_clean in ["north america", "northamerica", "na"]:
        search_locs = job_collector.NA_HUBS
    else:
        search_locs = [resume.location]
        
    score_query = (1 - models.JobPosting.embedding.cosine_distance(resume.embedding)).label("score")
    
    query = select(models.JobPosting, score_query).filter(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.location.in_(search_locs)
    )

    if levels: 
        query = query.filter(models.JobPosting.experience_level.in_(levels))
    if types: 
        query = query.filter(models.JobPosting.employment_type.in_(types))
    if skills:
        skill_filters = [models.JobPosting.skills.ilike(f"%{s}%") for s in skills]
        query = query.filter(or_(*skill_filters))

    query = query.order_by(desc("score")).limit(100)
    
    result = await db.execute(query)
    candidates = result.all()
    
    if not candidates: 
        return []

    jobs_only = [c[0] for c in candidates]
    scores_dict = {c[0].id: c[1] for c in candidates}
    
    # The LLM returns indices into jobs_only in priority order; only the top 10 are returned.
    order = await ai_service.rerank_jobs(resume.description, jobs_only, preferred_skills=skills)
    
    results = []
    for idx in order[:10]:
        if idx >= len(jobs_only): 
            continue
        job = jobs_only[idx]
        
        analysis_stmt = select(models.MatchAnalysis).filter(
            models.MatchAnalysis.resume_id == resume_id, 
            models.MatchAnalysis.job_id == job.id
        )
        analysis_res = await db.execute(analysis_stmt)
        analysis = analysis_res.scalars().first()

        # Analyses are cached in the DB per (resume, job) pair to avoid repeated LLM calls.
        if not analysis:
            ko = await ai_service.analyze_match(resume.description, job.description, lang="ko")
            en = await ai_service.analyze_match(resume.description, job.description, lang="en")
            analysis = models.MatchAnalysis(
                resume_id=resume_id, job_id=job.id,
                summary_ko=ko.get("job_summary", ""), analysis_ko=ko.get("detail_analysis", ""),
                summary_en=en.get("job_summary", ""), analysis_en=en.get("detail_analysis", "")
            )
            db.add(analysis)
            await db.commit()

        results.append({
            "id": job.id,
            "title": str(job.title), "company": str(job.company), 
            "location": str(job.location), "salary": str(job.salary), 
            "match_score": round(float(scores_dict[job.id]), 4),
            "summary_ko": analysis.summary_ko, "analysis_ko": analysis.analysis_ko,
            "summary_en": analysis.summary_en, "analysis_en": analysis.analysis_en,
            "skills": job.skills 
        })

    cache = rd
    if cache:
        await cache.setex(cache_key, 3600, json.dumps(results))
    return results

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY_DIR = os.path.join(_BASE_DIR, "static")
_FRONTEND_DIST = os.path.join(_BASE_DIR, "frontend", "dist")

# Static mounts must come after all API routes are registered (end of file); otherwise they would shadow the API.
# The old static UI is always reachable at /legacy (for comparison and rollback).
@app.get("/legacy", include_in_schema=False)
async def legacy_redirect():
    """Redirect ``/legacy`` to ``/legacy/`` so that relative asset paths in the static UI resolve."""
    return RedirectResponse(url="/legacy/")

app.mount("/legacy", StaticFiles(directory=_LEGACY_DIR, html=True), name="legacy")

# Serve the built React dashboard at "/" when available; otherwise fall back to the legacy UI.
if os.path.isfile(os.path.join(_FRONTEND_DIST, "index.html")):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
else:
    app.mount("/", StaticFiles(directory=_LEGACY_DIR, html=True), name="static")
