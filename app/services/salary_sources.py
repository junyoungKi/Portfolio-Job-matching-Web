"""Author: Joonyoung Ki

Purpose: Pure extractors that turn structured payloads from public job sources
into ``SalaryInfo`` values.

Supported inputs (all already-fetched data, no network access here):
  * Greenhouse Job Board API jobs (``pay_input_ranges`` and ``pay-range`` HTML)
  * Lever Postings API postings (``salaryRange`` / ``salaryDescriptionPlain``)
  * Ashby Job Board API jobs (``compensation`` summary components)
  * schema.org ``JobPosting`` JSON-LD (``baseSalary``) embedded in HTML
  * Free-text pay-range sentences inside a job description

Structured fields are always preferred over text parsing.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Iterable, Optional

from .salary_parser import (
    PERIOD_YEARLY,
    SalaryInfo,
    build_salary_info,
    normalize_currency,
    normalize_period,
    parse_salary_text,
)

SOURCE_GREENHOUSE = "ats:greenhouse"
SOURCE_LEVER = "ats:lever"
SOURCE_ASHBY = "ats:ashby"
SOURCE_JSONLD = "jsonld"
SOURCE_DESCRIPTION = "description_text"
SOURCE_SALARY_TEXT = "salary_text"

_TAG_RE = re.compile(r"<[^>]+>")
_JSONLD_RE = re.compile(
    r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def html_to_text(raw: Optional[str]) -> str:
    """Convert (possibly entity-escaped) HTML into whitespace-normalised text."""
    if not raw:
        return ""
    text = html_lib.unescape(raw)
    if "&lt;" in text or "&gt;" in text:
        text = html_lib.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _as_float(value: Any) -> Optional[float]:
    """Convert numbers or numeric strings to float, otherwise ``None``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def combine_ranges(infos: Iterable[SalaryInfo]) -> Optional[SalaryInfo]:
    """Merge several tiered ranges into one envelope.

    Greenhouse and Ashby may publish one range per location tier. When all
    ranges share a currency and period we return the widest envelope; otherwise
    the first USD range (or simply the first) is used.
    """
    items = [i for i in infos if i is not None]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    same = len({(i.currency, i.period) for i in items}) == 1
    if not same:
        usd = [i for i in items if i.currency == "USD"]
        return (usd or items)[0]
    lows = [i.min for i in items if i.min is not None]
    highs = [i.max for i in items if i.max is not None]
    first = items[0]
    return build_salary_info(
        min(lows) if lows else None,
        max(highs) if highs else None,
        first.currency,
        first.period,
        source=first.source,
        raw_text=first.raw_text,
    )


def from_greenhouse_job(job: dict) -> Optional[SalaryInfo]:
    """Extract salary from a Greenhouse Job Board API job object.

    Uses ``pay_input_ranges`` (amounts are in cents, always annual unless the
    title says otherwise) and falls back to the ``pay-range`` HTML block that
    Greenhouse renders inside the job ``content``.
    """
    infos = []
    for rng in job.get("pay_input_ranges") or []:
        lo = _as_float(rng.get("min_cents"))
        hi = _as_float(rng.get("max_cents"))
        title = str(rng.get("title") or "")
        period = normalize_period(title) or PERIOD_YEARLY
        if re.search(r"hour", title, re.I):
            period = "hourly"
        info = build_salary_info(
            lo / 100 if lo is not None else None,
            hi / 100 if hi is not None else None,
            rng.get("currency_type"),
            period,
            source=SOURCE_GREENHOUSE,
            raw_text=title or None,
        )
        if info:
            infos.append(info)
    combined = combine_ranges(infos)
    if combined:
        return combined
    content = job.get("content") or ""
    if "pay-range" in html_lib.unescape(content):
        text = html_to_text(content)
        match = re.search(r"([^.]{0,60}\bPay Range\b\s*.{0,80})", text, re.I)
        parsed = parse_salary_text(match.group(1) if match else text)
        if parsed:
            return parsed.with_source(SOURCE_GREENHOUSE)
    return None


def from_lever_posting(posting: dict) -> Optional[SalaryInfo]:
    """Extract salary from a Lever Postings API posting object.

    Uses ``salaryRange`` ({min, max, currency, interval}) when present and
    otherwise parses ``salaryDescriptionPlain``.
    """
    rng = posting.get("salaryRange")
    if isinstance(rng, dict):
        info = build_salary_info(
            _as_float(rng.get("min")),
            _as_float(rng.get("max")),
            rng.get("currency"),
            normalize_period(rng.get("interval")) or PERIOD_YEARLY,
            source=SOURCE_LEVER,
            raw_text=str(rng.get("interval") or "") or None,
        )
        if info:
            return info
    text = posting.get("salaryDescriptionPlain") or html_to_text(posting.get("salaryDescription"))
    parsed = parse_salary_text(text)
    return parsed.with_source(SOURCE_LEVER) if parsed else None


