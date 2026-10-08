"""Author: Joonyoung Ki

Purpose: Polite HTTP client for public applicant-tracking-system (ATS) job
board APIs (Greenhouse, Lever, Ashby) that publish structured pay ranges.

Compliance behaviour: every request identifies the crawler via User-Agent,
honours the host's robots.txt (via ``urllib.robotparser``), and is rate limited
per host (at least one second between calls, matching Lever's published
``Crawl-delay: 1``). Only documented public JSON endpoints are used; there is
no HTML scraping and no login.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any, Optional

from .salary_parser import SalaryInfo
from .salary_sources import (
    from_ashby_job,
    from_greenhouse_job,
    from_lever_posting,
    html_to_text,
)

logger = logging.getLogger(__name__)

USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "PortfolioJobMatchingBot/1.0 (+https://github.com/junyoungKi/Portfolio-Job-matching-Web)",
)
MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("ATS_MIN_INTERVAL_SECONDS", "1.0"))
REQUEST_TIMEOUT_SECONDS = 30

_robots_cache: dict = {}
_last_request_at: dict = {}
_host_locks: dict = {}


def _fetch_robots(origin: str) -> urllib.robotparser.RobotFileParser:
    """Download and parse robots.txt for an origin (cached per process).

    Per RFC 9309, a 4xx response means "no restrictions"; network errors or
    5xx responses make us assume everything is disallowed (fail closed).
    """
    parser = urllib.robotparser.RobotFileParser()
    request = urllib.request.Request(f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            parser.parse(resp.read().decode("utf-8", "replace").splitlines())
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500:
            parser.parse([])
        else:
            parser.parse(["User-agent: *", "Disallow: /"])
    except Exception:  # noqa: BLE001 - fail closed on any network problem
        parser.parse(["User-agent: *", "Disallow: /"])
    return parser


def is_allowed_by_robots(url: str) -> bool:
    """Return True when the URL may be fetched according to robots.txt."""
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _robots_cache:
        _robots_cache[origin] = _fetch_robots(origin)
    return _robots_cache[origin].can_fetch(USER_AGENT, url)


def _blocking_get_json(url: str) -> Any:
    """Perform a blocking GET and decode the JSON body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def polite_get_json(url: str) -> Optional[Any]:
    """Fetch JSON with robots.txt checks and per-host rate limiting.

    Returns ``None`` (and logs) when blocked by robots.txt or on any error, so
    one failing board never aborts a whole crawl.
    """
    host = urllib.parse.urlsplit(url).netloc
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        allowed = await asyncio.to_thread(is_allowed_by_robots, url)
        if not allowed:
            logger.warning("Skipping %s: disallowed by robots.txt", url)
            return None
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at.get(host, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await asyncio.to_thread(_blocking_get_json, url)
        except Exception as exc:  # noqa: BLE001 - isolate per-board failures
            logger.warning("Fetch failed for %s: %s", url, exc)
            return None
        finally:
            _last_request_at[host] = time.monotonic()


def _format_salary_text(info: Optional[SalaryInfo]) -> str:
    """Render a short human-readable salary string for the legacy text column."""
    if info is None:
        return "Competitive Salary"
    lo = f"{info.min:,.0f}" if info.min is not None else ""
    hi = f"{info.max:,.0f}" if info.max is not None else ""
    amount = lo if lo == hi or not hi else (f"{lo} - {hi}" if lo else f"up to {hi}")
    parts = [amount, info.currency or "", f"/ {info.period}" if info.period else ""]
    return " ".join(p for p in parts if p).strip()


def normalize_greenhouse_job(job: dict, board: str) -> dict:
    """Convert a Greenhouse API job into the collector's job dict shape."""
    info = from_greenhouse_job(job)
    location = job.get("location") or {}
    return {
        "title": job.get("title") or "",
        "company": job.get("company_name") or board,
        "description": html_to_text(job.get("content")),
        "location": location.get("name") if isinstance(location, dict) else str(location or ""),
        "url": job.get("absolute_url"),
        "salary": _format_salary_text(info),
        "salary_info": info,
    }


def normalize_lever_job(posting: dict, site: str) -> dict:
    """Convert a Lever API posting into the collector's job dict shape."""
    info = from_lever_posting(posting)
    categories = posting.get("categories") or {}
    return {
        "title": posting.get("text") or "",
        "company": site,
        "description": posting.get("descriptionPlain") or html_to_text(posting.get("description")),
        "location": categories.get("location") or "",
        "url": posting.get("hostedUrl"),
        "salary": _format_salary_text(info),
        "salary_info": info,
    }


def normalize_ashby_job(job: dict, board: str) -> dict:
    """Convert an Ashby API job into the collector's job dict shape."""
    info = from_ashby_job(job)
    return {
        "title": job.get("title") or "",
        "company": board,
        "description": job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml")),
        "location": job.get("location") or "",
        "url": job.get("jobUrl"),
        "salary": _format_salary_text(info),
        "salary_info": info,
    }


async def fetch_ats_jobs(provider: str, board: str) -> list:
    """Fetch and normalise all open jobs for one ATS board.

    ``provider`` is ``greenhouse``, ``lever`` or ``ashby``; ``board`` is the
    company's board token / site name. Returns an empty list on failure.
    """
    quoted = urllib.parse.quote(board, safe="")
    if provider == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{quoted}/jobs?content=true&pay_transparency=true"
        data = await polite_get_json(url)
        return [normalize_greenhouse_job(j, board) for j in (data or {}).get("jobs", [])]
    if provider == "lever":
        data = await polite_get_json(f"https://api.lever.co/v0/postings/{quoted}?mode=json")
        return [normalize_lever_job(p, board) for p in (data if isinstance(data, list) else [])]
    if provider == "ashby":
        url = f"https://api.ashbyhq.com/posting-api/job-board/{quoted}?includeCompensation=true"
        data = await polite_get_json(url)
        return [normalize_ashby_job(j, board) for j in (data or {}).get("jobs", []) if j.get("isListed", True)]
    logger.warning("Unknown ATS provider %r", provider)
    return []
