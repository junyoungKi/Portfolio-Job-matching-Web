"""Match batching, the index-friendly vector query, stage timing and the SQL counter.

No database, Redis or OpenAI key: the session, cache and LLM are fakes.
"""
import asyncio
import json
import os
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from sqlalchemy.dialects import postgresql

import app.main as main
from app.database import format_query_stats, note_query_end, note_query_start, query_stats_scope
from app.main import app
from test_match_redis import Rows, _get, _use_db


class RecordingSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.statements = []
        self.executes = 0
        self.commits = 0
        self.added = []

    async def execute(self, stmt):
        sql = getattr(stmt, "text", None)
        if isinstance(sql, str) and sql.lstrip().upper().startswith("SET "):
            self.statements.append(sql.strip())
            return Rows()
        self.executes += 1
        self.statements.append("query")
        if not self._responses:
            raise AssertionError("database was queried more times than expected")
        return self._responses.pop(0)

    def add_all(self, rows):
        self.added.append(list(rows))

    async def commit(self):
        self.commits += 1


def _job(job_id):
    return SimpleNamespace(
        id=job_id,
        title=f"Job {job_id}",
        company="Acme",
        location="Seattle, WA",
        salary="100k",
        description=f"description {job_id}",
        skills="Python",
    )


def _analysis(job_id):
    return SimpleNamespace(
        job_id=job_id,
        summary_ko=f"ko-{job_id}",
        analysis_ko="ko-detail",
        summary_en=f"en-{job_id}",
        analysis_en="en-detail",
    )


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def analyze_match(self, resume_text, job_description, lang="ko"):
        self.calls.append((job_description, lang))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)
        finally:
            self.in_flight -= 1
        return {"job_summary": f"{lang}:{job_description}", "detail_analysis": "detail"}


def _setup(monkeypatch, jobs, cached_ids, distances=None):
    if distances is None:
        distances = [0.1 + 0.01 * i for i in range(len(jobs))]
    events_session = RecordingSession([
        Rows(first=SimpleNamespace(
            location="Seattle, WA", description="python engineer", embedding=[0.2, 0.3],
        )),
        Rows(rows=[(job, 1 - distance) for job, distance in zip(jobs, distances)]),
        Rows(rows=[_analysis(job_id) for job_id in cached_ids]),
    ])
    llm = FakeLLM()

    async def rerank(resume_text, job_list, preferred_skills=None):
        return list(range(len(job_list)))

    class Cache:
        def __init__(self):
            self.calls = []
            self.fail_set = False

        async def get(self, key):
            self.calls.append(("get", key))
            return None

        async def setex(self, key, ttl, value):
            self.calls.append(("setex", key, ttl, value))
            if self.fail_set:
                raise TimeoutError("socket timeout")
            return True

    cache = Cache()
    monkeypatch.setattr(main, "rd", cache)
    monkeypatch.setattr(main.ai_service, "rerank_jobs", rerank)
    monkeypatch.setattr(main.ai_service, "analyze_match", llm.analyze_match)
    _use_db(events_session)
    return events_session, llm, cache


