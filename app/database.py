# app/database.py
"""
Author: Joonyoung Ki

Database configuration for the application.

Creates the asynchronous SQLAlchemy engine (PostgreSQL via asyncpg), the async session factory,
the declarative ``Base`` shared by all models, and the ``get_db`` FastAPI dependency.
"""
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

# The driver is switched from 'postgresql://' to 'postgresql+asyncpg://' for async access.
# (Note: adjust the user, password and dbname below to match your local DB environment.)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://user:password@localhost:5432/job_match"
)


def _env_int(name: str, default: int) -> int:
    """Read a non-negative integer setting from the environment, falling back to ``default``."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"Ignoring invalid {name}={raw!r}; using {default}")
        return default
    return value if value >= 0 else default


# Connection pool settings, explicit and env-configurable so a deployment or load test can size the
# pool deliberately. The defaults equal SQLAlchemy's own (5 + 10 overflow, 30 s wait), so behaviour
# is unchanged until you override them. The pool is per process: with N uvicorn workers the server
# can open N * (DB_POOL_SIZE + DB_MAX_OVERFLOW) connections, which must stay below Postgres'
# max_connections.
DB_POOL_SIZE = _env_int("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW = _env_int("DB_MAX_OVERFLOW", 10)
DB_POOL_TIMEOUT = _env_int("DB_POOL_TIMEOUT", 30)

# 1. Create the async engine.
# Keeping echo=False stops SQL statements from being printed to the terminal, which improves speed.
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
)
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