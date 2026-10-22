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
import sys, asyncio, os, re, shutil, time, json, redis, hashlib
import aiofiles
import uuid
import traceback
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response

from sqlalchemy.exc import DBAPIError, InterfaceError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, text, func, tuple_
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import (
    engine, get_db, AsyncSessionLocal,
    QUERY_STATS_ENABLED, query_stats_scope, format_query_stats,
)
from . import models
from .services.parser import resume_parser
from .services.ai import ai_service
from .services.collector import job_collector

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


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# How many nearest postings /match asks the database for. Also the hnsw.ef_search used for that
# one transaction: pgvector's default is 40, which cannot fill a LIMIT 100 index scan.
MATCH_CANDIDATE_LIMIT = 100

# Shared cap for OpenAI calls from /match (the KO/EN analyses) and from the crawler
# (metadata + embedding). One process, one limit.
LLM_MAX_CONCURRENCY = 8
llm_semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENCY)

# Per-stage /match timings. Off unless MATCH_TIMING=1. Logs a line and sets a Server-Timing header.
MATCH_TIMING = _env_flag("MATCH_TIMING")

# Set at startup from pg_extension.extversion. pgvector 0.8+ can keep scanning until LIMIT rows
# survive the WHERE filters; older versions post-filter one index pass and can return fewer rows.
hnsw_iterative_scan = False

# create_all() does not add indexes to a table that already exists. This statement is what
# actually creates ix_job_postings_embedding_hnsw on a database created before the model had it.
# It matches the Index() in app/models.py (hnsw, cosine ops, m=16, ef_construction=64).
HNSW_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_job_postings_embedding_hnsw
ON job_postings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
"""

# create_all() does not add a column to a table that already exists. These two statements
# add source_job_id on a database created before the column. They do not rewrite rows,
# and they do not change ix_job_postings_embedding_hnsw. asyncpg rejects several
# commands in one prepared statement, so the column and the index are separate.
SOURCE_JOB_ID_COLUMN_SQL = (
    "ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS source_job_id VARCHAR"
)
SOURCE_JOB_ID_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_job_postings_source_job_id "
    "ON job_postings (source_job_id)"
)

# Trailing digit run on a /jobs/view/<slug>-<id> or /jobs/view/<id> path segment.
_LINKEDIN_JOB_ID = re.compile(r"(?:.*-)?(\d{6,})\Z")


def vector_extension_supports_iterative_scan(version: Optional[str]) -> bool:
    """True when the installed pgvector is at least 0.8 (iterative HNSW scans)."""
    if not version:
        return False
    parts = []
    for piece in str(version).split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits == "":
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]) >= (0, 8, 0)


class _Timer:
    """Collect named stage durations. Does nothing when disabled."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.parts = []
        self._name = None
        self._t = None

    def start(self, name: str) -> None:
        self.stop()
        if not self.enabled:
            return
        self._name = name
        self._t = time.perf_counter()

    def stop(self) -> None:
        if self._t is None:
            return
        self.parts.append((self._name, (time.perf_counter() - self._t) * 1000.0))
        self._name = None
        self._t = None

    def emit(self, response: Response, resume_id: int) -> None:
        self.stop()
        if not self.enabled or not self.parts:
            return
        # Spans with the same name (the analysis lookup and the later insert) add up.
        totals = {}
        order = []
        for name, ms in self.parts:
            if name not in totals:
                order.append(name)
                totals[name] = 0.0
            totals[name] += ms
        header = ", ".join(f"{name};dur={totals[name]:.1f}" for name in order)
        response.headers["Server-Timing"] = header
        print(f"[MATCH_TIMING] resume_id={resume_id} {header}")


async def _bounded(coro):
    """Await ``coro`` while holding one slot of the shared LLM concurrency limit."""
    async with llm_semaphore:
        return await coro


def nearest_postings_stmt(resume_vector, search_locs, levels, types, skills, limit: int = MATCH_CANDIDATE_LIMIT):
    """Top-``limit`` postings by cosine distance to ``resume_vector``.

    ``ORDER BY`` is the ``<=>`` operator itself, with the resume vector bound as a parameter.
    pgvector can use ``ix_job_postings_embedding_hnsw`` for that form. Ordering by
    ``1 - distance`` (a labeled score) cannot. The score is still selected so callers can
    return cosine similarity, which is ``1 - cosine_distance``.
    """
    distance = models.JobPosting.embedding.cosine_distance(resume_vector)
    score = (1 - distance).label("score")
    query = select(models.JobPosting, score).where(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.location.in_(search_locs),
    )
    if levels:
        query = query.where(models.JobPosting.experience_level.in_(levels))
    if types:
        query = query.where(models.JobPosting.employment_type.in_(types))
    if skills:
        query = query.where(or_(*[models.JobPosting.skills.ilike(f"%{s}%") for s in skills]))
    return query.order_by(distance).limit(limit)


