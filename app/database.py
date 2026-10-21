# app/database.py
"""
Author: Joonyoung Ki

Database configuration for the application.

Creates the asynchronous SQLAlchemy engine (PostgreSQL via asyncpg), the async session factory,
the declarative ``Base`` shared by all models, and the ``get_db`` FastAPI dependency.
"""
import os
import time
from contextvars import ContextVar

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

# The driver is switched from 'postgresql://' to 'postgresql+asyncpg://' for async access.
# (Note: adjust the user, password and dbname below to match your local DB environment.)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://user:password@localhost:5432/job_match"
)
# 1. Create the async engine.
# Keeping echo=False stops SQL statements from being printed to the terminal, which improves speed.
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
# Log only the host/database part of the URL so that credentials are never printed.
masked_url = SQLALCHEMY_DATABASE_URL.split("@")[-1] if "@" in SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL
print(f"[DB Connection Target]: {masked_url}")

# 2. Create the async session factory.
# A factory that produces AsyncSession objects is used instead of the classic SessionLocal.
# expire_on_commit=False keeps ORM objects usable after commit, which async code relies on.
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 3. Base class from which all models inherit.
Base = declarative_base()

# 4. Async DB session generator used for dependency injection.
async def get_db():
    """
    Open an independent async DB session for each FastAPI request and close it afterwards.
    """
    async with AsyncSessionLocal() as session:
        yield session


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# Opt-in SQL counter. Off unless QUERY_STATS=1 (also true/yes/on). The cursor hooks are not
# registered when it is off, so a normal request does not pay for them.
QUERY_STATS_ENABLED = _env_flag("QUERY_STATS")
_query_stats: ContextVar = ContextVar("query_stats", default=None)


class query_stats_scope:
    """Count cursor executions, and how long they took, while this block is active."""

    def __enter__(self):
        self.data = {"count": 0, "seconds": 0.0, "_t": None}
        self.token = _query_stats.set(self.data)
        return self.data

    def __exit__(self, exc_type, exc, tb):
        _query_stats.reset(self.token)
        return False


def note_query_start() -> None:
    stats = _query_stats.get()
    if stats is None:
        return
    stats["count"] += 1
    stats["_t"] = time.perf_counter()


def note_query_end() -> None:
    stats = _query_stats.get()
    if not stats or stats.get("_t") is None:
        return
    stats["seconds"] += time.perf_counter() - stats["_t"]
    stats["_t"] = None


def format_query_stats(kind: str, name: str, stats: dict, wall_seconds: float) -> str:
    """One log line: statements, DB time, wall time, and DB time as a share of wall time."""
    db_seconds = float(stats.get("seconds") or 0.0)
    share = (db_seconds / wall_seconds) if wall_seconds > 0 else 0.0
    return (
        f"[QUERY_STATS] {kind} {name} statements={int(stats.get('count') or 0)} "
        f"db_ms={db_seconds * 1000:.1f} wall_ms={wall_seconds * 1000:.1f} db_share={share:.3f}"
    )


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    note_query_start()


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    note_query_end()


if QUERY_STATS_ENABLED:
    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine.sync_engine, "after_cursor_execute", _after_cursor_execute)
    print("[QUERY_STATS] SQL statement counting is on")