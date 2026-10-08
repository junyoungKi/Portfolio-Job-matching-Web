"""
Author: Joonyoung Ki

Purpose: Security primitives for account handling: argon2 password hashing,
JWT creation/verification, and cookie settings driven by environment variables.

Environment variables:
    JWT_SECRET            Required for auth. HMAC secret, at least 32 characters.
    JWT_EXPIRE_MINUTES    Token and cookie lifetime in minutes (default 10080 = 7 days).
    COOKIE_SECURE         "true" to set the Secure cookie flag (use behind HTTPS).
                          Defaults to "false" so plain HTTP deployments keep working.
    COOKIE_SAMESITE       "lax" (default), "strict" or "none".
"""

import asyncio
import os
import time
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ACCESS_COOKIE_NAME = "access_token"
JWT_ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32

_hasher = PasswordHasher()
# A real hash used to equalize timing when the email is unknown.
_DUMMY_HASH = _hasher.hash("timing-equalization-placeholder")


class AuthNotConfiguredError(RuntimeError):
    """Raised when JWT_SECRET is missing or too short."""


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable (1/true/yes/on are truthy)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_jwt_secret() -> str:
    """Return the JWT secret from the environment or raise AuthNotConfiguredError."""
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise AuthNotConfiguredError(
            f"JWT_SECRET must be set to at least {MIN_SECRET_LENGTH} characters"
        )
    return secret


def token_lifetime_seconds() -> int:
    """Return the token lifetime in seconds from JWT_EXPIRE_MINUTES (default 7 days)."""
    try:
        minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
    except ValueError:
        minutes = 10080
    return max(minutes, 1) * 60


def cookie_settings() -> dict:
    """Return keyword arguments for ``Response.set_cookie`` based on the environment."""
    samesite = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    secure = _env_bool("COOKIE_SECURE", False)
    if samesite == "none":
        # Browsers reject SameSite=None cookies that are not Secure.
        secure = True
    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "path": "/",
        "max_age": token_lifetime_seconds(),
    }


async def hash_password(password: str) -> str:
    """Hash a password with argon2 in a worker thread so the event loop stays free."""
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """
    Verify a password against an argon2 hash.

    When ``password_hash`` is None (unknown account) a dummy verification is
    performed so response time does not reveal whether the email exists.
    """

    def _check() -> bool:
        """Run the blocking argon2 verification."""
        try:
            return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
        except (VerificationError, InvalidHashError):
            return False

    return await asyncio.to_thread(_check)


def create_access_token(user_id: int) -> str:
    """Create a signed JWT whose subject is the user id."""
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + token_lifetime_seconds()}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Return the user id from a valid token, or None if invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
