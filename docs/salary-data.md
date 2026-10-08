<!--
Author: Joonyoung Ki
Purpose: Salary data source research, compliance notes, schema, and operations guide
for the structured salary feature.
-->

# Structured salary data

## 1. Current state (before this change)

* `app/services/collector.py` only scrapes **LinkedIn public job search** with Playwright. It hard-coded
  `"salary": "Competitive Salary"` for every posting, so the `job_postings.salary` text column never held a real
  pay figure and `frontend/src/lib/salary.ts` could never extract a number from production data.
* The `salary` column is free text (`String`); no structured amounts, currency or period existed.

## 2. Sources that expose pay (measured 2026-10-08, public APIs, no login)

| Source | Structured pay field | Measured coverage (jobs with pay / total) | Notes |
| --- | --- | --- | --- |
| Greenhouse Job Board API (`boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true&pay_transparency=true`) | `pay_input_ranges[]` (`min_cents`, `max_cents`, `currency_type`, `title`) plus a `pay-range` HTML block in `content` | Airbnb 129/163, Databricks 490/894, Coinbase 218/223, Reddit 122/156, Figma 101/152, Okta 226/370, Robinhood 150/165, Datadog 217/439; Stripe, Cloudflare, Twilio 0 | Coverage depends on each employer enabling pay transparency. One range per location tier. |
| Lever Postings API (`api.lever.co/v0/postings/{site}?mode=json`) | `salaryRange` (`min`, `max`, `currency`, `interval`) and `salaryDescriptionPlain` | WeRide 4/17, Spotify 0/76, Palantir 0/315 | Sparse; only some employers fill it. |
| Ashby Posting API (`api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true`) | `compensation.compensationTiers[].components[]` / `summaryComponents` (`minValue`, `maxValue`, `currencyCode`, `interval`) and `scrapeableCompensationSalarySummary` | Ashby board 68/68 | Best structure; only returned when `includeCompensation=true`. |
| schema.org JSON-LD `baseSalary` in a job page | `MonetaryAmount` / `QuantitativeValue` (`minValue`, `maxValue`, `unitText`) | Varies by site | Parsed from HTML we already loaded; no extra requests. |
| Pay-range sentences in descriptions ("The base salary range is $X - $Y") | Free text | Common for US states with pay-transparency laws (CA, CO, NY, WA) | Parsed only near words such as salary / pay range / compensation to avoid false positives. |
| LinkedIn public job pages | Occasionally JSON-LD or a salary element | Unknown, mostly absent | See compliance below. |

Precedence when several are present: structured ATS fields > JSON-LD > explicit salary text > description sentence.

## 3. Compliance review

| Source | robots.txt | Terms / access model | Verdict |
| --- | --- | --- | --- |
| Greenhouse Job Board API | `Disallow: /embed/` only | Documented public, unauthenticated API for job boards | OK. Client checks robots.txt, identifies itself, 1 request/second/host. |
| Lever Postings API | `Allow: /`, `Crawl-delay: 1` | Documented public API | OK. 1 s delay honoured. |
| Ashby Posting API | API host has no robots.txt (HTTP 401 body); `jobs.ashbyhq.com` disallows `/api/`, `/b/`, `/meeting/` | Documented public Posting API | OK, using only the documented API host. A 4xx robots response is treated as "no restrictions" (RFC 9309). |
| **LinkedIn (existing collector)** | `User-agent: *` -> `Disallow: /` (also `/jobs-guest/`); crawling needs written whitelisting | User Agreement forbids automated access/scraping | **Non-compliant pre-existing behaviour.** This change adds no new LinkedIn requests (salary is read from the already loaded detail page), but we recommend replacing LinkedIn with the ATS APIs above or an official partner feed, and not relying on LinkedIn for pay data. |

Limitations: ATS coverage is only for configured employers (`ATS_BOARDS`); pay is often absent; location-tiered
ranges are merged into one envelope (widest range, USD preferred when currencies differ); equity/bonus are ignored.

## 4. Schema (all nullable, `salary` text column kept)

`salary_min`, `salary_max` (double, in the stated period), `salary_currency` (ISO code), `salary_period`
(`hourly|daily|weekly|biweekly|monthly|yearly`), `salary_annual_min`, `salary_annual_max` (annualised, original
currency; hourly x2080, daily x260, weekly x52, biweekly x26, monthly x12), `salary_source`
(`ats:greenhouse|ats:lever|ats:ashby|jsonld|description_text|salary_text`).

`/match` additionally returns these fields plus `salary_annual_min_usd_approx` / `salary_annual_max_usd_approx`
(static FX table in `salary_parser.APPROX_USD_RATES`, for sorting only). Existing response fields are unchanged.

## 5. Operations

```bash
# 1) Migration (idempotent; also runs automatically on app start). Takes a 5 s lock_timeout and an advisory lock.
python -m scripts.migrate_salary_columns

# 2) Backfill existing rows from salary text, no crawling
python -m scripts.backfill_salary --dry-run --from-description   # review first
python -m scripts.backfill_salary --from-description             # --force re-parses rows that already have a source

# 3) Optional ATS ingestion (disabled when empty)
export ATS_BOARDS="greenhouse:airbnb,lever:weride,ashby:ashby"
```

Tests: `python -m pytest tests` (set `TEST_DATABASE_URL=postgresql+asyncpg://.../job_match_test` for the DB tests).
Redis caches `/match` for one hour, so the new fields appear after the cache expires or is flushed.
