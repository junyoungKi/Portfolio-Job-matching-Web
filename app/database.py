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