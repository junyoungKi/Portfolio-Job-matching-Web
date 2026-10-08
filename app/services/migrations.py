"""Author: Joonyoung Ki

Purpose: Idempotent, production-safe schema migrations for ``job_postings``.

``Base.metadata.create_all`` never adds columns to an existing table, so the
structured salary columns are added with ``ALTER TABLE ... ADD COLUMN IF NOT
EXISTS``. Adding a nullable column without a default is a metadata-only change
in PostgreSQL, so existing rows and the legacy ``salary`` text are untouched
and the statement is safe to run repeatedly on a live RDS instance.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .salary_store import SALARY_COLUMN_DDL

logger = logging.getLogger(__name__)

# Arbitrary constant key so concurrent app workers serialise their DDL.
MIGRATION_ADVISORY_LOCK_KEY = 7_302_024_001
LOCK_TIMEOUT = "5s"


async def ensure_salary_columns(conn: AsyncConnection) -> list:
    """Add the structured salary columns to ``job_postings`` if missing.

    Must run inside a transaction (``engine.begin()``). Returns the list of
    column names that were newly added (empty when already migrated). The
    table is skipped silently when it does not exist yet, since ``create_all``
    will create it with the columns already present.
    """
    await conn.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_ADVISORY_LOCK_KEY})
    exists = (await conn.execute(text("SELECT to_regclass('public.job_postings') IS NOT NULL"))).scalar()
    if not exists:
        return []
    before = {
        row[0]
        for row in await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'job_postings'"
            )
        )
    }
    for name, ddl_type in SALARY_COLUMN_DDL:
        await conn.execute(text(f"ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS {name} {ddl_type}"))
    return [name for name, _ in SALARY_COLUMN_DDL if name not in before]


async def run_salary_migration(engine: AsyncEngine, attempts: int = 3) -> list:
    """Run ``ensure_salary_columns`` in its own transaction with retries.

    A short ``lock_timeout`` keeps the migration from stalling live traffic;
    if another session holds a conflicting lock we back off and retry before
    giving up with the last error.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                added = await ensure_salary_columns(conn)
            logger.info("Salary migration complete; added columns: %s", added or "none")
            return added
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised below
            last_error = exc
            logger.warning("Salary migration attempt %d/%d failed: %s", attempt, attempts, exc)
            await asyncio.sleep(2 * attempt)
    assert last_error is not None
    raise last_error
