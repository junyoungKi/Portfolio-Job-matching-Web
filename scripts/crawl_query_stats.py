"""Count SQL statements for one crawler city, without calling OpenAI or LinkedIn.

This script exists only on the fixed branch. The baseline commit (529e2a1) has no
``store_scraped_jobs`` and no ``QUERY_STATS`` hook; use ``pg_stat_statements`` there,
as described in docs/performance-measurement.md.

    QUERY_STATS=1 DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/job_match \\
        python scripts/crawl_query_stats.py

The AI calls are replaced with local stubs, so no API key is used. The database must
be reachable. The script deletes the sample rows (company ``Query Stats Co``) afterwards.
"""
import asyncio
import os

os.environ["QUERY_STATS"] = "1"
os.environ.setdefault("OPENAI_API_KEY", "stub")

from sqlalchemy import delete  # noqa: E402

from app import models  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.main import ai_service, store_scraped_jobs  # noqa: E402


async def _meta(_description):
    return {"employment_type": "Full-time", "experience_level": "Junior", "skills": ["Python"]}


async def _embed(_description):
    return [0.01] * 1536


async def main():
    ai_service.extract_job_metadata = _meta
    ai_service.get_embedding = _embed
    jobs = [
        {
            "title": f"Load test role {i}",
            "company": "Query Stats Co",
            "description": f"Sample posting {i} for statement counting.",
            "location": "Seattle, WA",
            "salary": "Competitive Salary",
        }
        for i in range(5)
    ]
    async with AsyncSessionLocal() as db:
        try:
            saved = await store_scraped_jobs(db, jobs, "Software Engineer")
        finally:
            await db.execute(delete(models.JobPosting).where(
                models.JobPosting.company == "Query Stats Co"
            ))
            await db.commit()
        print(f"inserted={saved} (those rows were deleted afterwards)")


if __name__ == "__main__":
    asyncio.run(main())
