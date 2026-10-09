"""
Author: Joonyoung Ki

Purpose: Tests for the wishlist endpoints and for the additive ``id`` field on
the /match response, including anonymous access to the existing endpoints.
"""

from app import main as app_main
from app.database import AsyncSessionLocal
from app import models

CREDS = {"email": "w@example.com", "password": "passw0rdpassw0rd"}


async def _login(client):
    """Register and log in a user on the given client."""
    res = await client.post("/auth/register", json=CREDS)
    assert res.status_code == 201


async def test_wishlist_requires_login(client):
    """All wishlist endpoints return 401 for anonymous callers."""
    assert (await client.get("/wishlist")).status_code == 401
    assert (await client.post("/wishlist", json={"job_id": 1})).status_code == 401
    assert (await client.delete("/wishlist/1")).status_code == 401


async def test_wishlist_add_list_remove(client, job_ids):
    """Saving is idempotent, listing is newest first and deleting removes the item."""
    await _login(client)
    first, second = job_ids["jobs"]

    async with AsyncSessionLocal() as db:
        db.add(models.MatchAnalysis(resume_id=job_ids["resume"], job_id=first, summary_ko="요약", summary_en="Summary"))
        await db.commit()

    added = await client.post("/wishlist", json={"job_id": first})
    assert added.status_code == 201
    body = added.json()
    assert body["id"] == first and body["title"] == "Backend Engineer"
    assert body["summary_en"] == "Summary" and body["summary_ko"] == "요약"

    again = await client.post("/wishlist", json={"job_id": first})
    assert again.status_code == 200

    assert (await client.post("/wishlist", json={"job_id": second})).status_code == 201
    listing = (await client.get("/wishlist")).json()
    assert [i["id"] for i in listing] == [second, first]

    assert (await client.delete(f"/wishlist/{first}")).status_code == 204
    assert (await client.delete(f"/wishlist/{first}")).status_code == 204
    assert [i["id"] for i in (await client.get("/wishlist")).json()] == [second]


async def test_wishlist_rejects_unknown_resume_and_bad_ids(client, job_ids):
    """Resume uploads, unknown ids and out-of-range ids cannot be saved."""
    await _login(client)
    assert (await client.post("/wishlist", json={"job_id": job_ids["resume"]})).status_code == 404
    assert (await client.post("/wishlist", json={"job_id": 99999})).status_code == 404
    assert (await client.post("/wishlist", json={"job_id": 0})).status_code == 422
    assert (await client.post("/wishlist", json={"job_id": 2**40})).status_code == 422
    assert (await client.post("/wishlist", json={"job_id": "abc"})).status_code == 422


async def test_wishlists_are_isolated_per_user(client, job_ids):
    """One user cannot see or delete another user's saved jobs."""
    import httpx

    await _login(client)
    await client.post("/wishlist", json={"job_id": job_ids["jobs"][0]})

    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other:
        await other.post("/auth/register", json={"email": "o@example.com", "password": "passw0rdpassw0rd"})
        assert (await other.get("/wishlist")).json() == []
        await other.delete(f"/wishlist/{job_ids['jobs'][0]}")

    assert len((await client.get("/wishlist")).json()) == 1


async def test_saved_job_survives_posting_deletion(client, job_ids):
    """The snapshot keeps rendering after the original posting is cleaned up."""
    from sqlalchemy import delete

    await _login(client)
    job_id = job_ids["jobs"][0]
    await client.post("/wishlist", json={"job_id": job_id})
    async with AsyncSessionLocal() as db:
        await db.execute(delete(models.JobPosting).where(models.JobPosting.id == job_id))
        await db.commit()
    listing = (await client.get("/wishlist")).json()
    assert listing[0]["title"] == "Backend Engineer"


async def test_match_response_includes_id_and_works_anonymously(client, job_ids, monkeypatch):
    """/match keeps its existing fields, adds ``id`` and needs no login."""
    async def fake_rerank(resume_text, jobs, preferred_skills=None):
        """Return the candidate order unchanged."""
        return list(range(len(jobs)))

    async def fake_analyze(resume_text, job_text, lang="ko"):
        """Return a canned analysis."""
        return {"job_summary": f"sum-{lang}", "detail_analysis": f"detail-{lang}"}

    monkeypatch.setattr(app_main.ai_service, "rerank_jobs", fake_rerank)
    monkeypatch.setattr(app_main.ai_service, "analyze_match", fake_analyze)

    res = await client.get(f"/match/{job_ids['resume']}")
    assert res.status_code == 200
    results = res.json()
    assert {r["id"] for r in results} == set(job_ids["jobs"])
    expected = {"title", "company", "location", "salary", "match_score", "summary_ko",
                "analysis_ko", "summary_en", "analysis_en", "skills"}
    assert expected <= set(results[0])
