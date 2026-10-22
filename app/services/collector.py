# app/services/collector.py
"""
Author: Joonyoung Ki

LinkedIn job collector.

Uses Playwright (headless Chromium) to scrape public LinkedIn job search results and detail pages
for a keyword and city. Randomised delays and block detection are used to behave like a normal user
and to stop gracefully when LinkedIn redirects to a login or checkpoint page.

Launch, navigation, and closing the browser all have deadlines. The caller can pass
``on_step`` and is told the step name before each of those awaits. A driver crash
such as ``EPIPE`` is logged and raised so that city ends, and the browser is still
closed from ``finally``.
"""
import asyncio
import os
import random

from playwright.async_api import async_playwright

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _positive_number(name, default, cast):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        print(f"Ignoring invalid {name}={raw!r}; using {default}")
        return default
    if value <= 0:
        print(f"Ignoring non-positive {name}={value}; using {default}")
        return default
    return value


# Action timeout for Playwright calls that do not pass their own. Milliseconds.
DEFAULT_TIMEOUT_MS = _positive_number("PLAYWRIGHT_DEFAULT_TIMEOUT_MS", 30_000, int)
# Search-page navigation. The detail page keeps a shorter explicit timeout below.
NAVIGATION_TIMEOUT_MS = _positive_number("PLAYWRIGHT_NAVIGATION_TIMEOUT_MS", 60_000, int)
CARD_SELECTOR_TIMEOUT_MS = 15_000
DETAIL_NAVIGATION_TIMEOUT_MS = 30_000
DESCRIPTION_TIMEOUT_MS = 10_000
# Chromium launch has no Playwright timeout of its own.
LAUNCH_TIMEOUT_SECONDS = _positive_number("PLAYWRIGHT_LAUNCH_TIMEOUT_SECONDS", 60, float)
# page.close / browser.close / playwright.stop have no Playwright timeout of their own.
CLOSE_TIMEOUT_SECONDS = _positive_number("PLAYWRIGHT_CLOSE_TIMEOUT_SECONDS", 15, float)
_ACTION_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_MS / 1000


class CollectorTimeout(Exception):
    """A Playwright step exceeded its own deadline."""


