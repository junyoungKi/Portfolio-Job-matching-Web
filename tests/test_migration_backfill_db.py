"""Author: Joonyoung Ki

Purpose: Integration tests for the idempotent salary migration and the
backfill script against a real PostgreSQL database.

Skipped unless ``TEST_DATABASE_URL`` (``postgresql+asyncpg://...``) points to
a database whose name contains "test". The tests DROP and recreate the
``job_postings`` table, so never point them at real data.
"""

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB or "test" not in TEST_DB.rsplit("/", 1)[-1],
    reason="Set TEST_DATABASE_URL to a scratch database whose name contains 'test'",
)


async def _scenario():
    """Create a legacy table, migrate twice, backfill twice and verify."""
    from app.services.migrations import run_salary_migration
    from scripts import backfill_salary

    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS job_postings"))
        await conn.execute(text(
            "CREATE TABLE job_postings (id SERIAL PRIMARY KEY, title VARCHAR, company VARCHAR, "
            "description TEXT, salary VARCHAR)"
        ))
        await conn.execute(text(
            "INSERT INTO job_postings (title, company, description, salary) VALUES "
            "('a','c','d','$120,000 - $150,000 a year'),"
            "('b','c','Pay range: $45 - $60 per hour.','Competitive Salary'),"
            "('r','USER_UPLOAD','resume','$1 - $2 a year')"
        ))

    first = await run_salary_migration(engine)
    second = await run_salary_migration(engine)
    assert len(first) == 7 and second == []

    backfill_salary.engine = engine
    ns = type("Args", (), {"dry_run": False, "from_description": True, "force": False, "batch_size": 1, "limit": 0})()
    stats = await backfill_salary.run(ns)
    stats_again = await backfill_salary.run(ns)

    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT title, salary, salary_min, salary_max, salary_currency, salary_period, "
            "salary_annual_max, salary_source FROM job_postings ORDER BY id"
        ))).all()
        await conn.execute(text("DROP TABLE job_postings"))
        await conn.commit()
    await engine.dispose()
    return stats, stats_again, rows


def test_migration_and_backfill_are_idempotent():
    """Migration adds 7 columns once; backfill fills rows and keeps salary text."""
    stats, stats_again, rows = asyncio.run(_scenario())
    assert stats["parsed"] == 2 and stats["updated"] == 2
    assert stats_again["updated"] == 0
    assert rows[0][1] == "$120,000 - $150,000 a year"
    assert rows[0][2:6] == (120000.0, 150000.0, "USD", "yearly") and rows[0][7] == "salary_text"
    assert rows[1][1] == "Competitive Salary" and rows[1][6] == 124800.0 and rows[1][7] == "description_text"
    assert rows[2][7] is None
