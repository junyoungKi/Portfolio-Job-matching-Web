"""Author: Joonyoung Ki

Purpose: Tests for the ATS / JSON-LD / description salary extractors using
fixed fixtures (real payload excerpts from public job board APIs).
"""

import json
import pathlib

from app.services.ats_client import (
    _format_salary_text,
    normalize_ashby_job,
    normalize_greenhouse_job,
    normalize_lever_job,
)
from app.services.ats_ingest import map_location_to_hub, matches_keyword, parse_ats_boards
from app.services.salary_sources import (
    extract_best_salary,
    from_ashby_job,
    from_description_text,
    from_greenhouse_job,
    from_jsonld_html,
    from_lever_posting,
    html_to_text,
)
from app.services.salary_store import salary_api_fields, salary_columns_from_info

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    """Load a JSON fixture by file name."""
    return json.loads((FIXTURES / name).read_text())


def test_greenhouse_pay_input_ranges_are_converted_from_cents():
    """Greenhouse pay_input_ranges (cents) become whole-currency annual values."""
    info = from_greenhouse_job(load("greenhouse_job_with_pay_ranges.json"))
    assert (info.min, info.max, info.currency, info.period) == (46000, 54000, "GBP", "yearly")
    assert info.source == "ats:greenhouse"


def test_greenhouse_html_pay_range_fallback():
    """Without pay_input_ranges the escaped pay-range HTML block is parsed."""
    info = from_greenhouse_job(load("greenhouse_job_html_pay_only.json"))
    assert (info.min, info.max, info.currency, info.period) == (46000, 54000, "GBP", "yearly")


def test_greenhouse_multiple_tiers_use_widest_envelope():
    """Several same-currency tiers collapse into the widest range."""
    job = {"pay_input_ranges": [
        {"min_cents": 10000000, "max_cents": 14000000, "currency_type": "USD", "title": "Tier 1 Annual"},
        {"min_cents": 9000000, "max_cents": 12000000, "currency_type": "USD", "title": "Tier 2 Annual"},
    ]}
    info = from_greenhouse_job(job)
    assert (info.min, info.max) == (90000, 140000)


def test_greenhouse_without_pay_data_is_none():
    """Jobs with no pay information give None."""
    assert from_greenhouse_job({"pay_input_ranges": [], "content": "<p>No pay here</p>"}) is None


def test_lever_salary_range():
    """Lever salaryRange maps interval, currency and bounds."""
    info = from_lever_posting(load("lever_posting_with_salary_range.json"))
    assert (info.min, info.max, info.currency, info.period) == (90000, 120000, "USD", "yearly")
    assert info.source == "ats:lever"


def test_lever_hourly_interval_and_text_fallback():
    """Lever hourly intervals are annualised; text is used when no range exists."""
    hourly = from_lever_posting({"salaryRange": {"min": 40, "max": 50, "currency": "USD", "interval": "per-hour-wage"}})
    assert hourly.period == "hourly" and hourly.annual_max == 104000
    text = from_lever_posting({"salaryDescriptionPlain": "The pay range is $100,000 - $120,000 per year."})
    assert text.min == 100000 and text.source == "ats:lever"
    assert from_lever_posting({"text": "nothing"}) is None


def test_ashby_compensation_components():
    """Ashby Salary components are read; bonus/equity components are ignored."""
    info = from_ashby_job(load("ashby_job_with_compensation.json"))
    assert info.source == "ats:ashby"
    assert info.min is not None and info.max >= info.min
    assert info.period == "yearly"


def test_ashby_summary_text_fallback_and_empty():
    """Ashby falls back to the scrapeable summary text, and handles no data."""
    info = from_ashby_job({"compensation": {"scrapeableCompensationSalarySummary": "$150K - $200K"}})
    assert (info.min, info.max, info.currency) == (150000, 200000, "USD")
    assert from_ashby_job({"compensation": None}) is None
    assert from_ashby_job({}) is None


JSONLD_HTML = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Dev",
 "baseSalary":{"@type":"MonetaryAmount","currency":"CAD",
   "value":{"@type":"QuantitativeValue","minValue":45,"maxValue":60,"unitText":"HOUR"}}}
