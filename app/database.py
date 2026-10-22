# app/database.py
"""
Author: Joonyoung Ki

Database configuration for the application.

Creates the asynchronous SQLAlchemy engine (PostgreSQL via asyncpg), the async session factory,
the declarative ``Base`` shared by all models, and the ``get_db`` FastAPI dependency.
"""
import os
import socket

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