async def configure_hnsw_scan(db) -> None:
    """Let this transaction's nearest-neighbour scan fill ``MATCH_CANDIDATE_LIMIT`` rows.

    ``hnsw.ef_search`` defaults to 40, so an index scan would otherwise stop short of LIMIT 100.
    On pgvector >= 0.8, ``hnsw.iterative_scan = strict_order`` keeps walking the index until
    LIMIT rows also pass the WHERE filters. Without it, filters are applied after one pass and
    a selective filter can return fewer than LIMIT rows. Both settings are LOCAL to the
    transaction and do not change the connection's defaults after commit.
    """
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(MATCH_CANDIDATE_LIMIT)}"))
    if hnsw_iterative_scan:
        await db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))


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


def linkedin_job_id(url):
    """Return the LinkedIn job id in ``url``, or None when the URL has no id.

    Card links look like ``/jobs/view/<slug>-<id>`` or ``/jobs/view/<id>``. Search links
    sometimes carry the id only as ``currentJobId``. The id is a trailing run of at least
    six digits, so a year or a short number in a slug is not treated as an id.
    """
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    for key in ("currentJobId", "jobId"):
        for value in query.get(key, []):
            if value.isdigit() and len(value) >= 6:
                return value
    segment = ""
    if parsed.path:
        segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    match = _LINKEDIN_JOB_ID.fullmatch(segment)
    if match:
        return match.group(1)
    return None


def normalize_dedup_text(value):
    """Lowercase and collapse whitespace. None becomes an empty string.

    This is the same transformation as the SQL fallback (``lower``, ``btrim``, and
    collapsed whitespace). It does not treat two company spellings as one company.
    """
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def posting_identity(job):
    """Primary key ``source_job_id``, plus the normalized title, company, and location."""
    if not isinstance(job, dict):
        job = {}
    return {
        "source_job_id": linkedin_job_id(job.get("url")),
        "fallback": (
            normalize_dedup_text(job.get("title")),
            normalize_dedup_text(job.get("company")),
            normalize_dedup_text(job.get("location")),
        ),
    }


def _normalized_column(column):
    collapsed = func.regexp_replace(func.btrim(column), r"\s+", " ", "g")
    return func.lower(collapsed)


def existing_source_ids_stmt(ids):
    """Lookup for LinkedIn job ids that are already stored."""
    return select(models.JobPosting.source_job_id).where(
        models.JobPosting.source_job_id.in_(list(ids))
    )


def existing_fallback_stmt(triples):
    """Normalized title, company, and location, plus ``source_job_id`` (null on legacy rows)."""
    title = _normalized_column(models.JobPosting.title)
    company = _normalized_column(models.JobPosting.company)
    location = _normalized_column(models.JobPosting.location)
    return select(title, company, location, models.JobPosting.source_job_id).where(
        tuple_(title, company, location).in_(list(triples))
    )


def prepare_posting_records(jobs):
    """Return ``(records, invalid_count)``. A record needs a title and a company."""
    records = []
    invalid = 0
    for job in jobs:
        try:
            job["title"]
            job["company"]
        except (KeyError, TypeError) as error:
            invalid += 1
            print(f"Failed to process an individual posting: {error}")
            continue
        records.append({"job": job, **posting_identity(job)})
    return records, invalid