</script></head><body></body></html>
"""


def test_jsonld_base_salary_hourly():
    """schema.org baseSalary with HOUR unit yields hourly values and CAD."""
    info = from_jsonld_html(JSONLD_HTML)
    assert (info.min, info.max, info.currency, info.period) == (45, 60, "CAD", "hourly")
    assert info.annual_max == 124800
    assert info.source == "jsonld"


def test_jsonld_graph_single_value_and_invalid_json():
    """@graph wrappers and single values work; malformed JSON is ignored."""
    html = ('<script type="application/ld+json">{"@graph":[{"@type":"JobPosting","baseSalary":'
            '{"currency":"USD","value":{"value":130000,"unitText":"YEAR"}}}]}</script>')
    info = from_jsonld_html(html)
    assert info.min == info.max == 130000
    assert from_jsonld_html('<script type="application/ld+json">{bad json</script>') is None
    assert from_jsonld_html("<html></html>") is None
    assert from_jsonld_html(None) is None


def test_description_pay_sentence_requires_pay_context():
    """Only figures near salary/pay wording are used from descriptions."""
    good = "We raised $50 million. The base salary range is $140,000 - $170,000 USD per year, plus equity."
    info = from_description_text(good)
    assert (info.min, info.max, info.source) == (140000, 170000, "description_text")
    assert from_description_text("We raised $200,000,000 in funding and offer free lunch.") is None
    assert from_description_text(None) is None


def test_extract_best_salary_prefers_jsonld():
    """JSON-LD wins over text sources."""
    info = extract_best_salary(JSONLD_HTML, "Salary $1,000,000 per year", "$10/hr")
    assert info.source == "jsonld"
    assert extract_best_salary(None, None, "Competitive Salary") is None


def test_html_to_text_handles_double_escaped_html():
    """Greenhouse-style double escaped HTML is flattened to text."""
    assert html_to_text("&lt;p&gt;Hello&amp;nbsp;&lt;b&gt;World&lt;/b&gt;&lt;/p&gt;") == "Hello World"


def test_store_helpers():
    """Column and API helpers expose consistent values and USD approximations."""
    info = from_lever_posting(load("lever_posting_with_salary_range.json"))
    cols = salary_columns_from_info(info)
    assert cols["salary_annual_max"] == 120000 and cols["salary_source"] == "ats:lever"
    assert all(v is None for v in salary_columns_from_info(None).values())

    class Row:
        """Minimal stand-in for a JobPosting row."""

        salary_currency = "CAD"
        salary_annual_min = 100000.0
        salary_annual_max = 120000.0

    api = salary_api_fields(Row())
    assert api["salary_annual_max_usd_approx"] == 87600.0
    assert api["salary_min"] is None
    assert set(salary_api_fields(object())) == set(api)


def test_ats_normalizers_and_text_formatting():
    """Normalised job dicts carry salary_info and a readable salary string."""
    gh = normalize_greenhouse_job(load("greenhouse_job_with_pay_ranges.json"), "airbnb")
    assert gh["salary_info"].currency == "GBP" and "46,000 - 54,000 GBP" in gh["salary"]
    lv = normalize_lever_job(load("lever_posting_with_salary_range.json"), "weride")
    assert lv["company"] == "weride" and lv["salary_info"].max == 120000
    ab = normalize_ashby_job(load("ashby_job_with_compensation.json"), "ashby")
    assert ab["salary_info"] is not None
    assert _format_salary_text(None) == "Competitive Salary"


def test_ats_ingest_helpers():
    """Board parsing, hub mapping and keyword filtering behave as expected."""
    assert parse_ats_boards("greenhouse:airbnb, lever:weride,bogus:x,nocolon") == [("greenhouse", "airbnb"), ("lever", "weride")]
    assert parse_ats_boards(None) == []
    assert map_location_to_hub("Seattle, Washington, United States") == "Seattle, WA"
    assert map_location_to_hub("Remote - Berlin") is None
    assert matches_keyword({"title": "Senior Software Engineer", "description": ""}, "Software Engineer")
    assert not matches_keyword({"title": "Designer", "description": ""}, "Software Engineer")
