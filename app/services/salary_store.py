"""Author: Joonyoung Ki

Purpose: Bridge between ``SalaryInfo`` values, the ``job_postings`` salary
columns and the API response shape.

It defines the single source of truth for the structured salary column names
and DDL types, converts a ``SalaryInfo`` into column values for inserts and
updates, and builds the extra salary fields returned by the ``/match`` API.
"""

from __future__ import annotations

from typing import Any, Optional

from .salary_parser import SalaryInfo, to_usd_approx

# (column name, PostgreSQL type) pairs; used by the migration and the model.
SALARY_COLUMN_DDL = (
    ("salary_min", "DOUBLE PRECISION"),
    ("salary_max", "DOUBLE PRECISION"),
    ("salary_currency", "VARCHAR(3)"),
    ("salary_period", "VARCHAR(16)"),
    ("salary_annual_min", "DOUBLE PRECISION"),
    ("salary_annual_max", "DOUBLE PRECISION"),
    ("salary_source", "VARCHAR(32)"),
)
SALARY_COLUMN_NAMES = tuple(name for name, _ in SALARY_COLUMN_DDL)


def empty_salary_columns() -> dict:
    """Return salary column values meaning "no structured salary known"."""
    return {name: None for name in SALARY_COLUMN_NAMES}


def salary_columns_from_info(info: Optional[SalaryInfo]) -> dict:
    """Convert a ``SalaryInfo`` into a dict keyed by the salary column names."""
    if info is None:
        return empty_salary_columns()
    return {
        "salary_min": info.min,
        "salary_max": info.max,
        "salary_currency": info.currency,
        "salary_period": info.period,
        "salary_annual_min": info.annual_min,
        "salary_annual_max": info.annual_max,
        "salary_source": info.source,
    }


def salary_api_fields(job: Any) -> dict:
    """Build the additive structured-salary fields for the ``/match`` response.

    Annual USD values are approximations (static FX table) intended only for
    sorting across currencies; ``None`` is returned for unknown values.
    """
    currency = getattr(job, "salary_currency", None)
    annual_min = getattr(job, "salary_annual_min", None)
    annual_max = getattr(job, "salary_annual_max", None)
    return {
        "salary_min": getattr(job, "salary_min", None),
        "salary_max": getattr(job, "salary_max", None),
        "salary_currency": currency,
        "salary_period": getattr(job, "salary_period", None),
        "salary_annual_min": annual_min,
        "salary_annual_max": annual_max,
        "salary_annual_min_usd_approx": to_usd_approx(annual_min, currency),
        "salary_annual_max_usd_approx": to_usd_approx(annual_max, currency),
        "salary_source": getattr(job, "salary_source", None),
    }