def select_new_postings(records, existing_ids, legacy_fallbacks, any_fallbacks):
    """Split ``records`` into ``(fresh, skipped)``.

    A card with a LinkedIn job id is a duplicate when that id is already stored or
    already in this batch, or when a row with no id has the same normalized title,
    company, and location. Two different ids are kept, including when the title and
    company match and the cities differ.

    A card with no id is a duplicate when that fallback triple matches any stored row
    or any earlier card in this batch. The first card wins.
    """
    fresh = []
    skipped = []
    seen_ids = set()
    seen_no_id = set()
    seen_any = set()
    for record in records:
        job_id = record["source_job_id"]
        fallback = record["fallback"]
        if job_id:
            if (
                job_id in seen_ids
                or job_id in existing_ids
                or fallback in seen_no_id
                or fallback in legacy_fallbacks
            ):
                skipped.append(record)
                continue
            seen_ids.add(job_id)
            seen_any.add(fallback)
            fresh.append(record)
            continue
        if fallback in seen_any or fallback in any_fallbacks:
            skipped.append(record)
            continue
        seen_no_id.add(fallback)
        seen_any.add(fallback)
        fresh.append(record)
    return fresh, skipped


def _dedup_sets_from_rows(id_rows, fallback_rows):
    existing_ids = {row[0] for row in id_rows if row and row[0]}
    legacy = set()
    any_fb = set()
    for row in fallback_rows:
        triple = (row[0], row[1], row[2])
        any_fb.add(triple)
        if len(row) > 3 and row[3] is None:
            legacy.add(triple)
    return existing_ids, legacy, any_fb


async def _read_dedup(db, records):
    """Load stored ids and fallback triples. Skips a query the batch does not need."""
    ids = [record["source_job_id"] for record in records if record["source_job_id"]]
    triples = [record["fallback"] for record in records]
    id_rows = []
    fallback_rows = []
    if ids:
        result = await db.execute(existing_source_ids_stmt(ids))
        id_rows = list(result.all())
    if triples:
        result = await db.execute(existing_fallback_stmt(triples))
        fallback_rows = list(result.all())
    return _dedup_sets_from_rows(id_rows, fallback_rows)


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
        source_job_id=linkedin_job_id(job.get("url")),
        employment_type=meta.get("employment_type", "Full-time") if isinstance(meta, dict) else "Full-time",
        experience_level=meta.get("experience_level", "Junior") if isinstance(meta, dict) else "Junior",
        skills=", ".join(str(skill) for skill in skills),
    )


async def _enrich_posting(job, progress=None):
    """Metadata and embedding for one new posting. Each call takes one semaphore slot.

    The step is recorded immediately before each model await so a stall names that call.
    """
    description = job.get("description") or ""
    title = job.get("title")

    async def metadata():
        if progress is not None:
            progress.note(f"OpenAI metadata {title}")
        return await ai_service.extract_job_metadata(description)

    async def embedding():
        if progress is not None:
            progress.note(f"OpenAI embedding {title}")
        return await ai_service.get_embedding(description)

    meta, vector = await asyncio.gather(_bounded(metadata()), _bounded(embedding()))
    return meta, vector


async def _commit_postings(db, specs) -> int:
    """Insert ``specs`` in one commit. If that commit fails, retry each row on its own.

    A single bad row then rolls back only itself. The other rows of the city are still saved.
    The caller owns ``db`` (the measurement script and the batch tests). The scheduled crawl
    uses ``_insert_postings``, which opens a fresh session per commit.
    """
    built = []
    for spec in specs:
        try:
            built.append((spec, _posting_from(**spec)))
        except Exception as build_error:
            print(f"Failed to process an individual posting: {build_error}")
    if not built:
        return 0
    db.add_all([row for _, row in built])
    try:
        await db.commit()
    except Exception as batch_error:
        await db.rollback()
        db.expunge_all()
        print(f"[BATCH] Batch commit failed, retrying each posting: {batch_error}")
        saved = 0
        for spec, _row in built:
            try:
                db.add(_posting_from(**spec))
                await db.commit()
                saved += 1
                print(f"Saved to DB: {spec['job']['title']} @ {spec['job']['company']}")
            except Exception as row_error:
                await db.rollback()
                print(f"Failed to process an individual posting: {row_error}")
        return saved
    for spec, _row in built:
        print(f"Saved to DB: {spec['job']['title']} @ {spec['job']['company']}")
    return len(built)