async def _wait(awaitable, timeout, what):
    """Await ``awaitable`` or raise ``CollectorTimeout``.

    ``TimeoutError`` is reserved for the city and job deadlines in ``app.main``.
    A step timeout must not look like those, or a slow selector would be reported as the
    whole city giving up.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except TimeoutError as exc:
        raise CollectorTimeout(f"{what} exceeded {timeout}s") from exc


def _note(on_step, step):
    if on_step is not None:
        on_step(step)


def _is_driver_crash(exc):
    """True when the Playwright driver pipe or the browser is already gone."""
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("epipe", "target closed", "has been closed", "browser closed")
    )


def _consume_task_exception(task):
    if not task.done() or task.cancelled():
        return
    try:
        exc = task.exception()
    except Exception:
        return
    if exc is not None:
        print(f"Playwright close failed: {exc}")


async def close_playwright_resource(resource, timeout):
    """Close a page, context, browser, or Playwright driver.

    The close runs on its own task so it cannot block the caller past ``timeout``.
    Errors, including a driver ``EPIPE`` while the pipe is going away, are printed.
    """
    if resource is None:
        return
    closer = getattr(resource, "close", None)
    if closer is None:
        closer = getattr(resource, "stop", None)
    if closer is None:
        return
    task = asyncio.create_task(closer())
    task.add_done_callback(_consume_task_exception)
    try:
        done, _pending = await asyncio.wait({task}, timeout=timeout)
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
        raise
    if task not in done:
        task.cancel()
        print(f"Playwright close timed out after {timeout}s")


class JobCollector:
    """Scrapes job postings from LinkedIn for the North American hub cities."""

    def __init__(self):
        """Define ``NA_HUBS``, the list of cities that "North America" expands to."""
        self.NA_HUBS = [
            "Vancouver, BC", "Toronto, ON", "Seattle, WA",
            "San Francisco, CA", "Austin, TX", "New York, NY",
            "Los Angeles, CA", "Montreal, QC"
        ]

    async def scrape_linkedin(self, keyword: str, location: str, max_pages: int = 1, on_step=None):
        """Collect postings for ``keyword`` in ``location``.

        Each result page holds 25 cards. For every card the detail page is opened to read the full
        description. Returns a list of dicts with title, company, description, location, salary
        and url. A failure on one page stops the pagination, and a failure on one detail page
        only skips that posting. A driver crash ends the scrape. The browser is closed in a
        ``finally`` with its own deadline. ``on_step`` is called with a short name before each
        slow await.
        """
        jobs = []
        playwright = None
        browser = None
        context = None
        try:
            _note(on_step, "Playwright start")
            playwright = await _wait(
                async_playwright().start(), LAUNCH_TIMEOUT_SECONDS, "Playwright start"
            )
            # Headless in the server image. Set headless=False only when debugging a local browser.
            _note(on_step, "Chromium launch")
            browser = await _wait(
                playwright.chromium.launch(headless=True),
                LAUNCH_TIMEOUT_SECONDS,
                "Chromium launch",
            )
            _note(on_step, "browser context")
            context = await _wait(
                browser.new_context(user_agent=_USER_AGENT),
                LAUNCH_TIMEOUT_SECONDS,
                "browser context",
            )
            context.set_default_timeout(DEFAULT_TIMEOUT_MS)
            context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
            for current_page in range(max_pages):
                keep_going = await self._collect_search_page(
                    context, keyword, location, current_page, jobs, on_step
                )
                if not keep_going:
                    break
        finally:
            _note(on_step, "closing browser")
            await close_playwright_resource(context, CLOSE_TIMEOUT_SECONDS)
            await close_playwright_resource(browser, CLOSE_TIMEOUT_SECONDS)
            await close_playwright_resource(playwright, CLOSE_TIMEOUT_SECONDS)
        return jobs

    async def _collect_search_page(self, context, keyword, location, current_page, jobs, on_step):
        """Read one search page. Return False when pagination should stop."""
        start_index = current_page * 25
        page = None
        job_targets = []
        try:
            _note(on_step, "search page")
            page = await _wait(context.new_page(), LAUNCH_TIMEOUT_SECONDS, "search page")
            search_url = (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={keyword}&location={location}&f_TPR=r604800&start={start_index}"
            )
            _note(on_step, "search navigation")
            await page.goto(search_url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS)
            _note(on_step, "wait for job cards")
            await page.wait_for_selector(".base-card", timeout=CARD_SELECTOR_TIMEOUT_MS)
            _note(on_step, "scrolling search results")
            for _ in range(3):
                await _wait(
                    page.evaluate("window.scrollBy(0, 500)"),
                    _ACTION_TIMEOUT_SECONDS,
                    "search scroll",
                )
                await asyncio.sleep(random.uniform(0.5, 1.0))
            _note(on_step, "reading cards")
            raw_cards = await _wait(
                page.query_selector_all(".base-card"),
                _ACTION_TIMEOUT_SECONDS,
                "card list",
            )
            for card in raw_cards:
                target = await self._read_card(card)
                if target:
                    job_targets.append(target)
        except Exception as e:
            if _is_driver_crash(e):
                print(f"[BATCH] Playwright driver crashed for {location}: {e}")
                raise
            print(f"Collection failed for {location}: {e}")
            return False
        finally:
            await close_playwright_resource(page, CLOSE_TIMEOUT_SECONDS)

        for target in job_targets:
            if any(j.get("url") == target["url"] for j in jobs):
                continue
            await asyncio.sleep(random.uniform(2.0, 4.0))
            await self._collect_detail(context, target, location, jobs, on_step)
        return True

    async def _read_card(self, card):
        """Return a title/company/url dict, or None when the card cannot be read."""
        try:
            title_el = await _wait(
                card.query_selector(".base-search-card__title"),
                _ACTION_TIMEOUT_SECONDS,
                "title selector",
            )
            company_el = await _wait(
                card.query_selector(".base-search-card__subtitle"),
                _ACTION_TIMEOUT_SECONDS,
                "company selector",
            )
            link_el = await _wait(
                card.query_selector(".base-card__full-link"),
                _ACTION_TIMEOUT_SECONDS,
                "link selector",
            )
            if not (title_el and company_el and link_el):
                return None
            title = await _wait(title_el.inner_text(), _ACTION_TIMEOUT_SECONDS, "title text")
            company = await _wait(
                company_el.inner_text(), _ACTION_TIMEOUT_SECONDS, "company text"
            )
            url = await _wait(link_el.get_attribute("href"), _ACTION_TIMEOUT_SECONDS, "card url")
            return {"title": title.strip(), "company": company.strip(), "url": url}
        except Exception as exc:
            if _is_driver_crash(exc):
                raise
            return None

    async def _collect_detail(self, context, target, location, jobs, on_step):
        """Open one detail page and append the posting. A failure skips only this card.

        A driver crash is raised so the city stops instead of walking the rest of the cards
        against a dead browser.
        """
        detail_page = None
        try:
            _note(on_step, f"detail page {target['title']}")
            detail_page = await _wait(
                context.new_page(), LAUNCH_TIMEOUT_SECONDS, "detail page"
            )
            print(f"Collecting details: {target['title']} @ {target['company']}")
            _note(on_step, f"detail navigation {target['title']}")
            await detail_page.goto(
                target["url"],
                wait_until="load",
                timeout=DETAIL_NAVIGATION_TIMEOUT_MS,
            )
            current_url = detail_page.url
            if "login" in current_url or "checkpoint" in current_url:
                print(f"Block detected (redirected to a login page): {target['title']}")
                return

            desc_selector = ".description__text, .show-more-less-html__markup"
            try:
                _note(on_step, f"description {target['title']}")
                await detail_page.wait_for_selector(desc_selector, timeout=DESCRIPTION_TIMEOUT_MS)
                desc_el = await _wait(
                    detail_page.query_selector(desc_selector),
                    _ACTION_TIMEOUT_SECONDS,
                    "description selector",
                )
                if desc_el:
                    description = await _wait(
                        desc_el.inner_text(), _ACTION_TIMEOUT_SECONDS, "description text"
                    )
                    description = description.strip()
                else:
                    description = ""
            except Exception:
                description = f"Unable to load the job details for {target['title']}."

            jobs.append({
                "title": target["title"],
                "company": target["company"],
                "description": description,
                "location": location,
                "salary": "Competitive Salary",
                "url": target["url"],
            })
        except Exception as e:
            if _is_driver_crash(e):
                print(f"[BATCH] Playwright driver crashed for {location}: {e}")
                raise
            if "destroyed" in str(e):
                print(f"Execution context destroyed (suspected redirect): {target['title']}")
            else:
                print(f"Detail page failed: {e}")
        finally:
            await close_playwright_resource(detail_page, CLOSE_TIMEOUT_SECONDS)


# This line is required so that main.py can import the collector instance.
job_collector = JobCollector()
