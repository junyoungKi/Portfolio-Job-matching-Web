"""Tests for the async hardening of ``/match`` and ``/process-resume``.

They use in-memory fakes for the database, Redis and the LLM, so no Postgres, Redis or OpenAI
key is needed. They lock: batched analysis lookup, bounded concurrent LLM calls, connection
release before slow calls, a Redis write failure not becoming a 500, the upload size limit, and
the explicit pool / OpenAI client settings.
"""
import asyncio
import importlib
import json
import os
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import httpx
import pytest

import app.main as main
from app.database import get_db
from app.main import app


class Rows:
    def __init__(self, first=None, rows=None):
        self._first = first
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class RecordingSession:
    """Scripted AsyncSession stand-in that records ordering relative to the LLM calls."""

    def __init__(self, responses, events):
        self._responses = list(responses)
        self.events = events
        self.executes = 0
        self.commits = 0
        self.rollbacks = 0
        self.added = []

    async def execute(self, stmt):
        self.executes += 1
        self.events.append("execute")
        if not self._responses:
            raise AssertionError("database was queried more times than expected")
        return self._responses.pop(0)

    def add(self, obj):
        raise AssertionError("expected add_all, not one add per row")

    def add_all(self, objs):
        self.added.append(list(objs))
        self.events.append("add_all")

    async def commit(self):
        self.commits += 1
        self.events.append("commit")

    async def rollback(self):
        self.rollbacks += 1
        self.events.append("rollback")

    async def refresh(self, obj):
        obj.id = 99


class FakeRedis:
    def __init__(self, fail_set=False):
        self.fail_set = fail_set
        self.calls = []

    async def get(self, key):
        self.calls.append(("get", key))
        return None

    async def setex(self, key, ttl, value):
        self.calls.append(("setex", key, ttl, value))
        if self.fail_set:
            raise TimeoutError("socket timeout")
        return True


def _job(job_id):
    return SimpleNamespace(
        id=job_id,
        title=f"Job {job_id}",
        company=f"Co {job_id}",
        location="Seattle, WA",
        salary="100k",
        description=f"description {job_id}",
        skills="Python",
    )


def _resume():
    return SimpleNamespace(location="Seattle, WA", description="python engineer", embedding=[0.1, 0.2])


def _analysis(job_id):
    return SimpleNamespace(
        job_id=job_id,
        summary_ko=f"ko-sum-{job_id}",
        analysis_ko=f"ko-det-{job_id}",
        summary_en=f"en-sum-{job_id}",
        analysis_en=f"en-det-{job_id}",
    )


def _use_db(session):
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override


async def _asgi_get(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(path)
    return response.status_code, response.json()


class FakeLLM:
    """Replacement for ``ai_service.analyze_match`` that tracks in-flight calls."""

    def __init__(self, events, delay=0.02):
        self.events = events
        self.delay = delay
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = []

    async def analyze_match(self, resume_text, job_description, lang="ko"):
        self.calls.append((job_description, lang))
        self.events.append(f"llm-start-{lang}")
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.in_flight -= 1
        self.events.append(f"llm-end-{lang}")
        return {"job_summary": f"{lang}:{job_description}:summary", "detail_analysis": f"{lang}:{job_description}:detail"}


def _setup_match(monkeypatch, jobs, cached_ids, cache, llm_limit=8, delay=0.02):
    events = []
    candidates = [(job, 0.9 - 0.01 * i) for i, job in enumerate(jobs)]
    session = RecordingSession(
        [
            Rows(first=_resume()),
            Rows(rows=candidates),
            Rows(rows=[_analysis(i) for i in cached_ids]),
        ],
        events,
    )
    llm = FakeLLM(events, delay=delay)

    async def rerank(resume_text, job_list, preferred_skills=None):
        events.append("rerank")
        return list(range(len(job_list)))

    monkeypatch.setattr(main, "rd", cache)
    monkeypatch.setattr(main.ai_service, "rerank_jobs", rerank)
    monkeypatch.setattr(main.ai_service, "analyze_match", llm.analyze_match)
    monkeypatch.setattr(main, "llm_semaphore", asyncio.Semaphore(llm_limit))
    _use_db(session)
    return session, llm, events


def test_match_uses_one_analysis_query_and_one_batched_commit(monkeypatch):
    jobs = [_job(i) for i in range(1, 6)]
    cache = FakeRedis()
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[1, 2, 3], cache=cache)
    try:
        status, body = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()

    assert status == 200
    # resume + candidates + ONE query for the analyses of all five jobs (was one per job).
    assert session.executes == 3
    assert len(session.added) == 1
    assert sorted(row.job_id for row in session.added[0]) == [4, 5]
    # Only the two uncached jobs hit the LLM, once per language each.
    assert sorted(llm.calls) == sorted(
        [("description 4", "ko"), ("description 4", "en"), ("description 5", "ko"), ("description 5", "en")]
    )
    assert [item["title"] for item in body] == [f"Job {i}" for i in range(1, 6)]
    assert body[0]["summary_ko"] == "ko-sum-1" and body[0]["analysis_en"] == "en-det-1"
    assert body[3]["summary_ko"] == "ko:description 4:summary"
    assert body[3]["analysis_en"] == "en:description 4:detail"
    assert cache.calls[-1][0] == "setex" and json.loads(cache.calls[-1][3]) == body