async def store_scraped_jobs(db, jobs, keyword: str) -> int:
    """Insert scraped jobs that are not already stored.

    The primary key is the LinkedIn job id on the card URL. A card with no id, and a
    stored row with no id, fall back to normalized title + company + location. One id
    lookup and one fallback lookup for the city (either is skipped when the batch does
    not need it), then bounded concurrent metadata and embedding calls for the new jobs
    only, then one ``add_all`` / commit. The first card in the batch wins. A failure
    while tagging one job skips that job and does not abort the city.
    """
    if not QUERY_STATS_ENABLED:
        return await _store_scraped_jobs(db, jobs, keyword)
    started = time.perf_counter()
    saved = 0
    with query_stats_scope() as stats:
        try:
            saved = await _store_scraped_jobs(db, jobs, keyword)
        finally:
            wall = time.perf_counter() - started
            print(format_query_stats("CRAWL", keyword, stats, wall) + f" inserted={saved}")
    return saved


def _log_skipped(records):
    for record in records:
        job = record["job"]
        print(f"Skipped (duplicate): {job.get('title')} @ {job.get('company')}")


async def _store_scraped_jobs(db, jobs, keyword: str) -> int:
    records, _invalid = prepare_posting_records(jobs)
    if not records:
        return 0

    existing_ids, legacy_fallbacks, any_fallbacks = await _read_dedup(db, records)
    # End the read transaction before the OpenAI calls so this connection is not held
    # for the whole city. expire_on_commit is False; the keys above are plain values.
    await db.commit()

    fresh_records, skipped = select_new_postings(
        records, existing_ids, legacy_fallbacks, any_fallbacks
    )
    _log_skipped(skipped)
    if not fresh_records:
        return 0
    fresh = [record["job"] for record in fresh_records]

    outcomes = await asyncio.gather(
        *(_enrich_posting(job) for job in fresh),
        return_exceptions=True,
    )
    specs = []
    for job, outcome in zip(fresh, outcomes):
        if isinstance(outcome, Exception):
            print(f"Failed to process an individual posting: {outcome}")
            continue
        meta, embedding = outcome
        specs.append({"job": job, "keyword": keyword, "meta": meta, "embedding": embedding})
    return await _commit_postings(db, specs)


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


async def _try_once_more(action, progress, retry_step):
    """Run ``action``. On a closed connection, log it and try once with a fresh session."""
    try:
        return await action()
    except (InterfaceError, DBAPIError) as exc:
        print(f"[BATCH] Database connection failed, retrying once: {exc}")
        progress.note(retry_step)
        return await action()


async def _lookup_dedup(records):
    """Load dedup keys on a new session. The session closes before the caller continues."""
    async with AsyncSessionLocal() as db:
        try:
            return await _read_dedup(db, records)
        except (InterfaceError, DBAPIError):
            await _rollback_quietly(db)
            raise


async def _insert_postings(specs):
    """Insert ``specs`` on a new session and commit once. The session closes here."""
    async with AsyncSessionLocal() as db:
        try:
            db.add_all([_posting_from(**spec) for spec in specs])
            await db.commit()
            return len(specs)
        except (InterfaceError, DBAPIError):
            await _rollback_quietly(db)
            raise
        except Exception:
            await _rollback_quietly(db)
            raise


async def _persist_scraped_jobs(jobs, keyword, stats, progress):
    """Store one city's cards with one lookup round and one commit, on short sessions.

    The lookup session closes before any OpenAI call. The commit uses a new session.
    A closed connection is retried once. Any other batch-commit failure is retried per row,
    each row on its own session, so one bad row does not drop the city. The duplicate key
    is the LinkedIn job id, then normalized title + company + location. Repeats inside
    the batch count as skipped.
    """
    records, invalid = prepare_posting_records(jobs)
    stats.failed += invalid
    if not records:
        return

    progress.note("duplicate check")
    try:
        existing_ids, legacy_fallbacks, any_fallbacks = await _try_once_more(
            lambda: _lookup_dedup(records),
            progress,
            "duplicate check retry",
        )
    except Exception as exc:
        stats.failed += len(records)
        print(f"Failed to process an individual posting: {exc}")
        return

    fresh_records, skipped = select_new_postings(
        records, existing_ids, legacy_fallbacks, any_fallbacks
    )
    stats.skipped += len(skipped)
    _log_skipped(skipped)
    if not fresh_records:
        return
    fresh = [record["job"] for record in fresh_records]

    outcomes = await asyncio.gather(
        *(_enrich_posting(job, progress) for job in fresh),
        return_exceptions=True,
    )
    specs = []
    for job, outcome in zip(fresh, outcomes):
        if isinstance(outcome, Exception):
            stats.failed += 1
            print(f"Failed to process an individual posting: {outcome}")
            continue
        meta, embedding = outcome
        specs.append({"job": job, "keyword": keyword, "meta": meta, "embedding": embedding})
    if not specs:
        return

    progress.note("commit")
    try:
        saved = await _try_once_more(
            lambda: _insert_postings(specs),
            progress,
            "commit retry",
        )
    except (InterfaceError, DBAPIError) as exc:
        stats.failed += len(specs)
        print(f"Failed to process an individual posting: {exc}")
        return
    except Exception as exc:
        print(f"[BATCH] Batch commit failed, retrying each posting: {exc}")
        saved = 0
        for spec in specs:
            title = spec["job"].get("title")
            try:
                progress.note(f"commit {title}")
                await _try_once_more(
                    lambda spec=spec: _insert_postings([spec]),
                    progress,
                    f"commit retry {title}",
                )
                saved += 1
                print(f"Saved to DB: {spec['job']['title']} @ {spec['job']['company']}")
            except Exception as row_error:
                stats.failed += 1
                print(f"Failed to process an individual posting: {row_error}")
        stats.saved += saved
        return

    stats.saved += saved
    for spec in specs:
        print(f"Saved to DB: {spec['job']['title']} @ {spec['job']['company']}")


