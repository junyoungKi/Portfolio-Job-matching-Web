"""Author: Joonyoung Ki

Purpose: Pure (I/O free) salary parsing and normalisation helpers.

This module turns free-text salary expressions such as
"$120,000 - $150,000 a year", "$45/hr" or "120k-150k" into a structured
``SalaryInfo`` value (min / max / currency / period) and normalises every
value to an annual amount so postings can be compared and sorted. It also
offers a rough USD conversion for cross-currency sorting. Nothing here
touches the network or the database, which keeps it trivially unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

PERIOD_HOURLY = "hourly"
PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_BIWEEKLY = "biweekly"
PERIOD_MONTHLY = "monthly"
PERIOD_YEARLY = "yearly"

# Multipliers that turn one pay period into a full year of full-time work.
ANNUAL_FACTORS = {
    PERIOD_HOURLY: 2080.0,
    PERIOD_DAILY: 260.0,
    PERIOD_WEEKLY: 52.0,
    PERIOD_BIWEEKLY: 26.0,
    PERIOD_MONTHLY: 12.0,
    PERIOD_YEARLY: 1.0,
}

# Plausible annual bounds (any currency) used to reject numbers that are
# obviously not salaries, such as headcounts or funding amounts.
MIN_PLAUSIBLE_ANNUAL = 8_000.0
MAX_PLAUSIBLE_ANNUAL = 3_000_000.0

# Approximate, static FX rates (units of USD per 1 unit of currency). They are
# only meant for coarse cross-currency sorting, never for display or payroll.
APPROX_USD_RATES = {
    "USD": 1.0,
    "CAD": 0.73,
    "EUR": 1.08,
    "GBP": 1.27,
    "AUD": 0.66,
    "CHF": 1.12,
    "SGD": 0.74,
    "INR": 0.012,
    "JPY": 0.0067,
}

_SYMBOL_CURRENCY = {
    "US$": "USD",
    "CA$": "CAD",
    "C$": "CAD",
    "CAD$": "CAD",
    "A$": "AUD",
    "AU$": "AUD",
    "S$": "SGD",
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
}
_CODES = ("USD", "CAD", "EUR", "GBP", "AUD", "CHF", "SGD", "INR", "JPY")

_CUR_PREFIX = r"(?:CAD\$|US\$|CA\$|AU\$|C\$|A\$|S\$|USD|CAD|EUR|GBP|AUD|CHF|SGD|INR|JPY|\$|£|€)"
_NUMBER = r"(?:\d{1,3}(?:[,.]\d{3})+(?!\d)|\d+(?:\.\d+)?)"
_SEP = r"(?:\s*(?:-|–|—|―|to|and)\s*)"

_AMOUNT_RE = re.compile(
    rf"(?P<cur>{_CUR_PREFIX})?\s?(?P<num>{_NUMBER})\s?(?P<suf>[kK](?![a-zA-Z]))?",
)
_RANGE_RE = re.compile(
    rf"(?P<c1>{_CUR_PREFIX})?\s?(?P<n1>{_NUMBER})\s?(?P<s1>[kK](?![a-zA-Z]))?"
    rf"{_SEP}"
    rf"(?P<c2>{_CUR_PREFIX})?\s?(?P<n2>{_NUMBER})\s?(?P<s2>[kK](?![a-zA-Z]))?",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    rf"(?P<pre>up\s+to|from|starting\s+(?:at|from)|at\s+least|min(?:imum)?(?:\s+of)?|max(?:imum)?(?:\s+of)?)?\s*"
    rf"(?P<c1>{_CUR_PREFIX})\s?(?P<n1>{_NUMBER})\s?(?P<s1>[kK](?![a-zA-Z]))?",
    re.IGNORECASE,
)
_SINGLE_BARE_PERIOD_RE = re.compile(
    rf"(?P<n1>{_NUMBER})\s?(?P<s1>[kK](?![a-zA-Z]))?\s*(?=/|per\s|an?\s+(?:hour|year)|hourly|annually|yearly)",
    re.IGNORECASE,
)

_PERIOD_PATTERNS = [
    (PERIOD_HOURLY, re.compile(r"(?:/\s?(?:hr|hour|h)\b|\bper\s+hour\b|\ban?\s+hour\b|\bhourly\b|\bph\b|\bp\.h\.|\bhr\b)", re.I)),
    (PERIOD_BIWEEKLY, re.compile(r"(?:bi-?weekly|every\s+two\s+weeks|\bper\s+pay\s+period\b)", re.I)),
    (PERIOD_WEEKLY, re.compile(r"(?:/\s?(?:wk|week)\b|\bper\s+week\b|\ba\s+week\b|\bweekly\b)", re.I)),
    (PERIOD_DAILY, re.compile(r"(?:/\s?day\b|\bper\s+day\b|\ba\s+day\b|\bdaily\b|\bper\s+diem\b)", re.I)),
    (PERIOD_MONTHLY, re.compile(r"(?:/\s?(?:mo|month)\b|\bper\s+month\b|\ba\s+month\b|\bmonthly\b|\bp\.m\.)", re.I)),
    (PERIOD_YEARLY, re.compile(r"(?:/\s?(?:yr|year)\b|\bper\s+(?:year|annum)\b|\ban?\s+year\b|\byearly\b|\bannual(?:ly)?\b|\bp\.a\.|\bper\s+yr\b|\bpa\b|\byr\b)", re.I)),
]

_MAGNITUDE_AFTER_RE = re.compile(r"^\s*(?:million|billion|mm\b|bn\b|m\b|b\b|%|\+?\s*(?:employees|users|customers))", re.I)
_CODE_AFTER_RE = re.compile(rf"^\s*\(?\s*(?P<code>{'|'.join(_CODES)})\b", re.I)
_CODE_BEFORE_RE = re.compile(rf"(?P<code>{'|'.join(_CODES)})\s*$", re.I)
_PERIOD_WINDOW = 40


@dataclass(frozen=True)
class SalaryInfo:
    """Structured salary range with its provenance and annualised values."""

    min: Optional[float]
    max: Optional[float]
    currency: Optional[str]
    period: Optional[str]
    annual_min: Optional[float]
    annual_max: Optional[float]
    source: Optional[str] = None
    raw_text: Optional[str] = None

    def with_source(self, source: str, raw_text: Optional[str] = None) -> "SalaryInfo":
        """Return a copy that records where the value came from."""
        return SalaryInfo(
            self.min, self.max, self.currency, self.period,
            self.annual_min, self.annual_max, source,
            raw_text if raw_text is not None else self.raw_text,
        )


def annualize(amount: Optional[float], period: Optional[str]) -> Optional[float]:
    """Convert an amount for the given pay period into a yearly amount.

    Returns ``None`` when the amount or the period is unknown.
    """
    if amount is None or period not in ANNUAL_FACTORS:
        return None
    return round(amount * ANNUAL_FACTORS[period], 2)


def normalize_period(value: Optional[str]) -> Optional[str]:
    """Map vendor-specific interval labels onto our canonical period names.

    Handles values such as ``per-year-salary`` (Lever), ``1 YEAR`` (Ashby),
    ``YEAR`` / ``HOUR`` (schema.org) and ``annual``.
    """
    if not value:
        return None
    v = str(value).strip().lower().replace("_", "-")
    if "bi-week" in v or "biweek" in v:
        return PERIOD_BIWEEKLY
    if "hour" in v:
        return PERIOD_HOURLY
    if "day" in v:
        return PERIOD_DAILY
    if "week" in v:
        return PERIOD_WEEKLY
    if "month" in v:
        return PERIOD_MONTHLY
    if "year" in v or "annual" in v or v in {"yr", "pa"}:
        return PERIOD_YEARLY
    return None


def normalize_currency(value: Optional[str]) -> Optional[str]:
    """Return an upper-case ISO 4217 code for a symbol or code, else ``None``."""
    if not value:
        return None
    v = str(value).strip()
    if v in _SYMBOL_CURRENCY:
        return _SYMBOL_CURRENCY[v]
    if v.upper() in _SYMBOL_CURRENCY:
        return _SYMBOL_CURRENCY[v.upper()]
    up = v.upper()
    if len(up) == 3 and up.isalpha():
        return up
    return None


def to_usd_approx(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    """Convert an amount to USD using the static approximate rate table.

    Unknown currencies return ``None`` rather than guessing.
    """
    if amount is None:
        return None
    rate = APPROX_USD_RATES.get((currency or "").upper())
    if rate is None:
        return None
    return round(amount * rate, 2)


def build_salary_info(
    min_value: Optional[float],
    max_value: Optional[float],
    currency: Optional[str],
    period: Optional[str],
    source: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> Optional[SalaryInfo]:
    """Build a validated ``SalaryInfo`` from already structured values.

    Swaps reversed bounds, normalises currency/period labels and returns
    ``None`` when no amount is present or the annualised value is implausible.
    """
    if min_value is None and max_value is None:
        return None
    lo = float(min_value) if min_value is not None else None
    hi = float(max_value) if max_value is not None else None
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    if lo is not None and lo <= 0:
        lo = None
    if hi is not None and hi <= 0:
        hi = None
    if lo is None and hi is None:
        return None
    period = normalize_period(period) if period not in ANNUAL_FACTORS else period
    cur = normalize_currency(currency)
    a_lo, a_hi = annualize(lo, period), annualize(hi, period)
    if period is not None:
        probe = a_hi if a_hi is not None else a_lo
        if probe is None or not (MIN_PLAUSIBLE_ANNUAL <= probe <= MAX_PLAUSIBLE_ANNUAL):
            return None
        if a_lo is not None and a_lo < MIN_PLAUSIBLE_ANNUAL * 0.5:
            return None
    return SalaryInfo(lo, hi, cur, period, a_lo, a_hi, source, raw_text)


def _to_number(num: str, suffix: Optional[str]) -> Optional[float]:
    """Convert a matched numeric token (with optional ``k`` suffix) to a float."""
    token = num
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", token):
        token = re.sub(r"[,.]", "", token)
    else:
        token = token.replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return None
    if suffix:
        value *= 1000.0
    return value


def _detect_period(window: str) -> Optional[str]:
    """Find the earliest pay-period phrase inside a short text window."""
    best: tuple[int, str] | None = None
    for name, pattern in _PERIOD_PATTERNS:
        m = pattern.search(window)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def _infer_period(hi: Optional[float], lo: Optional[float]) -> Optional[str]:
    """Guess the period for an amount with no explicit period phrase.

    Only one confident case is inferred: amounts of 20,000 or more are treated
    as yearly. Smaller bare numbers could be hourly, monthly or prices, so they
    stay unknown (and are rejected) instead of being guessed.
    """
    probe = hi if hi is not None else lo
    if probe is not None and probe >= 20_000:
        return PERIOD_YEARLY
    return None


def _currency_around(text: str, start: int, end: int, c1: Optional[str], c2: Optional[str]) -> Optional[str]:
    """Resolve the currency from prefixes, or an ISO code before/after the match."""
    for c in (c1, c2):
        cur = normalize_currency(c)
        if cur:
            if c in ("$",) or (c or "").upper() == "$":
                after = _CODE_AFTER_RE.match(text[end:end + 12])
                before = _CODE_BEFORE_RE.search(text[max(0, start - 8):start])
                for hit in (after, before):
                    if hit:
                        return hit.group("code").upper()
            return cur
    after = _CODE_AFTER_RE.match(text[end:end + 12])
    if after:
        return after.group("code").upper()
    before = _CODE_BEFORE_RE.search(text[max(0, start - 8):start])
    if before:
        return before.group("code").upper()
    return None


def _make_info(
    lo: Optional[float], hi: Optional[float], currency: Optional[str],
    period: Optional[str], default_currency: Optional[str], raw: str,
) -> Optional[SalaryInfo]:
    """Finalise a candidate: default currency, infer period, validate."""
    if period is None:
        period = _infer_period(hi if hi is not None else lo, lo)
    if period is None:
        probe = hi if hi is not None else lo
        if probe is None or probe < MIN_PLAUSIBLE_ANNUAL:
            return None
        return build_salary_info(lo, hi, currency or default_currency, None, raw_text=raw)
    return build_salary_info(lo, hi, currency or default_currency, period, raw_text=raw)


def _candidates(text: str):
    """Yield ``(start, end, lo, hi, currency, None)`` salary candidates.

    Ranges are tried first; single amounts only count when they carry a
    currency marker or a pay-period phrase, which avoids matching stray numbers.
    """
    used: list[tuple[int, int]] = []
    for m in _RANGE_RE.finditer(text):
        s1, s2 = m.group("s1"), m.group("s2")
        n1 = _to_number(m.group("n1"), s1)
        n2 = _to_number(m.group("n2"), s2)
        if n1 is None or n2 is None:
            continue
        if s2 and not s1 and n1 < 1000 <= n2:
            n1 *= 1000.0
        end = m.end()
        if _MAGNITUDE_AFTER_RE.match(text[end:end + 14]):
            continue
        if text[max(0, m.start() - 1):m.start()].isalnum():
            continue
        symbol = m.group("c1") or m.group("c2")
        has_code = bool(_CODE_AFTER_RE.match(text[end:end + 12]) or _CODE_BEFORE_RE.search(text[max(0, m.start() - 8):m.start()]))
        window = text[end:end + _PERIOD_WINDOW]
        has_period = _detect_period(window) is not None
        both_k = bool(s1 and s2)
        if not (symbol or has_code or has_period or both_k):
            continue
        used.append((m.start(), end))
        yield m.start(), end, min(n1, n2), max(n1, n2), _currency_around(text, m.start(), end, m.group("c1"), m.group("c2")), None
    for m in _SINGLE_RE.finditer(text):
        if any(a <= m.start("c1") < b for a, b in used):
            continue
        n = _to_number(m.group("n1"), m.group("s1"))
        if n is None:
            continue
        end = m.end()
        if _MAGNITUDE_AFTER_RE.match(text[end:end + 14]):
            continue
        pre = (m.group("pre") or "").lower().strip()
        lo = hi = n
        if pre.startswith(("up to", "max")):
            lo = None
        elif pre.startswith(("from", "starting", "at least", "min")):
            hi = None
        used.append((m.start(), end))
        yield m.start(), end, lo, hi, _currency_around(text, m.start(), end, m.group("c1"), None), None
    for m in _SINGLE_BARE_PERIOD_RE.finditer(text):
        if any(a <= m.start() < b for a, b in used):
            continue
        if text[max(0, m.start() - 1):m.start()].isalnum():
            continue
        n = _to_number(m.group("n1"), m.group("s1"))
        if n is None:
            continue
        yield m.start(), m.end(), n, n, None, None


def parse_salary_text(text: Optional[str], default_currency: Optional[str] = None) -> Optional[SalaryInfo]:
    """Parse the first plausible salary expression found in ``text``.

    Supports ranges ("$120,000 - $150,000 a year", "120k-150k"), single values
    ("$45/hr"), open-ended bounds ("up to $150k"), ISO codes and common
    symbols, and period words (hour/day/week/month/year). Returns ``None`` for
    non-salary text such as "Competitive Salary", empty input or "401k".

    ``default_currency`` is applied when the text shows no currency marker.
    """
    if not text or not isinstance(text, str):
        return None
    cleaned = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
    cleaned = re.sub(r"\b401\s?\(?k\)?", " ", cleaned, flags=re.I)
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    found = sorted(_candidates(cleaned), key=lambda c: c[0])
    for start, end, lo, hi, currency, _ in found:
        window = cleaned[end:end + _PERIOD_WINDOW]
        period = _detect_period(window)
        if period is None:
            period = _detect_period(cleaned[max(0, start - 20):start])
        raw = cleaned[start:end + (len(window) if period else 0)].strip()
        info = _make_info(lo, hi, currency, period, default_currency, raw[:200])
        if info is not None:
            return info
    return None