def test_match_response_keys_are_unchanged(monkeypatch):
    jobs = [_job(1)]
    session, _, _ = _setup_match(monkeypatch, jobs, cached_ids=[1], cache=FakeRedis())
    try:
        status, body = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert list(body[0].keys()) == [
        "title", "company", "location", "salary", "match_score",
        "summary_ko", "analysis_ko", "summary_en", "analysis_en", "skills",
    ]
    assert body[0]["match_score"] == 0.9


def test_match_runs_llm_calls_concurrently_and_ko_en_overlap(monkeypatch):
    jobs = [_job(i) for i in range(1, 6)]
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[], cache=FakeRedis(), llm_limit=20)
    try:
        status, _ = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert len(llm.calls) == 10
    assert llm.max_in_flight == 10
    # The first ko call has not finished before an en call has started.
    first_end = events.index("llm-end-ko")
    assert "llm-start-en" in events[:first_end]


def test_match_llm_concurrency_is_bounded_by_the_semaphore(monkeypatch):
    jobs = [_job(i) for i in range(1, 6)]
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[], cache=FakeRedis(), llm_limit=3)
    try:
        status, _ = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert len(llm.calls) == 10
    assert llm.max_in_flight == 3


def test_match_releases_the_connection_before_each_slow_external_call(monkeypatch):
    jobs = [_job(i) for i in range(1, 4)]
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[], cache=FakeRedis())
    try:
        status, _ = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert events.index("commit") < events.index("rerank")
    first_llm = events.index("llm-start-ko")
    assert events[:first_llm].count("commit") == 2
    # The single write happens after every LLM call has finished.
    last_llm = max(i for i, e in enumerate(events) if e.startswith("llm-end"))
    assert events.index("add_all") > last_llm
    assert events.count("add_all") == 1
    assert events[-1] == "commit"


def test_match_with_all_analyses_cached_makes_no_llm_calls(monkeypatch):
    jobs = [_job(i) for i in range(1, 4)]
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[1, 2, 3], cache=FakeRedis())
    try:
        status, body = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert llm.calls == []
    assert session.added == []
    assert len(body) == 3


def test_match_survives_a_redis_write_failure(monkeypatch):
    jobs = [_job(1), _job(2)]
    cache = FakeRedis(fail_set=True)
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[1, 2], cache=cache)
    try:
        status, body = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert len(body) == 2
    assert any(call[0] == "setex" for call in cache.calls)


