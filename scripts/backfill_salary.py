"""Author: Joonyoung Ki

Purpose: Backfill the structured salary columns of existing ``job_postings``
rows by re-parsing the stored ``salary`` text (and, optionally, pay-range
sentences in ``description``). No crawling is performed.

Safe to re-run: only rows without a ``salary_source`` are touched (use
``--force`` to re-parse everything), rows are processed in id order in small
committed batches, and the original ``salary`` text is never modified.

Usage:
    python -m scripts.backfill_salary --dry-run
    python -m scripts.backfill_salary --from-description
"""

import argparse
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.services.migrations import run_salary_migration  # noqa: E402
from app.services.salary_sources import from_description_text, from_salary_text  # noqa: E402
from app.services.salary_store import salary_columns_from_info  # noqa: E402

UPDATE_SQL = text(
    "UPDATE job_postings SET salary_min = :salary_min, salary_max = :salary_max, "
    "salary_currency = :salary_currency, salary_period = :salary_period, "
    "salary_annual_min = :salary_annual_min, salary_annual_max = :salary_annual_max, "
    "salary_source = :salary_source WHERE id = :id"
)


def parse_args() -> argparse.Namespace:
    """Parse command line options for the backfill."""
    parser = argparse.ArgumentParser(description="Backfill structured salary columns from existing text.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; do not write.")
    parser.add_argument("--from-description", action="store_true", help="Also look for pay ranges in the description.")
    parser.add_argument("--force", action="store_true", help="Re-parse rows that already have a salary_source.")
    parser.add_argument("--batch-size", type=int, default=200, help="Rows per transaction (default 200).")
    parser.add_argument("--limit", type=int, default=0, help="Stop after scanning this many rows (0 = all).")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    """Scan rows in id order, parse salaries and update rows in batches."""
    await run_salary_migration(engine)
    stats = {"scanned": 0, "parsed": 0, "updated": 0, "unparsable": 0}
    last_id = 0
    where_done = "" if args.force else "AND salary_source IS NULL"
    select_sql = text(
        "SELECT id, salary, description FROM job_postings "
        f"WHERE id > :last_id AND company <> 'USER_UPLOAD' {where_done} "
        "ORDER BY id LIMIT :batch"
    )
    while True:
        async with engine.begin() as conn:
            rows = (await conn.execute(select_sql, {"last_id": last_id, "batch": args.batch_size})).all()
            if not rows:
                break
            updates = []
            for row_id, salary, description in rows:
                stats["scanned"] += 1
                info = from_salary_text(salary)
                if info is None and args.from_description:
                    info = from_description_text(description)
                if info is None:
                    stats["unparsable"] += 1
                    continue
                stats["parsed"] += 1
                if args.dry_run:
                    print(f"[dry-run] id={row_id} {salary!r} -> {info.min}-{info.max} {info.currency} {info.period} ({info.source})")
                    continue
                updates.append({"id": row_id, **salary_columns_from_info(info)})
            if updates:
                await conn.execute(UPDATE_SQL, updates)
                stats["updated"] += len(updates)
        last_id = rows[-1][0]
        if args.limit and stats["scanned"] >= args.limit:
            break
    return stats


async def main() -> None:
    """Entry point: run the backfill and print a summary."""
    args = parse_args()
    stats = await run(args)
    print(f"Backfill {'(dry run) ' if args.dry_run else ''}finished: {stats}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
