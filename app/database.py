# app/database.py
"""
Author: Joonyoung Ki

Database configuration for the application.

Creates the asynchronous SQLAlchemy engine (PostgreSQL via asyncpg), the async session factory,
the declarative ``Base`` shared by all models, and the ``get_db`` FastAPI dependency.
"""
import os
import socket
import time
from contextvars import ContextVar

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

load_dotenv()

# The driver is switched from 'postgresql://' to 'postgresql+asyncpg://' for async access.
# (Note: adjust the user, password and dbname below to match your local DB environment.)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://user:password@localhost:5432/job_match"
)
def _positive_number(name, default, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        print(f"Ignoring invalid {name}={raw!r}; using {default}")
        return default
    if value <= 0:
        print(f"Ignoring non-positive {name}={value}; using {default}")
        return default
    return value


# Defensive pool settings. They do not identify why a crawl once failed to return.
# pre_ping drops a pooled connection that is already closed. recycle replaces one
# that has been open longer than this, so an idle connection is not kept forever.
# command_timeout bounds a single query so a database wait cannot sit there without a limit.
DB_POOL_RECYCLE_SECONDS = _positive_number("DB_POOL_RECYCLE_SECONDS", 1800, int)
DB_COMMAND_TIMEOUT_SECONDS = _positive_number("DB_COMMAND_TIMEOUT_SECONDS", 30, int)
DB_TCP_KEEPIDLE_SECONDS = _positive_number("DB_TCP_KEEPIDLE_SECONDS", 60, int)
DB_TCP_KEEPINTVL_SECONDS = _positive_number("DB_TCP_KEEPINTVL_SECONDS", 10, int)
DB_TCP_KEEPCNT = _positive_number("DB_TCP_KEEPCNT", 5, int)


def async_engine_kwargs():
    """Keyword arguments for the async engine, apart from the URL."""
    return {
        "echo": False,
        "pool_pre_ping": True,
        "pool_recycle": DB_POOL_RECYCLE_SECONDS,
        "connect_args": {"command_timeout": DB_COMMAND_TIMEOUT_SECONDS},
    }


def tcp_keepalive_enabled():
    """Return whether the connect hook should set TCP keepalive.

    Default is on, matching the previous deploy. Set ``DB_TCP_KEEPALIVE`` to
    ``0``, ``false``, ``no``, or ``off`` to skip the hook. The hook calls
    ``setsockopt`` only; it does not call into OpenSSL.
    """
    raw = os.getenv("DB_TCP_KEEPALIVE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def enable_tcp_keepalive(dbapi_connection):
    """Turn on TCP keepalive for one asyncpg connection, when the socket is visible.

    asyncpg does not take keepalive arguments. The socket is reached through the
    adapted connection SQLAlchemy hands to the connect event.
    """
    raw = getattr(dbapi_connection, "_connection", None)
    transport = getattr(raw, "_transport", None) if raw is not None else None
    sock = transport.get_extra_info("socket") if transport is not None else None
    if sock is None:
        return
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, DB_TCP_KEEPIDLE_SECONDS)
    elif hasattr(socket, "TCP_KEEPALIVE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, DB_TCP_KEEPIDLE_SECONDS)
    if hasattr(socket, "TCP_KEEPINTVL"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, DB_TCP_KEEPINTVL_SECONDS)
    if hasattr(socket, "TCP_KEEPCNT"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, DB_TCP_KEEPCNT)


# 1. Create the async engine.
# Keeping echo=False stops SQL statements from being printed to the terminal, which improves speed.
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, **async_engine_kwargs())


@event.listens_for(engine.sync_engine, "connect")
def _enable_tcp_keepalive(dbapi_connection, connection_record):
    if not tcp_keepalive_enabled():
        return
    try:
        enable_tcp_keepalive(dbapi_connection)
    except Exception as exc:
        print(f"TCP keepalive was not enabled on a database connection: {exc}")


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