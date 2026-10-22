"""Crawl deadlines, per-commit sessions, and a driver crash.

No database, no network, and no API key. Slow work is a local sleep or a fake browser.
"""
import asyncio
import os
import socket

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InterfaceError

import app.database as database
import app.main as main
from app.services import collector


def _closed(statement):
    return InterfaceError(statement, {}, Exception("connection is closed"), connection_invalidated=True)


def _job(title="Role", company="Acme", location="Seattle, WA"):
    return {
        "title": title,
        "company": company,
        "description": "build things",
        "location": location,
        "salary": "100k",
    }


class _Scalars:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return _Scalars(self._row)

    def all(self):
        # A truthy ``exists`` stands for a legacy row: Role @ Acme in Austin, TX, no job id.
        if not self._row:
            return []
        return [("role", "acme", "austin, tx", None)]


class Session:
    open_count = 0
    made = []

    def __init__(self, exists=None, fail_commit=False, fail_rollback=False):
        self.exists = exists
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback
        self.commits = 0
        self.rollbacks = 0
        self.exited = False
        self.stmt = None
        Session.made.append(self)

    async def __aenter__(self):
        Session.open_count += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        Session.open_count -= 1
        self.exited = True
        return False

    async def execute(self, stmt):
        self.stmt = stmt
        return _Result(self.exists)

    def add(self, row):
        self.added = row

    def add_all(self, rows):
        self.added = list(rows)

    async def commit(self):
        if self.fail_commit:
            self.fail_commit = False
            raise _closed("COMMIT")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise _closed("ROLLBACK")


def _install_sessions(monkeypatch, plan):
    Session.open_count = 0
    Session.made = []
    remaining = list(plan)

    def factory():
        kwargs = remaining.pop(0)
        return Session(**kwargs)

    monkeypatch.setattr(main, "AsyncSessionLocal", factory)


def _install_ai(monkeypatch, embedding_seen):
    async def meta(_description):
        embedding_seen["during_meta"] = Session.open_count
        return {"employment_type": "Full-time", "experience_level": "Junior", "skills": ["Python"]}

    async def embed(_description):
        embedding_seen["during_embed"] = Session.open_count
        embedding_seen["calls"] = embedding_seen.get("calls", 0) + 1
        return [0.1, 0.2]

    monkeypatch.setattr(main.ai_service, "extract_job_metadata", meta)
    monkeypatch.setattr(main.ai_service, "get_embedding", embed)


def _run_crawl(monkeypatch, scrape, hubs, city_timeout, job_timeout):
    monkeypatch.setattr(main.job_collector, "NA_HUBS", hubs)
    monkeypatch.setattr(main.job_collector, "scrape_linkedin", scrape)
    monkeypatch.setattr(main, "CRAWL_CITY_TIMEOUT_SECONDS", city_timeout)
    monkeypatch.setattr(main, "CRAWL_JOB_TIMEOUT_SECONDS", job_timeout)

    async def bounded():
        await asyncio.wait_for(main.scheduled_north_america_crawl(), timeout=3)

    asyncio.run(bounded())


def test_city_timeout_continues_and_names_the_step(monkeypatch, capsys):
    calls = []

    async def scrape(keyword, city, on_step=None, max_pages=1):
        calls.append(city)
        if on_step:
            on_step("Chromium launch")
        if city == "Slow":
            await asyncio.sleep(30)
        return [_job(location=city)]

    _install_sessions(monkeypatch, [{}, {}])
    seen = {}
    _install_ai(monkeypatch, seen)
    _run_crawl(monkeypatch, scrape, ["Slow", "Fast"], city_timeout=0.2, job_timeout=5)

    out = capsys.readouterr().out
    assert calls == ["Slow", "Fast"]
    assert "Watchdog: Slow (Software Engineer) exceeded 0.2s; last step was Chromium launch" in out
    assert "Continuing with the next city" in out
    assert "[BATCH] Fast: Collected 1 cards, saved 1, skipped 0 (duplicate), failed 0," in out
    assert "[BATCH] Finished total saved 1, skipped 0, failed 0," in out
    assert seen["during_embed"] == 0