def test_match_repeated_job_index_from_the_llm_is_analysed_once(monkeypatch):
    jobs = [_job(1), _job(2)]
    session, llm, events = _setup_match(monkeypatch, jobs, cached_ids=[], cache=FakeRedis())

    async def rerank(resume_text, job_list, preferred_skills=None):
        return [1, 1, 0]

    monkeypatch.setattr(main.ai_service, "rerank_jobs", rerank)
    try:
        status, body = asyncio.run(_asgi_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert [item["title"] for item in body] == ["Job 2", "Job 2", "Job 1"]
    assert len(llm.calls) == 4
    assert sorted(row.job_id for row in session.added[0]) == [1, 2]


class UploadSession:
    def __init__(self, events):
        self.events = events

    async def execute(self, stmt):
        self.events.append("execute")
        return Rows(first=None)

    def add(self, obj):
        self.events.append("add")

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")

    async def refresh(self, obj):
        obj.id = 42


async def _post_resume(data: bytes, filename="resume.pdf"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/process-resume",
            params={"location": "Seattle, WA"},
            files={"file": (filename, data, "application/pdf")},
        )
    return response.status_code, response.json()


@pytest.fixture
def upload_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    events = []

    async def extract_text(path):
        events.append("parse")
        assert os.path.exists(path)
        return "parsed resume text"

    async def get_embedding(text):
        events.append("embed")
        return [0.0] * 4

    monkeypatch.setattr(main.resume_parser, "extract_text", extract_text)
    monkeypatch.setattr(main.ai_service, "get_embedding", get_embedding)
    _use_db(UploadSession(events))
    yield tmp_path, events
    app.dependency_overrides.clear()


def test_process_resume_releases_the_connection_before_embedding(upload_env):
    tmp_path, events = upload_env
    status, body = asyncio.run(_post_resume(b"%PDF-1.4 small"))
    assert status == 200
    assert body["id"] == 42
    assert events.index("rollback") < events.index("embed")
    assert events[-1] == "commit"
    assert os.listdir(tmp_path / "temp_uploads") == []


def test_process_resume_rejects_an_oversize_upload_and_leaves_no_file(monkeypatch, upload_env):
    tmp_path, events = upload_env
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 16)
    status, body = asyncio.run(_post_resume(b"x" * 17))
    assert status == 413
    assert "too large" in body["detail"].lower()
    assert "parse" not in events and "embed" not in events
    upload_dir = tmp_path / "temp_uploads"
    assert not upload_dir.exists() or os.listdir(upload_dir) == []


def test_process_resume_accepts_an_upload_exactly_at_the_limit(monkeypatch, upload_env):
    tmp_path, events = upload_env
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 16)
    status, _ = asyncio.run(_post_resume(b"x" * 16))
    assert status == 200


def test_engine_pool_defaults_match_sqlalchemy_and_are_explicit():
    from app import database

    assert database.DB_POOL_SIZE == 5
    assert database.DB_MAX_OVERFLOW == 10
    assert database.DB_POOL_TIMEOUT == 30
    assert database.engine.pool.size() == database.DB_POOL_SIZE
    assert database.engine.pool._max_overflow == database.DB_MAX_OVERFLOW
    assert database.engine.pool._timeout == database.DB_POOL_TIMEOUT


def test_pool_and_openai_settings_are_env_configurable(monkeypatch):
    from app import database
    from app.services import ai

    monkeypatch.setenv("DB_POOL_SIZE", "17")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "7")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    try:
        importlib.reload(database)
        importlib.reload(ai)
        assert database.engine.pool.size() == 17
        assert database.engine.pool._max_overflow == 3
        assert database.engine.pool._timeout == 7
        assert ai.client.timeout == 12.5
        assert ai.client.max_retries == 0
    finally:
        monkeypatch.undo()
        importlib.reload(database)
        importlib.reload(ai)
    assert ai.client.timeout == 30.0
    assert ai.client.max_retries == 2


def test_invalid_env_values_fall_back_to_defaults(monkeypatch):
    from app import database

    monkeypatch.setenv("DB_POOL_SIZE", "not-a-number")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "-4")
    assert database._env_int("DB_POOL_SIZE", 5) == 5
    assert database._env_int("DB_MAX_OVERFLOW", 10) == 10
    assert database._env_int("DB_UNSET_FOR_TEST", 9) == 9


def test_ai_service_has_no_bare_except():
    import inspect
    import re

    from app.services import ai, collector

    for module in (ai, collector):
        source = inspect.getsource(module)
        assert not re.search(r"except\s*:", source), module.__name__


def test_cancellation_is_not_swallowed_by_ai_service(monkeypatch):
    from app.services import ai

    class Completions:
        async def create(self, **kwargs):
            raise asyncio.CancelledError()

    class Chat:
        completions = Completions()

    monkeypatch.setattr(ai, "client", SimpleNamespace(chat=Chat()))

    async def run():
        await ai.ai_service.analyze_match("r", "j")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
