"""
Author: Joonyoung Ki

Purpose: Shared pytest fixtures for the account API tests. Tests run against a
real PostgreSQL + pgvector database given by TEST_DATABASE_URL (the database
name must contain "test" because tables are dropped and recreated). OpenAI and
Redis are never contacted: AI calls are monkeypatched and Redis is disabled.

Example:
    TEST_DATABASE_URL=postgresql+asyncpg://jm:jm@localhost:5432/job_match_test pytest
"""

import os

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is not set", allow_module_level=True)
if "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL must point to a database whose name contains 'test'")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-0123456789")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-used")
os.environ["REDIS_HOST"] = "127.0.0.1"
os.environ["REDIS_PORT"] = "1"

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import main as app_main  # noqa: E402
from app import models  # noqa: E402
from app.accounts.rate_limit import login_limiter  # noqa: E402
from app.database import engine  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database():
    """Recreate every table once per test session on the dedicated test database."""
    app_main.rd = None
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(models.Base.metadata.drop_all)
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_state(database):
    """Empty the account tables and the rate limiter before each test."""
    login_limiter.clear()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE wishlist_items, users RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def client():
    """Return an httpx client bound to the FastAPI app (lifespan hooks are not run)."""
    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def job_ids():
    """Insert two job postings and one resume row; return their ids."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        jobs = [
            models.JobPosting(
                title="Backend Engineer", company="Acme", location="Vancouver, BC",
                salary="$100k", skills="Python, AWS", embedding=[0.1] * 1536,
                employment_type="Full-time", experience_level="Junior",
            ),
            models.JobPosting(
                title="Data Engineer", company="Globex", location="Vancouver, BC",
                salary="None", skills="SQL", embedding=[0.2] * 1536,
                employment_type="Full-time", experience_level="Junior",
            ),
        ]
        resume = models.JobPosting(
            title="RESUME: a.pdf", company="USER_UPLOAD", description="Python dev",
            location="Vancouver, BC", embedding=[0.1] * 1536,
        )
        db.add_all(jobs + [resume])
        await db.commit()
        for obj in jobs + [resume]:
            await db.refresh(obj)
        ids = {"jobs": [j.id for j in jobs], "resume": resume.id}
    yield ids
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE match_analyses, job_postings RESTART IDENTITY CASCADE"))