async def _persist_one_posting(job, keyword, stats, progress):
    """Store one card through the city batch path.

    Kept so a single card still has its own lookup session and commit session. A city
    passes the whole list to ``_persist_scraped_jobs`` instead of calling this in a loop.
    """
    await _persist_scraped_jobs([job], keyword, stats, progress)


async def _crawl_one_city(keyword, city, stats, progress):
    """Scrape ``city``, then store the cards in one batch on short sessions.

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

    Runs on a schedule. A posting is skipped when its LinkedIn job id is already stored.
    A card with no id, and a stored row with no id, fall back to normalized title,
    company, and location. Each city is one batch: the duplicate-check queries and the
    insert commit each use their own session, closed before the next OpenAI call and
    before the next city. A failure on
    one posting does not stop the rest of that city. The whole job has a deadline, and each
    city has one, so this function returns even when one await does not.
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
            # Existing databases already have job_postings, so create_all will not add
            # source_job_id or the HNSW index. Both statements are no-ops when present.
            await conn.execute(text(SOURCE_JOB_ID_COLUMN_SQL))
            await conn.execute(text(SOURCE_JOB_ID_INDEX_SQL))
            await conn.execute(text(HNSW_INDEX_SQL))
            version = None
            version_result = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            if version_result is not None and hasattr(version_result, "scalar"):
                version = version_result.scalar()
            global hnsw_iterative_scan
            hnsw_iterative_scan = vector_extension_supports_iterative_scan(version)
            print(
                f"Database tables are ready (pgvector {version}; "
                f"hnsw iterative scan {'on' if hnsw_iterative_scan else 'off'})"
            )

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


@app.middleware("http")
async def _query_stats_middleware(request, call_next):
    """When QUERY_STATS=1, log statements, DB time, wall time and DB-time share for the request."""
    if not QUERY_STATS_ENABLED:
        return await call_next(request)
    started = time.perf_counter()
    with query_stats_scope() as stats:
        response = await call_next(request)
    wall = time.perf_counter() - started
    print(format_query_stats(request.method, request.url.path, stats, wall))
    return response

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
    response: Response,
    db: AsyncSession = Depends(get_db),
    levels: Optional[List[str]] = Query(None),
    types: Optional[List[str]] = Query(None),
    skills: Optional[List[str]] = Query(None)
):
    """Return the top 10 job matches for a stored resume.

    Pipeline: Redis cache lookup -> vector similarity search (top 100 by cosine distance, filtered
    by location, experience level, employment type and skills) -> LLM re-ranking -> Korean/English
    match analysis (loaded in one query, generated concurrently, written in one commit) -> cache
    the result for one hour. The JSON keys are unchanged.
    """
    timer = _Timer(MATCH_TIMING)
    filter_tag = f"{levels}_{types}_{skills}"
    cache_key = f"match_results:{resume_id}:{hashlib.md5(filter_tag.encode()).hexdigest()}"

    timer.start("redis")
    cache = rd
    if cache:
        try:
            cached = await cache.get(cache_key)
            if cached:
                timer.emit(response, resume_id)
                return json.loads(cached)
        except Exception as e:
            print(f"Redis read error: {e}")
    timer.stop()

    timer.start("vector")
    result = await db.execute(select(models.JobPosting).filter(models.JobPosting.id == resume_id))
    resume = result.scalars().first()
    if not resume:
        timer.emit(response, resume_id)
        raise HTTPException(status_code=404, detail="Resume not found")

    # "North America" (or its variants) expands to every hub city; otherwise match the exact location.
    loc_clean = str(resume.location).strip().lower() if resume.location else ""
    if loc_clean in ["north america", "northamerica", "na"]:
        search_locs = job_collector.NA_HUBS
    else:
        search_locs = [resume.location]

    # Copy the embedding out before the later commit. It is bound as a query parameter;
    # the ORDER BY below is the <=> operator, which is the form the HNSW index can use.
    resume_vector = resume.embedding
    if resume_vector is not None and not isinstance(resume_vector, list):
        resume_vector = list(resume_vector)
    resume_text = resume.description

    await configure_hnsw_scan(db)
    result = await db.execute(nearest_postings_stmt(
        resume_vector, search_locs, levels, types, skills
    ))
    candidates = result.all()
    timer.stop()

    if not candidates:
        timer.emit(response, resume_id)
        return []

    jobs_only = [c[0] for c in candidates]
    scores_dict = {c[0].id: c[1] for c in candidates}

    # The rows are loaded. expire_on_commit=False keeps them usable. Commit so the connection
    # goes back to the pool before the rerank call, and so SET LOCAL does not leak.
    await db.commit()

    timer.start("rerank")
    order = await ai_service.rerank_jobs(resume_text, jobs_only, preferred_skills=skills)
    timer.stop()

    ranked_jobs = []
    for idx in order[:10]:
        try:
            if idx >= len(jobs_only):
                continue
            ranked_jobs.append(jobs_only[idx])
        except (TypeError, IndexError):
            continue

    timer.start("db_write")
    job_ids = list(dict.fromkeys(job.id for job in ranked_jobs))
    analyses = {}
    if job_ids:
        cached_result = await db.execute(
            select(models.MatchAnalysis)
            .filter(
                models.MatchAnalysis.resume_id == resume_id,
                models.MatchAnalysis.job_id.in_(job_ids),
            )
            .order_by(models.MatchAnalysis.id)
        )
        for row in cached_result.scalars().all():
            analyses.setdefault(
                row.job_id,
                (row.summary_ko, row.analysis_ko, row.summary_en, row.analysis_en),
            )
    timer.stop()

    jobs_by_id = {job.id: job for job in ranked_jobs}
    missing_jobs = [jobs_by_id[job_id] for job_id in job_ids if job_id not in analyses]

    if missing_jobs:
        # Release the connection again. The tasks below use plain strings only, never this session.
        await db.commit()
        timer.start("analysis")
        generated = await asyncio.gather(*[
            _bounded(ai_service.analyze_match(resume_text, job.description, lang=lang))
            for job in missing_jobs
            for lang in ("ko", "en")
        ])
        timer.stop()

        new_rows = []
        for n, job in enumerate(missing_jobs):
            ko, en = generated[2 * n], generated[2 * n + 1]
            row = models.MatchAnalysis(
                resume_id=resume_id, job_id=job.id,
                summary_ko=ko.get("job_summary", ""), analysis_ko=ko.get("detail_analysis", ""),
                summary_en=en.get("job_summary", ""), analysis_en=en.get("detail_analysis", "")
            )
            new_rows.append(row)
            analyses[job.id] = (row.summary_ko, row.analysis_ko, row.summary_en, row.analysis_en)
        timer.start("db_write")
        db.add_all(new_rows)
        await db.commit()
        timer.stop()

    results = []
    for job in ranked_jobs:
        summary_ko, analysis_ko, summary_en, analysis_en = analyses[job.id]
        results.append({
            "title": str(job.title), "company": str(job.company),
            "location": str(job.location), "salary": str(job.salary),
            "match_score": round(float(scores_dict[job.id]), 4),
            "summary_ko": summary_ko, "analysis_ko": analysis_ko,
            "summary_en": summary_en, "analysis_en": analysis_en,
            "skills": job.skills
        })

    cache = rd
    if cache:
        try:
            await cache.setex(cache_key, 3600, json.dumps(results))
        except Exception as e:
            print(f"Redis write error: {e}")
    timer.emit(response, resume_id)
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
