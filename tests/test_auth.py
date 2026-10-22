"""
Author: Joonyoung Ki

Purpose: Tests for /auth/register, /auth/login, /auth/logout and /auth/me
including validation, cookie flags and the login rate limit.
"""

import pytest

GOOD = {"email": "User@Example.com", "password": "correct horse 9"}


async def test_register_sets_httponly_cookie_and_me_works(client):
    """Registering logs the user in with an httpOnly cookie and normalizes the email."""
    res = await client.post("/auth/register", json=GOOD)
    assert res.status_code == 201
    assert res.json()["email"] == "user@example.com"
    set_cookie = res.headers["set-cookie"].lower()
    assert "access_token=" in set_cookie and "httponly" in set_cookie
    assert "samesite=lax" in set_cookie and "secure" not in set_cookie
    assert "password" not in res.text

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


async def test_cookie_secure_flag_follows_environment(client, monkeypatch):
    """COOKIE_SECURE=true adds the Secure attribute to the session cookie."""
    monkeypatch.setenv("COOKIE_SECURE", "true")
    res = await client.post("/auth/register", json=GOOD)
    assert "secure" in res.headers["set-cookie"].lower()


async def test_duplicate_email_is_rejected_case_insensitively(client):
    """A second registration with the same email returns 409."""
    assert (await client.post("/auth/register", json=GOOD)).status_code == 201
    dup = await client.post("/auth/register", json={**GOOD, "email": "user@EXAMPLE.com"})
    assert dup.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "abcdefg1"},
        {"email": "a@b.co", "password": "short1"},
        {"email": "a@b.co", "password": "onlyletters"},
        {"email": "a@b.co", "password": "12345678"},
        {"email": "a@b.co", "password": "a1" * 100},
        {"email": "a@b.co"},
    ],
)
async def test_register_validation(client, payload):
    """Invalid emails and weak passwords are rejected with 422."""
    res = await client.post("/auth/register", json=payload)
    assert res.status_code == 422


async def test_login_logout_flow(client):
    """Login succeeds with correct credentials; logout clears access to /auth/me."""
    await client.post("/auth/register", json=GOOD)
    client.cookies.clear()
    assert (await client.get("/auth/me")).status_code == 401

    bad = await client.post("/auth/login", json={**GOOD, "password": "wrong-password1"})
    assert bad.status_code == 401
    unknown = await client.post("/auth/login", json={"email": "x@y.com", "password": "whatever12"})
    assert unknown.status_code == 401
    assert bad.json()["detail"] == unknown.json()["detail"]

    ok = await client.post("/auth/login", json={"email": " USER@example.com ", "password": GOOD["password"]})
    assert ok.status_code == 200
    assert (await client.get("/auth/me")).status_code == 200

    out = await client.post("/auth/logout")
    assert out.status_code == 204
    assert "max-age=0" in out.headers["set-cookie"].lower()
    client.cookies.clear()
    assert (await client.get("/auth/me")).status_code == 401


async def test_tampered_and_expired_tokens_are_rejected(client, monkeypatch):
    """Garbage and expired JWTs do not authenticate."""
    await client.post("/auth/register", json=GOOD)
    client.cookies.set("access_token", "garbage.token.value")
    assert (await client.get("/auth/me")).status_code == 401

    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "1")
    from app.accounts import security

    monkeypatch.setattr(security.time, "time", lambda: 1_000_000)
    token = security.create_access_token(1)
    monkeypatch.undo()
    client.cookies.set("access_token", token)
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_rate_limit(client, monkeypatch):
    """Repeated failures lock out further attempts with 429 and Retry-After."""
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    await client.post("/auth/register", json=GOOD)
    for _ in range(3):
        res = await client.post("/auth/login", json={**GOOD, "password": "wrong-password1"})
        assert res.status_code == 401
    locked = await client.post("/auth/login", json=GOOD)
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


async def test_auth_unavailable_without_jwt_secret(client, monkeypatch):
    """A missing JWT_SECRET yields 503 on register instead of crashing the app."""
    monkeypatch.delenv("JWT_SECRET")
    res = await client.post("/auth/register", json=GOOD)
    assert res.status_code == 503
