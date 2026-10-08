# app/database.py
import os
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_match"


def _normalize_db_url(url: str) -> str:
    """postgresql:// 또는 postgres:// 형태로 주어져도 비동기 드라이버(asyncpg)로 변환합니다."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


# DB_URL 을 우선 사용하고, 기존 배포 호환을 위해 DATABASE_URL 도 계속 지원합니다.
SQLALCHEMY_DATABASE_URL = _normalize_db_url(
    os.getenv("DB_URL") or os.getenv("DATABASE_URL") or DEFAULT_DB_URL
)

# pool_pre_ping: RDS 등에서 유휴 커넥션이 끊겨도 자동 복구
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", 5)),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 10)),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 1800)),
)
print(f"🔗 [DB Connection Target]: {make_url(SQLALCHEMY_DATABASE_URL).render_as_string(hide_password=True).split('@')[-1]}")

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    """
    FastAPI 엔드포인트에서 호출할 때마다 독립적인 비동기 DB 세션을 열고 닫습니다.
    """
    async with AsyncSessionLocal() as session:
        yield session