def test_overall_deadline_ends_the_run(monkeypatch, capsys):
    calls = []

    async def scrape(keyword, city, on_step=None, max_pages=1):
        calls.append(city)
        if on_step:
            on_step("OpenAI embedding Role")
        await asyncio.sleep(30)
        return []

    _run_crawl(monkeypatch, scrape, ["Slow", "Also Slow"], city_timeout=30, job_timeout=0.3)

    out = capsys.readouterr().out
    assert calls == ["Slow"]
    assert "Watchdog: run exceeded 0.3s; last step was Slow (Software Engineer): OpenAI embedding Role" in out
    assert "Ending this crawl so the next run can start" in out
    assert "[BATCH] Finished total saved 0, skipped 0, failed 0," in out


def test_commit_retries_once_when_the_connection_is_closed(monkeypatch, capsys):
    _install_sessions(monkeypatch, [
        {},
        {"fail_commit": True, "fail_rollback": True},
        {},
    ])
    seen = {}
    _install_ai(monkeypatch, seen)
    stats = main._CrawlCounts()
    progress = main._CrawlProgress()
    progress.city = "Seattle, WA"
    progress.keyword = "Software Engineer"

    asyncio.run(main._persist_one_posting(_job(), "Software Engineer", stats, progress))

    out = capsys.readouterr().out
    assert stats.saved == 1
    assert stats.failed == 0
    assert "retrying once" in out
    assert "Rollback on a closed connection was ignored" in out
    assert "Saved to DB: Role @ Acme" in out
    assert seen["during_embed"] == 0
    assert seen["during_meta"] == 0
    assert all(session.exited for session in Session.made)
    assert len(Session.made) == 3


def test_second_commit_failure_does_not_stop_the_next_card(monkeypatch, capsys):
    _install_sessions(monkeypatch, [
        {},
        {"fail_commit": True, "fail_rollback": True},
        {"fail_commit": True, "fail_rollback": True},
        {},
        {},
    ])
    _install_ai(monkeypatch, {})
    stats = main._CrawlCounts()
    progress = main._CrawlProgress()

    async def both():
        await main._persist_one_posting(_job("First"), "Software Engineer", stats, progress)
        await main._persist_one_posting(_job("Second"), "Software Engineer", stats, progress)

    asyncio.run(both())

    out = capsys.readouterr().out
    assert stats.saved == 1
    assert stats.failed == 1
    assert "Failed to process an individual posting" in out
    assert "Saved to DB: Second @ Acme" in out


def test_legacy_fallback_matches_title_company_and_location(monkeypatch):
    _install_sessions(monkeypatch, [{"exists": object()}])
    seen = {}
    _install_ai(monkeypatch, seen)
    stats = main._CrawlCounts()

    asyncio.run(main._persist_one_posting(
        _job(location="Austin, TX"), "Software Engineer", stats, main._CrawlProgress()
    ))

    assert stats.skipped == 1
    assert stats.saved == 0
    assert "calls" not in seen
    where = str(Session.made[0].stmt.compile(dialect=postgresql.dialect())).upper().split("WHERE", 1)[1]
    assert "TITLE" in where
    assert "COMPANY" in where
    assert "LOCATION" in where


def test_engine_pings_and_recycles_connections():
    kwargs = database.async_engine_kwargs()
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == database.DB_POOL_RECYCLE_SECONDS == 1800
    assert kwargs["connect_args"]["command_timeout"] == database.DB_COMMAND_TIMEOUT_SECONDS
    assert database.engine.pool._pre_ping is True
    assert database.engine.pool._recycle == database.DB_POOL_RECYCLE_SECONDS


def test_faulthandler_is_enabled_for_all_threads():
    import faulthandler
    assert faulthandler.is_enabled()


def test_tcp_keepalive_hook_can_be_disabled(monkeypatch):
    options = []

    class Sock:
        def setsockopt(self, level, opt, value):
            options.append((level, opt, value))

    class Transport:
        def get_extra_info(self, name):
            return Sock() if name == "socket" else None

    class Raw:
        _transport = Transport()

    class Conn:
        _connection = Raw()

    monkeypatch.setenv("DB_TCP_KEEPALIVE", "0")
    database._enable_tcp_keepalive(Conn(), None)
    assert options == []
    assert database.tcp_keepalive_enabled() is False

    monkeypatch.setenv("DB_TCP_KEEPALIVE", "1")
    database._enable_tcp_keepalive(Conn(), None)
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options


