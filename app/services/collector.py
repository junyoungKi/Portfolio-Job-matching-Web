# app/services/collector.py
"""
Author: Joonyoung Ki

LinkedIn job collector.

Uses Playwright (headless Chromium) to scrape public LinkedIn job search results and detail pages
for a keyword and city. Randomised delays and block detection are used to behave like a normal user
and to stop gracefully when LinkedIn redirects to a login or checkpoint page.
"""
import asyncio
import random
from playwright.async_api import async_playwright

class JobCollector:
    """Scrapes job postings from LinkedIn for the North American hub cities."""

    def __init__(self):
        """Define ``NA_HUBS``, the list of cities that "North America" expands to."""
        self.NA_HUBS = [
            "Vancouver, BC", "Toronto, ON", "Seattle, WA", 
            "San Francisco, CA", "Austin, TX", "New York, NY",
            "Los Angeles, CA", "Montreal, QC"
        ]

    async def scrape_linkedin(self, keyword: str, location: str, max_pages: int = 1):
        """Collect postings for ``keyword`` in ``location``.

        Each result page holds 25 cards. For every card the detail page is opened to read the full
        description. Returns a list of dicts with title, company, description, location, salary
        and url. A failure on one page stops the pagination, and a failure on one detail page
        only skips that posting.
        """
        jobs = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True) # For a portfolio project, occasionally set this to False to debug visually
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            for current_page in range(max_pages):
                start_index = current_page * 25
                page = await context.new_page()
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}&f_TPR=r604800&start={start_index}"
                
                try:
                    # 1. Wait more robustly for the search page to load
                    await page.goto(search_url, wait_until="load", timeout=60000)
                    await page.wait_for_selector(".base-card", timeout=15000)
                    
                    # Scroll down slowly to load more postings
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 500)")
                        await asyncio.sleep(random.uniform(0.5, 1.0))

                    raw_cards = await page.query_selector_all(".base-card")
                    job_targets = []
                    for card in raw_cards:
                        try:
                            title_el = await card.query_selector(".base-search-card__title")
                            company_el = await card.query_selector(".base-search-card__subtitle")
                            link_el = await card.query_selector(".base-card__full-link")
                            if title_el and company_el and link_el:
                                job_targets.append({
                                    "title": (await title_el.inner_text()).strip(),
                                    "company": (await company_el.inner_text()).strip(),
                                    "url": await link_el.get_attribute("href")
                                })
                        except: continue

                    await page.close()

                    # Loop that collects each detail page
                    for target in job_targets:
                        if any(j.get('url') == target['url'] for j in jobs): continue
                        
                        # 2. Add a random delay between requests (to look like a human)
                        await asyncio.sleep(random.uniform(2.0, 4.0)) 
                        
                        detail_page = await context.new_page()
                        try:
                            print(f"Collecting details: {target['title']} @ {target['company']}")
                            
                            # 3. Navigate to the detail page and check for redirects
                            response = await detail_page.goto(target['url'], wait_until="load", timeout=30000)
                            
                            # Check whether we were bounced to a login or security checkpoint page
                            current_url = detail_page.url
                            if "login" in current_url or "checkpoint" in current_url:
                                print(f"Block detected (redirected to a login page): {target['title']}")
                                await detail_page.close()
                                continue

                            # 4. Wait persistently when extracting elements (using a Locator is recommended)
                            # Wait up to 10 seconds for the description element to appear
                            desc_selector = ".description__text, .show-more-less-html__markup"
                            try:
                                await detail_page.wait_for_selector(desc_selector, timeout=10000)
                                desc_el = await detail_page.query_selector(desc_selector)
                                description = (await desc_el.inner_text()).strip() if desc_el else ""
                            except:
                                description = f"Unable to load the job details for {target['title']}."

                            jobs.append({
                                "title": target['title'],
                                "company": target['company'],
                                "description": description,
                                "location": location,
                                "salary": "Competitive Salary",
                                "url": target['url']
                            })
                        except Exception as e:
                            # 5. Make the error messages more specific
                            if "destroyed" in str(e):
                                print(f"Execution context destroyed (suspected redirect): {target['title']}")
                            else:
                                print(f"Detail page failed: {e}")
                        finally:
                            await detail_page.close()
                            
                except Exception as e:
                    print(f"Collection failed for {location}: {e}")
                    await page.close()
                    break

            await browser.close()
        return jobs
    
# This line is required so that main.py can import the collector instance.
job_collector = JobCollector()