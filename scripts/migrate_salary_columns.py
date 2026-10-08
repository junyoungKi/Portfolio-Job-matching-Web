"""Author: Joonyoung Ki

Purpose: Standalone, idempotent migration that adds the structured salary
columns to ``job_postings``. Safe to run repeatedly against the production
RDS database (``ADD COLUMN IF NOT EXISTS``, nullable, no rewrite).

Usage: ``python -m scripts.migrate_salary_columns``
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402
from app.services.migrations import run_salary_migration  # noqa: E402


async def main() -> None:
    """Run the salary column migration and report which columns were added."""
    added = await run_salary_migration(engine)
    print(f"Added columns: {', '.join(added) if added else 'none (already up to date)'}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