def test_vector_query_orders_by_the_distance_operator():
    stmt = main.nearest_postings_stmt(
        [0.1, 0.2, 0.3],
        ["Seattle, WA"],
        ["Junior"],
        ["Full-time"],
        ["Python"],
        limit=100,
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    order_by = sql.upper().split("ORDER BY", 1)[1]
    assert "<=>" in order_by
    assert "1 -" not in order_by
    assert "DESC" not in order_by
    assert "LIMIT" in sql.upper()
    # company != 'USER_UPLOAD' is bound, so the literal is not in the SQL text.
    assert "job_postings.company" in sql
    assert "ILIKE" in sql.upper()


def test_iterative_scan_starts_at_pgvector_0_8():
    assert main.vector_extension_supports_iterative_scan(None) is False
    assert main.vector_extension_supports_iterative_scan("0.7.4") is False
    assert main.vector_extension_supports_iterative_scan("0.8.0") is True
    assert main.vector_extension_supports_iterative_scan("0.8.0-dev") is True
    assert main.vector_extension_supports_iterative_scan("0.11.0") is True


def test_startup_index_sql_is_idempotent_and_matches_the_model():
    sql = " ".join(main.HNSW_INDEX_SQL.split())
    assert sql.startswith("CREATE INDEX IF NOT EXISTS ix_job_postings_embedding_hnsw")
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "m = 16" in sql
    assert "ef_construction = 64" in sql


def test_match_uses_one_analysis_query_and_one_insert(monkeypatch):
    jobs = [_job(1), _job(2), _job(3)]
    session, llm, cache = _setup(monkeypatch, jobs, cached_ids=[1])
    try:
        status, body = asyncio.run(_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    # resume, vector search, one analysis lookup. Not one lookup per job.
    assert session.executes == 3
    assert len(session.added) == 1
    assert sorted(row.job_id for row in session.added[0]) == [2, 3]
    assert sorted(llm.calls) == sorted([
        ("description 2", "ko"), ("description 2", "en"),
        ("description 3", "ko"), ("description 3", "en"),
    ])
    assert [item["title"] for item in body] == ["Job 1", "Job 2", "Job 3"]
    assert body[0]["summary_ko"] == "ko-1"
    assert body[1]["summary_ko"] == "ko:description 2"
    assert list(body[0].keys()) == [
        "title", "company", "location", "salary", "match_score",
        "summary_ko", "analysis_ko", "summary_en", "analysis_en", "skills",
    ]
    # distances were 0.1, 0.11, 0.12 and the selected column is still 1 - distance.
    assert body[0]["match_score"] == 0.9
    assert any(sql.startswith("SET LOCAL hnsw.ef_search") for sql in session.statements)
    assert cache.calls[-1][0] == "setex"


def test_ko_and_en_run_concurrently_under_the_semaphore(monkeypatch):
    jobs = [_job(i) for i in range(1, 4)]
    monkeypatch.setattr(main, "llm_semaphore", asyncio.Semaphore(2))
    _session, llm, _cache = _setup(monkeypatch, jobs, cached_ids=[])
    try:
        status, _body = asyncio.run(_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert len(llm.calls) == 6
    assert llm.max_in_flight == 2


def test_redis_write_failure_still_returns_the_matches(monkeypatch):
    session, _llm, cache = _setup(monkeypatch, [_job(1)], cached_ids=[1])
    cache.fail_set = True
    try:
        status, body = asyncio.run(_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert body[0]["title"] == "Job 1"
    assert cache.calls[-1][0] == "setex"


def test_match_timing_header_is_off_unless_asked(monkeypatch):
    monkeypatch.setattr(main, "MATCH_TIMING", False)
    _setup(monkeypatch, [_job(1)], cached_ids=[1])
    try:
        status, _body, headers = asyncio.run(_get_with_headers("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert not any(name == b"server-timing" for name, _value in headers)

    monkeypatch.setattr(main, "MATCH_TIMING", True)
    _setup(monkeypatch, [_job(1)], cached_ids=[1])
    try:
        status, _body, headers = asyncio.run(_get_with_headers("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    header = dict(headers)[b"server-timing"].decode()
    assert header.startswith("redis;dur=")
    assert "vector;dur=" in header
    assert "rerank;dur=" in header
    assert "db_write;dur=" in header
    # This resume already has its analysis, so the analysis LLM stage is absent.
    assert "analysis;dur=" not in header


def test_query_stats_helpers_are_opt_in():
    from app.database import QUERY_STATS_ENABLED
    if not os.getenv("QUERY_STATS", "").strip():
        assert QUERY_STATS_ENABLED is False
    outside = {"count": 0}
    note_query_start()
    note_query_end()
    with query_stats_scope() as stats:
        note_query_start()
        note_query_end()
        note_query_start()
        note_query_end()
    assert stats["count"] == 2
    assert stats["seconds"] >= 0
    line = format_query_stats("GET", "/match/1", {"count": 4, "seconds": 0.012}, 0.5)
    assert line.startswith("[QUERY_STATS] GET /match/1 statements=4 ")
    assert "db_ms=12.0" in line
    assert "wall_ms=500.0" in line
    assert "db_share=0.024" in line
    assert outside["count"] == 0


async def _get_with_headers(path):
    messages = []
    sent = False
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "root_path": "",
        "state": {},
    }

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], (json.loads(body) if body else None), start.get("headers", [])
