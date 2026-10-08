"""Author: Joonyoung Ki

Purpose: Unit tests for the pure salary parser in app/services/salary_parser.py.
"""

import pytest

from app.services.salary_parser import (
    annualize,
    build_salary_info,
    normalize_currency,
    normalize_period,
    parse_salary_text,
    to_usd_approx,
)


def _tuple(info):
    """Return the core fields of a SalaryInfo as a comparable tuple."""
    return (info.min, info.max, info.currency, info.period, info.annual_min, info.annual_max)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$120,000 - $150,000 a year", (120000, 150000, "USD", "yearly", 120000, 150000)),
        ("$120,000 – $150,000 per year", (120000, 150000, "USD", "yearly", 120000, 150000)),
        ("$45/hr", (45, 45, "USD", "hourly", 93600, 93600)),
        ("$45 - $60 per hour", (45, 60, "USD", "hourly", 93600, 124800)),
        ("$45.50/hour", (45.5, 45.5, "USD", "hourly", 94640, 94640)),
        ("120k-150k", (120000, 150000, None, "yearly", 120000, 150000)),
        ("$120k - $150k", (120000, 150000, "USD", "yearly", 120000, 150000)),
        ("$120-150k", (120000, 150000, "USD", "yearly", 120000, 150000)),
        ("$8,000 - $10,000 per month", (8000, 10000, "USD", "monthly", 96000, 120000)),
        ("$2,000/week", (2000, 2000, "USD", "weekly", 104000, 104000)),
        ("$400 per day", (400, 400, "USD", "daily", 104000, 104000)),
        ("CAD 90,000 - 110,000", (90000, 110000, "CAD", "yearly", 90000, 110000)),
        ("C$100k - C$130k annually", (100000, 130000, "CAD", "yearly", 100000, 130000)),
        ("$90,000 - $110,000 CAD", (90000, 110000, "CAD", "yearly", 90000, 110000)),
        ("CA$85,000 to CA$105,000", (85000, 105000, "CAD", "yearly", 85000, 105000)),
        ("£46,000 — £54,000 GBP", (46000, 54000, "GBP", "yearly", 46000, 54000)),
        ("€110K – €185K", (110000, 185000, "EUR", "yearly", 110000, 185000)),
        ("€60.000 - €80.000 per year", (60000, 80000, "EUR", "yearly", 60000, 80000)),
        ("USD $100,000 to $130,000", (100000, 130000, "USD", "yearly", 100000, 130000)),
        ("$130,000 - $100,000 per year", (100000, 130000, "USD", "yearly", 100000, 130000)),
        ("up to $150k", (None, 150000, "USD", "yearly", None, 150000)),
        ("from $90,000 per year", (90000, None, "USD", "yearly", 90000, None)),
        ("$95,000", (95000, 95000, "USD", "yearly", 95000, 95000)),
        ("The base salary range for this role is $142,000-$198,000 USD plus equity.", (142000, 198000, "USD", "yearly", 142000, 198000)),
        ("Pay: $25 - $30 an hour", (25, 30, "USD", "hourly", 52000, 62400)),
        ("Hourly: $30-$40", (30, 40, "USD", "hourly", 62400, 83200)),
        ("40 - 50 / hr", (40, 50, None, "hourly", 83200, 104000)),
    ],
)
def test_parse_valid_salaries(text, expected):
    """Common salary notations are parsed into the expected structure."""
    info = parse_salary_text(text)
    assert info is not None, text
    got = _tuple(info)
    for g, e in zip(got, expected):
        if isinstance(e, (int, float)):
            assert g == pytest.approx(e), (text, got)
        else:
            assert g == e, (text, got)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Competitive Salary",
        "None",
        "Negotiable",
        "5 years of experience required",
        "Join our team of 200 engineers",
        "We raised $50 million in Series B funding",
        "401k matching and great benefits",
        "Up to 10% bonus",
        "Posted 3 days ago",
        "$5",
        "$20 - $25",
        "$100 - $200",
    ],
)
def test_parse_returns_none_for_non_salary_text(text):
    """Text without a real pay figure yields None rather than a bogus value."""
    assert parse_salary_text(text) is None


def test_default_currency_applies_only_when_missing():
    """default_currency fills in the currency only if the text has none."""
    assert parse_salary_text("120k-150k", default_currency="CAD").currency == "CAD"
    assert parse_salary_text("$120k-$150k", default_currency="CAD").currency == "USD"


def test_ambiguous_amount_without_period_has_no_annual_value():
    """A mid-sized bare number is ambiguous, so no annual figure is produced."""
    info = parse_salary_text("$3,500")
    assert info is None or info.annual_max is None


def test_first_plausible_range_wins_in_long_text():
    """In long descriptions the first valid pay range is selected."""
    text = (
        "Acme was founded in 2010 and has 500 employees. "
        "The pay range for this role is $130,000 - $160,000 per year. "
        "Senior roles may reach $200,000 - $230,000 per year."
    )
    info = parse_salary_text(text)
    assert (info.min, info.max, info.period) == (130000, 160000, "yearly")


def test_annualize_and_conversions():
    """Annualisation factors and helper normalisers behave as documented."""
    assert annualize(50, "hourly") == 104000
    assert annualize(10000, "monthly") == 120000
    assert annualize(None, "yearly") is None
    assert annualize(10, None) is None
    assert normalize_period("per-year-salary") == "yearly"
    assert normalize_period("per-hour-wage") == "hourly"
    assert normalize_period("1 YEAR") == "yearly"
    assert normalize_period("HOUR") == "hourly"
    assert normalize_period("weird") is None
    assert normalize_currency("$") == "USD"
    assert normalize_currency("cad") == "CAD"
    assert normalize_currency("C$") == "CAD"
    assert normalize_currency("??") is None
    assert to_usd_approx(100, "EUR") > 100
    assert to_usd_approx(100, "XXX") is None
    assert to_usd_approx(None, "USD") is None


def test_build_salary_info_validation():
    """Structured inputs are validated, swapped and rejected when implausible."""
    info = build_salary_info(150000, 120000, "usd", "yearly", source="x")
    assert (info.min, info.max, info.currency, info.source) == (120000, 150000, "USD", "x")
    assert build_salary_info(None, None, "USD", "yearly") is None
    assert build_salary_info(0, 0, "USD", "yearly") is None
    assert build_salary_info(5, 9, "USD", "yearly") is None
    assert build_salary_info(50, 5_000_000, "USD", "hourly") is None
    hourly = build_salary_info(45, 60, "USD", "per-hour-wage")
    assert hourly.annual_min == 93600
