"""Author: Joonyoung Ki

Purpose: Optional scheduled ingestion of jobs from public ATS boards
(Greenhouse / Lever / Ashby) with structured salary data.

Boards are configured through the ``ATS_BOARDS`` environment variable, e.g.
``ATS_BOARDS="greenhouse:airbnb,lever:weride,ashby:ashby"``. When it is empty
(the default) nothing is crawled. Only postings whose location maps to one of
the collector's North America hubs are stored, because ``/match`` filters on
those exact location strings.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from sqlalchemy import select

from .. import models
from ..database import AsyncSessionLocal
from .ats_client import fetch_ats_jobs
from .collector import job_collector
from .salary_store import salary_columns_from_info

logger = logging.getLogger(__name__)

_HUB_ALIASES = {
    "vancouver": "Vancouver, BC",
    "toronto": "Toronto, ON",
    "seattle": "Seattle, WA",
    "san francisco": "San Francisco, CA",
    "austin": "Austin, TX",
    "new york": "New York, NY",
    "nyc": "New York, NY",
    "los angeles": "Los Angeles, CA",
    "montreal": "Montreal, QC",
    "montréal": "Montreal, QC",
}


def parse_ats_boards(value: Optional[str]) -> List[Tuple[str, str]]:
    """Parse ``provider:board`` pairs from a comma-separated string."""
    boards = []
    for item in (value or "").split(","):
        item = item.strip()
        if ":" not in item:
            continue
        provider, board = item.split(":", 1)
        if provider.strip().lower() in {"greenhouse", "lever", "ashby"} and board.strip():
            boards.append((provider.strip().lower(), board.strip()))
    return boards


def map_location_to_hub(location: Optional[str]) -> Optional[str]:
    """Map a free-text job location onto a known collector hub, else ``None``."""
    lowered = (location or "").lower()
    for alias, hub in _HUB_ALIASES.items():
        if alias in lowered and hub in job_collector.NA_HUBS:
            return hub
    return None


def matches_keyword(job: dict, keyword: str) -> bool:
    """Return True when every word of the keyword appears in title or description."""
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return all(word in haystack for word in keyword.lower().split())


async def ingest_ats_jobs(keyword: str = "Software Engineer", boards: Optional[List[Tuple[str, str]]] = None) -> dict:
    """Fetch configured ATS boards and store new jobs with structured salary.

    Existing rows (same title and company) are not duplicated; if they lack a
    structured salary and the ATS provides one, only the salary columns are
    updated. Returns simple counters for logging.
    """
    from .ai import ai_service

    boards = boards if boards is not None else parse_ats_boards(os.getenv("ATS_BOARDS"))
    stats = {"fetched": 0, "inserted": 0, "salary_updated": 0, "skipped": 0}
    async with AsyncSessionLocal() as db:
        for provider, board in boards:
            for job in await fetch_ats_jobs(provider, board):
                stats["fetched"] += 1
                hub = map_location_to_hub(job.get("location"))
                if not hub or not matches_keyword(job, keyword):
                    stats["skipped"] += 1
                    continue
                try:
                    stmt = select(models.JobPosting).filter(
                        models.JobPosting.title == job["title"],
                        models.JobPosting.company == job["company"],
                    )
                    existing = (await db.execute(stmt)).scalars().first()
                    columns = salary_columns_from_info(job.get("salary_info"))
                    if existing:
                        if existing.salary_source is None and columns["salary_source"]:
                            for key, value in columns.items():
                                setattr(existing, key, value)
                            existing.salary = job["salary"]
                            await db.commit()
                            stats["salary_updated"] += 1
                        else:
                            stats["skipped"] += 1
                        continue
                    meta = await ai_service.extract_job_metadata(job["description"])
                    embedding = await ai_service.get_embedding(job["description"])
                    db.add(models.JobPosting(
                        title=job["title"], company=job["company"], description=job["description"],
                        location=hub, salary=job["salary"], search_keyword=keyword, embedding=embedding,
                        employment_type=meta.get("employment_type", "Full-time"),
                        experience_level=meta.get("experience_level", "Junior"),
                        skills=", ".join(meta.get("skills", [])),
                        **columns,
                    ))
                    await db.commit()
                    stats["inserted"] += 1
                except Exception as exc:  # noqa: BLE001 - keep crawling other jobs
                    await db.rollback()
                    logger.warning("ATS job %r failed: %s", job.get("title"), exc)
    logger.info("ATS ingest finished: %s", stats)
    return stats


async def scheduled_ats_crawl() -> None:
    """Scheduler entry point; a no-op unless ``ATS_BOARDS`` is configured."""
    if parse_ats_boards(os.getenv("ATS_BOARDS")):
        await ingest_ats_jobs()