def from_ashby_job(job: dict) -> Optional[SalaryInfo]:
    """Extract salary from an Ashby Job Board API job object.

    Reads ``Salary`` components from ``compensation.compensationTiers`` (one
    range per tier, merged into an envelope) or ``summaryComponents``, and
    falls back to ``scrapeableCompensationSalarySummary`` text.
    """
    comp = job.get("compensation")
    if not isinstance(comp, dict):
        return None

    def component_info(component: dict) -> Optional[SalaryInfo]:
        """Build a SalaryInfo from one Ashby ``Salary`` component."""
        if str(component.get("compensationType")).lower() != "salary":
            return None
        return build_salary_info(
            _as_float(component.get("minValue")),
            _as_float(component.get("maxValue")),
            component.get("currencyCode"),
            normalize_period(component.get("interval")),
            source=SOURCE_ASHBY,
            raw_text=component.get("summary"),
        )

    infos = [
        component_info(c)
        for tier in comp.get("compensationTiers") or []
        for c in tier.get("components") or []
    ]
    combined = combine_ranges(i for i in infos if i)
    if combined:
        return combined
    combined = combine_ranges(
        i for i in (component_info(c) for c in comp.get("summaryComponents") or []) if i
    )
    if combined:
        return combined
    text = comp.get("scrapeableCompensationSalarySummary") or comp.get("compensationTierSummary")
    parsed = parse_salary_text(text)
    return parsed.with_source(SOURCE_ASHBY) if parsed else None


def _iter_jsonld_nodes(payload: Any) -> Iterable[dict]:
    """Walk a JSON-LD payload (lists, ``@graph``) yielding dict nodes."""
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(payload, dict):
        yield payload
        if "@graph" in payload:
            yield from _iter_jsonld_nodes(payload["@graph"])


def from_jsonld_baseSalary(base_salary: Any) -> Optional[SalaryInfo]:
    """Convert a schema.org ``baseSalary`` MonetaryAmount into a SalaryInfo."""
    if isinstance(base_salary, list):
        return combine_ranges(from_jsonld_baseSalary(b) for b in base_salary)
    if not isinstance(base_salary, dict):
        return None
    currency = base_salary.get("currency")
    value = base_salary.get("value")
    if isinstance(value, dict):
        lo = _as_float(value.get("minValue"))
        hi = _as_float(value.get("maxValue"))
        single = _as_float(value.get("value"))
        if lo is None and hi is None:
            lo = hi = single
        period = normalize_period(value.get("unitText"))
        currency = currency or value.get("currency")
    else:
        lo = hi = _as_float(value)
        period = normalize_period(base_salary.get("unitText"))
    if period is None and lo is not None and (hi or lo) >= 20_000:
        period = PERIOD_YEARLY
    return build_salary_info(lo, hi, currency, period, source=SOURCE_JSONLD)


def from_jsonld_html(page_html: Optional[str]) -> Optional[SalaryInfo]:
    """Find a ``JobPosting`` with ``baseSalary`` in the page's JSON-LD blocks."""
    if not page_html:
        return None
    for block in _JSONLD_RE.findall(page_html):
        try:
            payload = json.loads(html_lib.unescape(block.strip()))
        except (ValueError, TypeError):
            continue
        for node in _iter_jsonld_nodes(payload):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if "JobPosting" in types and node.get("baseSalary"):
                info = from_jsonld_baseSalary(node["baseSalary"])
                if info:
                    return info
    return None


_PAY_CONTEXT_RE = re.compile(
    r"(salary|pay\s+range|compensation|base\s+pay|pay\s+scale|wage|hourly\s+rate|annual\s+rate|OTE)",
    re.IGNORECASE,
)


def from_description_text(description: Optional[str]) -> Optional[SalaryInfo]:
    """Find a pay-range sentence inside a job description.

    Only sentences that mention salary/pay/compensation are examined, so
    unrelated figures (funding, headcount, perks) are ignored.
    """
    text = html_to_text(description) if description and "<" in description else (description or "")
    if not text:
        return None
    for match in _PAY_CONTEXT_RE.finditer(text):
        window = text[max(0, match.start() - 60): match.end() + 260]
        info = parse_salary_text(window)
        if info and info.currency:
            return info.with_source(SOURCE_DESCRIPTION)
    return None


def from_salary_text(salary: Optional[str]) -> Optional[SalaryInfo]:
    """Parse the legacy free-text ``salary`` column value."""
    info = parse_salary_text(salary)
    return info.with_source(SOURCE_SALARY_TEXT, raw_text=salary) if info else None


def extract_best_salary(
    page_html: Optional[str] = None,
    description: Optional[str] = None,
    salary_text: Optional[str] = None,
) -> Optional[SalaryInfo]:
    """Return the best salary from a crawled page, preferring structured data.

    Order: JSON-LD ``baseSalary`` -> explicit salary text -> description pay
    sentences.
    """
    return (
        from_jsonld_html(page_html)
        or from_salary_text(salary_text)
        or from_description_text(description)
    )


__all__ = [
    "SOURCE_GREENHOUSE", "SOURCE_LEVER", "SOURCE_ASHBY", "SOURCE_JSONLD",
    "SOURCE_DESCRIPTION", "SOURCE_SALARY_TEXT", "html_to_text", "combine_ranges",
    "from_greenhouse_job", "from_lever_posting", "from_ashby_job",
    "from_jsonld_baseSalary", "from_jsonld_html", "from_description_text",
    "from_salary_text", "extract_best_salary", "normalize_currency",
]
