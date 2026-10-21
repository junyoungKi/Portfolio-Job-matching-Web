"""Crawler batching: one duplicate-check query and one commit per city.

No database and no OpenAI key. The AI methods and the session are fakes.
"""
import asyncio

import app.main as main


class Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class Session:
    def __init__(self, existing=None, fail_batch=False, fail_titles=None):
        self.existing = list(existing or [])
        self.fail_batch = fail_batch
        self.fail_titles = set(fail_titles or [])
        self.executes = 0
        self.commits = 0
        self.rollbacks = 0
        self.added = []
        self._pending = []

    async def execute(self, stmt):
        self.executes += 1
        return Result(self.existing)

    def add_all(self, rows):
        self.added.append(list(rows))
        self._pending = list(rows)

    def add(self, row):
        self.added.append([row])
        self._pending = [row]

    async def commit(self):
        titles = {row.title for row in self._pending}
        pending_count = len(self._pending)
        self._pending = []
        if self.fail_batch and pending_count > 1:
            self.fail_batch = False
            raise RuntimeError("batch commit failed")
        if titles & self.fail_titles:
            raise RuntimeError("row rejected")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        self._pending = []

    def expunge_all(self):
        self._pending = []


def _job(title, company="Acme", description="build things"):
    return {
        "title": title,
        "company": company,
        "description": description,
        "location": "Seattle, WA",
        "salary": "100k",
    }


def _patch_ai(monkeypatch, fail_descriptions=None):
    fail_descriptions = set(fail_descriptions or [])
    calls = []
    state = {"in_flight": 0, "max_in_flight": 0}

    async def extract(description):
        calls.append(("meta", description))
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        await asyncio.sleep(0.01)
        state["in_flight"] -= 1
        return {"employment_type": "Full-time", "experience_level": "Junior", "skills": ["Python"]}

    async def embed(description):
        calls.append(("embed", description))
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        await asyncio.sleep(0.01)
        state["in_flight"] -= 1
        if description in fail_descriptions:
            raise RuntimeError("embedding failed")
        return [0.1, 0.2]

    monkeypatch.setattr(main.ai_service, "extract_job_metadata", extract)
    monkeypatch.setattr(main.ai_service, "get_embedding", embed)
    return calls, state


def test_one_select_and_one_commit_for_a_city(monkeypatch):
    calls, _state = _patch_ai(monkeypatch)
    session = Session(existing=[("Known", "Acme")])
    jobs = [
        _job("Known"),
        _job("New A"),
        _job("New A"),
        _job("New B", company="Other"),
    ]
    saved = asyncio.run(main.store_scraped_jobs(session, jobs, "Software Engineer"))
    assert saved == 2
    assert session.executes == 1
    assert session.commits == 2  # release the read, then one insert commit
    assert len(session.added) == 1
    assert sorted(row.title for row in session.added[0]) == ["New A", "New B"]
    assert {row.company for row in session.added[0]} == {"Acme", "Other"}
    assert all(row.search_keyword == "Software Engineer" for row in session.added[0])
    assert sorted(description for kind, description in calls if kind == "embed") == ["build things", "build things"]


def test_one_failed_embedding_does_not_drop_the_other_jobs(monkeypatch):
    _patch_ai(monkeypatch, fail_descriptions={"bad description"})
    session = Session()
    jobs = [_job("Good", description="good description"), _job("Bad", description="bad description")]
    saved = asyncio.run(main.store_scraped_jobs(session, jobs, "Software Engineer"))
    assert saved == 1
    assert [row.title for row in session.added[0]] == ["Good"]
    assert session.rollbacks == 0


def test_batch_commit_failure_retries_each_row(monkeypatch):
    _patch_ai(monkeypatch)
    session = Session(fail_batch=True, fail_titles={"Bad"})
    jobs = [_job("Good"), _job("Bad")]
    saved = asyncio.run(main.store_scraped_jobs(session, jobs, "Software Engineer"))
    assert saved == 1
    assert session.rollbacks >= 1
    titles = [row.title for batch in session.added for row in batch]
    assert titles.count("Good") == 2  # the failed batch, then the single-row retry
    assert "Bad" in titles


def test_llm_calls_stay_inside_the_semaphore(monkeypatch):
    _calls, state = _patch_ai(monkeypatch)
    monkeypatch.setattr(main, "llm_semaphore", asyncio.Semaphore(2))
    session = Session()
    jobs = [_job(f"Role {i}", description=f"desc {i}") for i in range(4)]
    saved = asyncio.run(main.store_scraped_jobs(session, jobs, "Software Engineer"))
    assert saved == 4
    # Four jobs, two calls each, at most two in flight.
    assert state["max_in_flight"] <= 2
    assert state["max_in_flight"] == 2


def test_empty_batch_does_not_query(monkeypatch):
    session = Session()
    assert asyncio.run(main.store_scraped_jobs(session, [], "Software Engineer")) == 0
    assert session.executes == 0
    assert session.commits == 0


def test_a_job_missing_a_title_is_skipped():
    session = Session()
    saved = asyncio.run(main.store_scraped_jobs(session, [{"company": "Acme"}], "Software Engineer"))
    assert saved == 0
    assert session.executes == 0
    assert session.commits == 0
