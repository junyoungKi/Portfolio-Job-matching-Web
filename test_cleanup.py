"""Retention filters for crawled postings and uploaded resumes.

Crawled postings expire after 30 days. ``USER_UPLOAD`` rows are personal data and expire
after one hour, together with their ``MatchAnalysis`` rows. These tests lock that split
without a database.
"""
import asyncio
import os
from datetime import datetime, timedelta

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from sqlalchemy.dialects import postgresql

import app.main as main
from app.main import app


def _literal_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_cleanup_filters_split_crawled_postings_and_user_resumes():
    now = datetime(2026, 10, 9, 15, 0, 0)
    crawled_sql = _literal_sql(main.crawled_posting_delete_stmt(now))
    analyses_stmt, resumes_stmt = main.expired_user_resume_delete_stmts(now)
    analysis_sql = _literal_sql(analyses_stmt)
    resume_sql = _literal_sql(resumes_stmt)

    crawled_cutoff = "2026-09-09 15:00:00"
    resume_cutoff = "2026-10-09 14:00:00"

    assert "job_postings" in crawled_sql
    assert "company !=" in crawled_sql or "company <>" in crawled_sql
    assert "USER_UPLOAD" in crawled_sql
    assert crawled_cutoff in crawled_sql
    assert resume_cutoff not in crawled_sql
    assert "company = 'USER_UPLOAD'" not in crawled_sql

    assert "job_postings" in resume_sql
    assert "company = 'USER_UPLOAD'" in resume_sql
    assert resume_cutoff in resume_sql
    assert crawled_cutoff not in resume_sql
    assert "company !=" not in resume_sql and "company <>" not in resume_sql

    assert "match_analyses" in analysis_sql
    assert "resume_id IN" in analysis_sql
    assert "company = 'USER_UPLOAD'" in analysis_sql
    assert resume_cutoff in analysis_sql
    assert crawled_cutoff not in analysis_sql

    assert main.CRAWLED_POSTING_RETENTION == timedelta(days=30)
    assert main.USER_RESUME_RETENTION == timedelta(hours=1)
    assert main.USER_RESUME_CLEANUP_MINUTES < 24 * 60


def test_resume_cleanup_deletes_analyses_before_resumes(monkeypatch):
    session = _RecordingSession()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(main, "datetime", _fixed_datetime(datetime(2026, 10, 9, 15, 0, 0)))

    asyncio.run(main.cleanup_expired_resumes())

    assert session.committed is True
    assert session.rolled_back is False
    assert len(session.statements) == 2
    analysis_sql = _literal_sql(session.statements[0])
    resume_sql = _literal_sql(session.statements[1])
    assert analysis_sql.startswith("DELETE FROM match_analyses")
    assert "resume_id IN" in analysis_sql
    assert resume_sql.startswith("DELETE FROM job_postings")
    assert "company = 'USER_UPLOAD'" in resume_sql
    assert "2026-10-09 14:00:00" in resume_sql


def test_crawled_cleanup_keeps_the_30_day_filter(monkeypatch):
    session = _RecordingSession()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(main, "datetime", _fixed_datetime(datetime(2026, 10, 9, 15, 0, 0)))

    asyncio.run(main.cleanup_old_jobs())

    assert session.committed is True
    assert len(session.statements) == 1
    sql = _literal_sql(session.statements[0])
    assert sql.startswith("DELETE FROM job_postings")
    assert "company !=" in sql or "company <>" in sql
    assert "USER_UPLOAD" in sql
    assert "2026-09-09 15:00:00" in sql
    assert "company = 'USER_UPLOAD'" not in sql


def test_resume_cleanup_is_scheduled_on_a_short_interval(monkeypatch):
    jobs = []

    class Scheduler:
        def add_job(self, func, trigger, **kwargs):
            jobs.append((func.__name__, trigger, kwargs))

        def start(self):
            return None

        def shutdown(self):
            return None

    class Begin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *args, **kwargs):
            return None

        async def run_sync(self, fn):
            return None

    class Engine:
        def begin(self):
            return Begin()

    class Client:
        async def aclose(self):
            return None

    async def connect():
        return Client()

    monkeypatch.setattr(main, "connect_redis", connect)
    monkeypatch.setattr(main, "engine", Engine())
    monkeypatch.setattr(main, "AsyncIOScheduler", Scheduler)

    async def run():
        async with main.lifespan(app):
            pass

    asyncio.run(run())

    by_name = {name: (trigger, kwargs) for name, trigger, kwargs in jobs}
    assert by_name["cleanup_old_jobs"] == ("cron", {"hour": 0, "minute": 0})
    trigger, kwargs = by_name["cleanup_expired_resumes"]
    assert trigger == "interval"
    assert kwargs["minutes"] == main.USER_RESUME_CLEANUP_MINUTES
    assert kwargs["minutes"] <= 60


class _RecordingSession:
    def __init__(self):
        self.statements = []
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return type("Result", (), {"rowcount": 0})()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _fixed_datetime(moment: datetime):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    return Fixed
