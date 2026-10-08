"""Tests for the async Redis client used by the ``/match`` cache.

The cache used to call a synchronous ``redis.Redis`` client inside the async endpoint.
These tests lock the replacement: one ``redis.asyncio`` client, awaited commands,
timeouts, and a startup/shutdown lifecycle.
"""
import asyncio
import hashlib
import inspect
import json
import os
from types import SimpleNamespace

# Importing the app constructs the OpenAI client. A placeholder is enough:
# these tests never call it.
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
import redis.asyncio

import app.main as main
from app.database import get_db
from app.main import app


def _cache_key(resume_id, levels=None, types=None, skills=None):
    filter_tag = f"{levels}_{types}_{skills}"
    return f"match_results:{resume_id}:{hashlib.md5(filter_tag.encode()).hexdigest()}"


class FakeRedis:
    """In-memory stand-in whose commands are coroutines, like ``redis.asyncio.Redis``."""

    def __init__(self, store=None, fail_get=False):
        self.store = dict(store or {})
        self.fail_get = fail_get
        self.calls = []
        self.closed = False

    async def get(self, key):
        self.calls.append(("get", key))
        if self.fail_get:
            raise TimeoutError("socket timeout")
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.calls.append(("setex", key, ttl, value))
        self.store[key] = value
        return True

    async def ping(self):
        return True

    async def aclose(self):
        self.closed = True


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


class Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        if not self._responses:
            raise AssertionError("database was queried more times than expected")
        return self._responses.pop(0)

    def add(self, obj):
        raise AssertionError("this test does not expect a new match analysis")

    async def commit(self):
        raise AssertionError("this test does not expect a commit")


def _use_db(session):
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override


async def _get(path):
    """Issue one HTTP GET through the ASGI app without running the lifespan."""
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
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, (json.loads(body) if body else None)


def _assert_awaitable(command):
    """redis-py wraps commands, so check the return value rather than the function type."""
    assert inspect.isawaitable(command)
    command.close()


def test_client_is_async_and_has_timeouts():
    client = main.build_redis_client("127.0.0.1", 6399)
    try:
        assert isinstance(client, redis.asyncio.Redis)
        _assert_awaitable(client.get("cache-key"))
        _assert_awaitable(client.setex("cache-key", 3600, "[]"))
        _assert_awaitable(client.ping())
        kwargs = client.connection_pool.connection_kwargs
        assert kwargs["socket_timeout"] == main.REDIS_SOCKET_TIMEOUT == 5.0
        assert kwargs["socket_connect_timeout"] == main.REDIS_SOCKET_CONNECT_TIMEOUT == 5.0
        assert kwargs["socket_keepalive"] is True
        assert kwargs["decode_responses"] is True
        assert kwargs["db"] == 0
    finally:
        asyncio.run(main._close_redis(client))


def test_close_redis_prefers_aclose_and_ignores_none():
    asyncio.run(main._close_redis(None))

    class CloseOnly:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    client = CloseOnly()
    asyncio.run(main._close_redis(client))
    assert client.closed is True


def test_connect_redis_falls_back_and_closes_the_failed_client(monkeypatch):
    monkeypatch.setattr(main, "REDIS_HOST", "primary")
    monkeypatch.setattr(main, "REDIS_PORT", 6380)
    created = []

    def factory(host, port):
        client = FakeRedis()
        client.host = host
        client.port = port
        if host == "primary":
            async def fail_ping():
                raise ConnectionError("primary down")

            client.ping = fail_ping
        created.append(client)
        return client

    monkeypatch.setattr(main, "build_redis_client", factory)
    client = asyncio.run(main.connect_redis())
    assert [c.host for c in created] == ["primary", "redis"]
    assert created[0].closed is True
    assert client is created[1]
    assert client.closed is False
    asyncio.run(main._close_redis(client))


def test_connect_redis_returns_none_when_both_attempts_fail(monkeypatch):
    monkeypatch.setattr(main, "REDIS_HOST", "redis")
    monkeypatch.setattr(main, "REDIS_PORT", 6379)
    created = []

    def factory(host, port):
        client = FakeRedis()

        async def fail_ping():
            raise ConnectionError("down")

        client.ping = fail_ping
        created.append(client)
        return client

    monkeypatch.setattr(main, "build_redis_client", factory)
    assert asyncio.run(main.connect_redis()) is None
    # The fallback still runs when the configured host is already the Docker service name.
    assert len(created) == 2
    assert all(client.closed for client in created)


def test_lifespan_opens_one_client_and_closes_it(monkeypatch):
    client = FakeRedis()
    connects = []

    async def connect():
        connects.append(1)
        return client

    class Begin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *args, **kwargs):
            return None

        async def run_sync(self, fn):
            return None

    class Scheduler:
        instance = None

        def __init__(self):
            Scheduler.instance = self
            self.stopped = False

        def add_job(self, *args, **kwargs):
            return None

        def start(self):
            return None

        def shutdown(self):
            self.stopped = True

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(main, "connect_redis", connect)
    monkeypatch.setattr(main, "engine", Engine())
    monkeypatch.setattr(main, "AsyncIOScheduler", Scheduler)

    async def run():
        async with main.lifespan(app):
            assert main.rd is client
            assert connects == [1]
        assert main.rd is None
        assert client.closed is True
        assert Scheduler.instance.stopped is True

    asyncio.run(run())


