import asyncio
from sqlalchemy import text
from app.database import engine
from app.models import Base

async def reset_database():
    print("Starting database reset...")
    async with engine.begin() as conn:
        print("Enabling vector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

        print("Dropping existing tables...")
        await conn.run_sync(Base.metadata.drop_all)

        print("Creating new tables...")
        await conn.run_sync(Base.metadata.create_all)

    print("Database reset completed successfully.")

if __name__ == "__main__":
    asyncio.run(reset_database())