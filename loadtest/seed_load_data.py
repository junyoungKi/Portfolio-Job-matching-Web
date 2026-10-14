"""
Seed deterministic job postings for load tests (stub embeddings, no OpenAI calls).

Inserts the same N postings every time (fixed random seed), spread over the North American hub
cities, with varied experience levels, employment types and skills, so ``/match`` has realistic
candidates under every filter combination used by ``locustfile.py``. Embeddings come from
``loadtest/fake_openai.py`` (``fake_embedding``), the same function the fake server uses for
resumes, so no server has to be running while seeding.

Take a ``pg_dump`` right after seeding and restore it before every measured run so that the
baseline and the fixed commit start from byte-identical data.

    DATABASE_URL=postgresql+asyncpg://user:pw@localhost:5432/job_match \\
        python loadtest/seed_load_data.py --jobs 400 --reset
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, select, text  # noqa: E402

from app import models  # noqa: E402
from app.database import AsyncSessionLocal, engine  # noqa: E402
from fake_openai import fake_embedding  # noqa: E402

HUBS = [
    "Vancouver, BC", "Toronto, ON", "Seattle, WA", "San Francisco, CA",
    "Austin, TX", "New York, NY", "Los Angeles, CA", "Montreal, QC",
]
LEVELS = ["Entry", "Junior", "Mid", "Senior"]
TYPES = ["Full-time", "Full-time", "Full-time", "Contract", "Internship", "Part-time"]
SKILLS = [
    "Python", "Java", "Go", "TypeScript", "React", "SQL", "PostgreSQL", "Redis",
    "Docker", "Kubernetes", "AWS", "FastAPI", "C++", "Rust", "Kafka", "GraphQL",
]
TITLES = [
    "Software Engineer", "Backend Engineer", "Full Stack Developer", "Platform Engineer",
    "Data Engineer", "Machine Learning Engineer", "DevOps Engineer", "Site Reliability Engineer",
]


def build_jobs(count: int, seed: int):
    rng = random.Random(seed)
    for i in range(count):
        skills = rng.sample(SKILLS, 4)
        title = f"{rng.choice(TITLES)} #{i}"
        company = f"LoadTest Co {i % 57}"
        location = HUBS[i % len(HUBS)]
        description = (
            f"{title} at {company} in {location}. Work with {', '.join(skills)}. "
            f"Build and operate production services. Posting {i}."
        )
        yield models.JobPosting(
            title=title,
            company=company,
            description=description,
            location=location,
            salary="Competitive Salary",
            search_keyword="Software Engineer",
            embedding=fake_embedding(description),
            employment_type=rng.choice(TYPES),
            experience_level=rng.choice(LEVELS),
            skills=", ".join(skills),
        )


async def main(count: int, seed: int, reset: bool):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(models.Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count(models.JobPosting.id)))).scalar()
        if existing and not reset:
            sys.exit(f"job_postings already has {existing} rows; pass --reset to wipe job_postings and match_analyses first")
        if reset:
            await db.execute(text("TRUNCATE TABLE match_analyses, job_postings RESTART IDENTITY"))
        batch = []
        for job in build_jobs(count, seed):
            batch.append(job)
            if len(batch) == 200:
                db.add_all(batch)
                await db.commit()
                batch = []
        if batch:
            db.add_all(batch)
            await db.commit()
        total = (await db.execute(select(func.count(models.JobPosting.id)))).scalar()
    # Fresh statistics keep the query planner's choices the same from run to run.
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("ANALYZE job_postings"))
    await engine.dispose()
    print(f"Seeded {count} postings (job_postings now has {total} rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=400)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--reset", action="store_true", help="TRUNCATE job_postings and match_analyses first")
    args = parser.parse_args()
    asyncio.run(main(args.jobs, args.seed, args.reset))
