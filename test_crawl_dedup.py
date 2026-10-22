"""Dedup key: LinkedIn job id, then normalized title + company + location.

No database, no network, and no API key. Decisions are pure. One test stores a
row through the batch helper with a fake session.
"""
import asyncio
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from sqlalchemy.dialects import postgresql

import app.main as main
from test_crawl_batch import Session, _patch_ai


VIEW = "https://www.linkedin.com/jobs/view/software-engineer-at-slack-3829103847?trk=public_jobs"
OTHER = "https://www.linkedin.com/jobs/view/software-engineer-at-slack-3829103999"
SALESFORCE = "https://www.linkedin.com/jobs/view/software-engineer-at-salesforce-3829103847?refId=abc"


def _job(title="Software Engineer", company="Slack", location="Seattle, WA", url=None):
    job = {
        "title": title,
        "company": company,
        "description": "build things",
        "location": location,
        "salary": "100k",
    }
    if url is not None:
        job["url"] = url
    return job


def _record(job):
    return {"job": job, **main.posting_identity(job)}


def _fresh(jobs, existing_ids=(), legacy=(), any_fb=()):
    records, invalid = main.prepare_posting_records(jobs)
    assert invalid == 0
    fresh, skipped = main.select_new_postings(
        records, set(existing_ids), set(legacy), set(any_fb)
    )
    return fresh, skipped


def test_job_id_from_a_slug_a_bare_path_and_a_query_param():
    assert main.linkedin_job_id(VIEW) == "3829103847"
    assert main.linkedin_job_id("https://www.linkedin.com/jobs/view/3829103847/") == "3829103847"
    assert main.linkedin_job_id(
        "https://www.linkedin.com/jobs/search/?currentJobId=3829103847&keywords=software"
    ) == "3829103847"


def test_url_without_an_id_and_a_missing_url():
    assert main.linkedin_job_id("https://www.linkedin.com/jobs/view/software-engineer") is None
    assert main.linkedin_job_id("https://example.com/roles/2024") is None
    assert main.linkedin_job_id(None) is None
    assert main.linkedin_job_id("") is None


def test_normalization_collapses_case_and_whitespace():
    assert main.normalize_dedup_text("  Software   Engineer ") == "software engineer"
    assert main.normalize_dedup_text("SLACK") == main.normalize_dedup_text(" slack ")
    assert main.normalize_dedup_text(None) == ""
    left = main.posting_identity(_job(title="Software  Engineer", company=" Slack ", location="Seattle,  WA"))
    right = main.posting_identity(_job(title="software engineer", company="slack", location="seattle, wa"))
    assert left["fallback"] == right["fallback"]
    # Different company spellings stay different. The job id is what unifies them.
    salesforce = main.posting_identity(_job(company="Salesforce"))
    assert left["fallback"] != salesforce["fallback"]


def test_same_id_is_skipped_even_when_the_company_text_differs():
    jobs = [
        _job(company="Slack", url=VIEW),
        _job(company="Salesforce", location="San Francisco, CA", url=SALESFORCE),
    ]
    fresh, skipped = _fresh(jobs)
    assert [record["job"]["company"] for record in fresh] == ["Slack"]
    assert [record["job"]["company"] for record in skipped] == ["Salesforce"]

    fresh, skipped = _fresh(
        [_job(company="Salesforce", url=SALESFORCE)],
        existing_ids={"3829103847"},
    )
    assert fresh == []
    assert len(skipped) == 1


def test_same_title_and_company_with_a_different_city_and_id_is_saved():
    jobs = [
        _job(location="Seattle, WA", url=VIEW),
        _job(location="Austin, TX", url=OTHER),
    ]
    fresh, skipped = _fresh(jobs)
    assert skipped == []
    assert [record["job"]["location"] for record in fresh] == ["Seattle, WA", "Austin, TX"]
    assert [record["source_job_id"] for record in fresh] == ["3829103847", "3829103999"]


def test_legacy_row_matches_the_normalized_fallback_and_not_a_different_city():
    legacy = {("software engineer", "slack", "seattle, wa")}
    same_city = _job(title="Software  Engineer", company=" SLACK ", location="Seattle,   WA", url=VIEW)
    other_city = _job(location="Austin, TX", url=OTHER)
    fresh, skipped = _fresh([same_city, other_city], legacy=legacy)
    assert [record["job"]["location"] for record in skipped] == ["Seattle,   WA"]
    assert [record["job"]["location"] for record in fresh] == ["Austin, TX"]


def test_url_without_an_id_uses_the_fallback_and_keeps_another_location():
    jobs = [
        _job(location="Seattle, WA"),
        _job(title="software engineer", company="slack", location="seattle, wa"),
        _job(location="Austin, TX"),
    ]
    fresh, skipped = _fresh(jobs)
    assert len(fresh) == 2
    assert [record["job"]["location"] for record in fresh] == ["Seattle, WA", "Austin, TX"]
    assert len(skipped) == 1
    assert all(record["source_job_id"] is None for record in fresh)

    stored = {("software engineer", "slack", "seattle, wa")}
    fresh, skipped = _fresh([_job(location="Seattle, WA")], any_fb=stored)
    assert fresh == []
    assert len(skipped) == 1


def test_fallback_sql_uses_title_company_and_location_and_leaves_hnsw_alone():
    fallback = main.existing_fallback_stmt([("software engineer", "slack", "seattle, wa")])
    compiled = str(fallback.compile(dialect=postgresql.dialect())).lower()
    assert "title" in compiled
    assert "company" in compiled
    assert "location" in compiled
    assert "source_job_id" in compiled
    ids = str(
        main.existing_source_ids_stmt(["3829103847"]).compile(dialect=postgresql.dialect())
    ).lower()
    assert "source_job_id" in ids
    assert "location" not in ids
    assert "source_job_id" not in main.HNSW_INDEX_SQL.lower()
    assert "embedding" in main.HNSW_INDEX_SQL.lower()
    assert main.SOURCE_JOB_ID_COLUMN_SQL.startswith("ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS")
    assert "IF NOT EXISTS" in main.SOURCE_JOB_ID_INDEX_SQL


def test_batch_save_stores_the_job_id_and_skips_a_known_id(monkeypatch):
    from test_crawl_batch import Result

    calls, _state = _patch_ai(monkeypatch)

    class RoutingSession(Session):
        async def execute(self, stmt):
            self.executes += 1
            compiled = str(stmt.compile(dialect=postgresql.dialect())).lower()
            if "regexp_replace" in compiled:
                return Result([])
            return Result([("3829103847",)])

    session = RoutingSession()
    jobs = [
        _job(company="Slack", url=VIEW),
        _job(company="Other", location="Austin, TX", url=OTHER),
    ]
    saved = asyncio.run(main.store_scraped_jobs(session, jobs, "Software Engineer"))
    assert saved == 1
    assert session.executes == 2  # id lookup, then fallback lookup
    assert [row.title for row in session.added[0]] == ["Software Engineer"]
    assert session.added[0][0].source_job_id == "3829103999"
    assert session.added[0][0].company == "Other"
    assert len(calls) == 2  # metadata + embedding for the new id only