def test_tcp_keepalive_is_set_on_the_asyncpg_socket():
    options = []

    class Sock:
        def setsockopt(self, level, opt, value):
            options.append((level, opt, value))

    class Transport:
        def get_extra_info(self, name):
            return Sock() if name == "socket" else None

    class Raw:
        _transport = Transport()

    class Conn:
        _connection = Raw()

    database.enable_tcp_keepalive(Conn())
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, database.DB_TCP_KEEPIDLE_SECONDS) in options


class _Page:
    def __init__(self, events, crash):
        self.events = events
        self.crash = crash

    async def goto(self, *args, **kwargs):
        self.events.append("goto")
        if self.crash:
            raise RuntimeError("write EPIPE")

    async def wait_for_selector(self, *args, **kwargs):
        raise RuntimeError("no cards")

    async def close(self):
        self.events.append("page.close")
        await asyncio.sleep(30)


class _Context:
    def __init__(self, events, crash):
        self.events = events
        self.crash = crash

    def set_default_timeout(self, _ms):
        return None

    def set_default_navigation_timeout(self, _ms):
        return None

    async def new_page(self):
        return _Page(self.events, self.crash)

    async def close(self):
        self.events.append("context.close")


class _Browser:
    def __init__(self, events, crash):
        self.events = events
        self.crash = crash

    async def new_context(self, **kwargs):
        return _Context(self.events, self.crash)

    async def close(self):
        self.events.append("browser.close")


class _Playwright:
    def __init__(self, events, crash):
        self.events = events
        self.crash = crash
        self.chromium = self

    async def launch(self, **kwargs):
        self.events.append("launch")
        return _Browser(self.events, self.crash)

    async def stop(self):
        self.events.append("playwright.stop")


def _patch_browser(monkeypatch, events, crash):
    class Manager:
        def start(self):
            async def _start():
                return _Playwright(events, crash)
            return _start()

    monkeypatch.setattr(collector, "async_playwright", lambda: Manager())
    monkeypatch.setattr(collector, "CLOSE_TIMEOUT_SECONDS", 0.2)


def test_driver_epipe_closes_the_browser_and_ends_the_city(monkeypatch, capsys):
    events = []
    _patch_browser(monkeypatch, events, crash=True)

    async def scrape():
        await collector.job_collector.scrape_linkedin("Software Engineer", "Seattle, WA", on_step=lambda step: events.append(step))

    with pytest.raises(RuntimeError, match="EPIPE"):
        asyncio.run(scrape())

    out = capsys.readouterr().out
    assert "Playwright driver crashed for Seattle, WA: write EPIPE" in out
    assert events.index("Chromium launch") < events.index("launch")
    assert "page.close" in events
    assert "browser.close" in events
    assert "playwright.stop" in events

    calls = []

    async def city_scrape(keyword, city, on_step=None, max_pages=1):
        calls.append(city)
        if city == "Seattle, WA":
            raise RuntimeError("write EPIPE")
        return [_job()]

    _install_sessions(monkeypatch, [{}, {}])
    _install_ai(monkeypatch, {})
    _run_crawl(
        monkeypatch,
        city_scrape,
        ["Seattle, WA", "Austin, TX"],
        city_timeout=5,
        job_timeout=5,
    )
    out = capsys.readouterr().out
    assert calls == ["Seattle, WA", "Austin, TX"]
    assert "City failed: Seattle, WA (Software Engineer): write EPIPE" in out
    assert "saved 1" in out


def test_browser_close_cannot_hang_the_scrape(monkeypatch, capsys):
    events = []
    _patch_browser(monkeypatch, events, crash=False)

    async def scrape():
        return await collector.job_collector.scrape_linkedin("Software Engineer", "Seattle, WA")

    jobs = asyncio.run(asyncio.wait_for(scrape(), timeout=2))
    out = capsys.readouterr().out
    assert jobs == []
    assert "Playwright close timed out after 0.2s" in out
    assert "browser.close" in events
    assert "playwright.stop" in events
