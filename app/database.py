# app/database.py
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

# 🎯 기존 'postgresql://' 에서 'postgresql+asyncpg://' 로 드라이버를 변경합니다.
# (주의: 아래 user, password, dbname은 실제 준영님의 로컬 DB 환경에 맞게 수정해주세요)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://user:password@localhost:5432/job_match"
)
# 1. 비동기 엔진 생성
# echo=False로 설정하면 터미널에 SQL 쿼리문이 출력되는 것을 막아 속도를 높일 수 있습니다.
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
masked_url = SQLALCHEMY_DATABASE_URL.split("@")[-1] if "@" in SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL
print(f"🔗 [DB Connection Target]: {masked_url}")

# 2. 비동기 세션 팩토리 생성
# SessionLocal 대신 AsyncSession을 생성하는 팩토리를 만듭니다.
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 3. 모델의 기본이 되는 Base 클래스
Base = declarative_base()

# 4. 의존성 주입을 위한 비동기 DB 세션 제너레이터
async def get_db():
    """
    FastAPI 엔드포인트에서 호출할 때마다 독립적인 비동기 DB 세션을 열고 닫습니다.
    """
    async with AsyncSessionLocal() as session:
        yield session