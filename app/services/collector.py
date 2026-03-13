# app/services/collector.py 수정본
import asyncio
import random
from playwright.async_api import async_playwright

class JobCollector:
    def __init__(self):
        self.NA_HUBS = [
            "Vancouver, BC", "Toronto, ON", "Seattle, WA", 
            "San Francisco, CA", "Austin, TX", "New York, NY",
            "Los Angeles, CA", "Montreal, QC"
        ]

    async def scrape_linkedin(self, keyword: str, location: str, max_pages: int = 1):
        jobs = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True) # 포트폴리오용이면 가끔 False로 디버깅 추천
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            for current_page in range(max_pages):
                start_index = current_page * 25
                page = await context.new_page()
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}&f_TPR=r604800&start={start_index}"
                
                try:
                    # 1. 페이지 접속 대기 강화
                    await page.goto(search_url, wait_until="load", timeout=60000)
                    await page.wait_for_selector(".base-card", timeout=15000)
                    
                    # 스크롤을 천천히 내려서 더 많은 공고 로드
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

                    # 상세 페이지 수집 루프
                    for target in job_targets:
                        if any(j.get('url') == target['url'] for j in jobs): continue
                        
                        # 2. 수집 간 랜덤 지연 시간 추가 (사람처럼 보이게)
                        await asyncio.sleep(random.uniform(2.0, 4.0)) 
                        
                        detail_page = await context.new_page()
                        try:
                            print(f"🔎 상세 수집 중: {target['title']} @ {target['company']}")
                            
                            # 3. 상세 페이지 이동 및 리다이렉트 체크
                            response = await detail_page.goto(target['url'], wait_until="load", timeout=30000)
                            
                            # 로그인 페이지나 보안 확인 페이지로 튕겼는지 확인
                            current_url = detail_page.url
                            if "login" in current_url or "checkpoint" in current_url:
                                print(f"⚠️ 차단 감지(로그인 창으로 이동됨): {target['title']}")
                                await detail_page.close()
                                continue

                            # 4. 요소 추출 시 끈질기게 대기 (Locator 사용 추천)
                            # description 요소가 보일 때까지 최대 10초 대기
                            desc_selector = ".description__text, .show-more-less-html__markup"
                            try:
                                await detail_page.wait_for_selector(desc_selector, timeout=10000)
                                desc_el = await detail_page.query_selector(desc_selector)
                                description = (await desc_el.inner_text()).strip() if desc_el else ""
                            except:
                                description = f"{target['title']} 공고 상세 내용을 불러올 수 없습니다."

                            jobs.append({
                                "title": target['title'],
                                "company": target['company'],
                                "description": description,
                                "location": location,
                                "salary": "Competitive Salary",
                                "url": target['url']
                            })
                        except Exception as e:
                            # 5. 에러 메시지 상세화
                            if "destroyed" in str(e):
                                print(f"⚠️ 컨텍스트 파괴(리다이렉트 의심): {target['title']}")
                            else:
                                print(f"⚠️ 상세 실패: {e}")
                        finally:
                            await detail_page.close()
                            
                except Exception as e:
                    print(f"❌ {location} 수집 실패: {e}")
                    await page.close()
                    break

            await browser.close()
        return jobs
    
# 🎯 이 줄이 반드시 있어야 main.py에서 불러올 수 있습니다.
job_collector = JobCollector()