def test_lifespan_closes_redis_when_database_startup_fails(monkeypatch):
    client = FakeRedis()

    async def connect():
        return client

    class Begin:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(main, "connect_redis", connect)
    monkeypatch.setattr(main, "engine", Engine())

    async def run():
        with pytest.raises(RuntimeError, match="db down"):
            async with main.lifespan(app):
                pass
        assert main.rd is None
        assert client.closed is True

    asyncio.run(run())


def test_match_cache_hit_awaits_get_and_skips_the_database(monkeypatch):
    payload = [{"title": "Cached role", "company": "Acme"}]
    key = _cache_key(4)
    cache = FakeRedis({key: json.dumps(payload)})
    session = Session([])
    monkeypatch.setattr(main, "rd", cache)
    _use_db(session)
    try:
        status, body = asyncio.run(_get("/match/4"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert body == payload
    assert cache.calls == [("get", key)]
    assert session.calls == 0


def test_match_reuses_the_same_client_across_requests(monkeypatch):
    key = _cache_key(4)
    cache = FakeRedis({key: json.dumps([{"title": "Cached role"}])})
    monkeypatch.setattr(main, "rd", cache)
    _use_db(Session([]))
    try:
        first, _ = asyncio.run(_get("/match/4"))
        second, _ = asyncio.run(_get("/match/4"))
    finally:
        app.dependency_overrides.clear()
    assert first == second == 200
    assert cache.calls == [("get", key), ("get", key)]


def test_match_read_error_falls_through_to_the_database(monkeypatch):
    cache = FakeRedis(fail_get=True)
    session = Session([Rows(first=None)])
    monkeypatch.setattr(main, "rd", cache)
    _use_db(session)
    try:
        status, body = asyncio.run(_get("/match/8"))
    finally:
        app.dependency_overrides.clear()
    assert status == 404
    assert body["detail"] == "Resume not found"
    assert cache.calls[0][0] == "get"
    assert not any(call[0] == "setex" for call in cache.calls)
    assert session.calls == 1


def test_match_skips_cache_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "rd", None)
    session = Session([Rows(first=None)])
    _use_db(session)
    try:
        status, body = asyncio.run(_get("/match/8"))
    finally:
        app.dependency_overrides.clear()
    assert status == 404
    assert body["detail"] == "Resume not found"
    assert session.calls == 1


def test_match_cache_miss_awaits_setex_for_one_hour(monkeypatch):
    resume = SimpleNamespace(location="Seattle, WA", description="python engineer", embedding=[0.1, 0.2])
    job = SimpleNamespace(
        id=7,
        title="Backend Engineer",
        company="Acme",
        location="Seattle, WA",
        salary="100k",
        description="build apis",
        skills="Python",
    )
    analysis = SimpleNamespace(
        summary_ko="요약",
        analysis_ko="분석",
        summary_en="summary",
        analysis_en="analysis",
    )
    session = Session([
        Rows(first=resume),
        Rows(rows=[(job, 0.91234)]),
        Rows(first=analysis),
    ])

    async def rerank(resume_text, jobs, preferred_skills=None):
        assert resume_text == "python engineer"
        assert jobs == [job]
        return [0]

    cache = FakeRedis()
    monkeypatch.setattr(main, "rd", cache)
    monkeypatch.setattr(main.ai_service, "rerank_jobs", rerank)
    _use_db(session)
    try:
        status, body = asyncio.run(_get("/match/15"))
    finally:
        app.dependency_overrides.clear()

    assert status == 200
    assert body[0]["title"] == "Backend Engineer"
    assert body[0]["match_score"] == 0.9123
    assert body[0]["summary_ko"] == "요약"
    key = _cache_key(15)
    assert cache.calls[0] == ("get", key)
    assert cache.calls[1][0] == "setex"
    assert cache.calls[1][1] == key
    assert cache.calls[1][2] == 3600
    assert json.loads(cache.calls[1][3]) == body


def test_match_does_not_cache_an_empty_candidate_list(monkeypatch):
    resume = SimpleNamespace(location="Seattle, WA", description="python", embedding=[0.1])
    session = Session([
        Rows(first=resume),
        Rows(rows=[]),
    ])
    cache = FakeRedis()
    monkeypatch.setattr(main, "rd", cache)
    _use_db(session)
    try:
        status, body = asyncio.run(_get("/match/15"))
    finally:
        app.dependency_overrides.clear()
    assert status == 200
    assert body == []
    assert cache.calls == [("get", _cache_key(15))]
