"""
Author: Joonyoung Ki

Purpose: A small in-memory sliding-window rate limiter used to slow down
credential guessing on the login and register endpoints.

Limitations: state is per process (the deployment runs a single uvicorn
worker) and is lost on restart. Use Redis or a reverse-proxy limiter if the
service is ever scaled horizontally.

Environment variables:
    TRUST_FORWARDED_FOR   "true" to use the first X-Forwarded-For address as the
                          client IP (only enable behind a trusted reverse proxy).
    LOGIN_RATE_LIMIT      Max login attempts per key per window (default 10).
    LOGIN_RATE_WINDOW     Window length in seconds (default 900).
"""

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


def _env_int(name: str, default: int) -> int:
    """Read a positive integer environment variable with a fallback."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


class SlidingWindowLimiter:
    """Track event timestamps per key and reject keys that exceed a limit."""

    def __init__(self) -> None:
        """Create an empty limiter."""
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def _prune(self, key: str, window: int, now: float) -> Deque[float]:
        """Drop timestamps older than the window and return the remaining queue."""
        events = self._events[key]
        while events and now - events[0] >= window:
            events.popleft()
        if not events:
            self._events.pop(key, None)
            return deque()
        return events

    def retry_after(self, key: str, limit: int, window: int) -> int:
        """Return seconds until ``key`` may act again, or 0 if it is under the limit."""
        now = time.monotonic()
        events = self._prune(key, window, now)
        if len(events) < limit:
            return 0
        return max(int(window - (now - events[0])) + 1, 1)

    def record(self, key: str, window: int) -> None:
        """Record one event for ``key``."""
        now = time.monotonic()
        self._prune(key, window, now)
        self._events[key].append(now)

    def reset(self, key: str) -> None:
        """Forget all events for ``key`` (used after a successful login)."""
        self._events.pop(key, None)

    def clear(self) -> None:
        """Forget every key (used by tests)."""
        self._events.clear()


login_limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """Return the caller IP, honouring X-Forwarded-For only when explicitly trusted."""
    if os.getenv("TRUST_FORWARDED_FOR", "false").strip().lower() in {"1", "true", "yes", "on"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def login_keys(request: Request, email: str) -> list:
    """Return the limiter keys for a login attempt: one per IP and one per email."""
    return [f"ip:{client_ip(request)}", f"email:{email}"]


def _enforce(keys: list) -> None:
    """Raise HTTP 429 with a Retry-After header if any key is over the limit."""
    limit = _env_int("LOGIN_RATE_LIMIT", 10)
    window = _env_int("LOGIN_RATE_WINDOW", 900)
    for key in keys:
        wait = login_limiter.retry_after(key, limit, window)
        if wait:
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(wait)},
            )


def enforce_login_limit(request: Request, email: str) -> None:
    """Reject a login attempt when the IP or email has too many recent failures."""
    _enforce(login_keys(request, email))


def record_login_failure(request: Request, email: str) -> None:
    """Record a failed login against both the IP and the email key."""
    window = _env_int("LOGIN_RATE_WINDOW", 900)
    for key in login_keys(request, email):
        login_limiter.record(key, window)


def clear_login_failures(request: Request, email: str) -> None:
    """Reset the email key after a successful login (the IP key keeps its history)."""
    login_limiter.reset(f"email:{email}")


def enforce_register_limit(request: Request) -> None:
    """Reject registrations when the caller IP has created too many accounts recently."""
    _enforce([f"register:{client_ip(request)}"])


def record_register_attempt(request: Request) -> None:
    """Count a successful registration against the caller IP to limit account spam."""
    window = _env_int("LOGIN_RATE_WINDOW", 900)
    login_limiter.record(f"register:{client_ip(request)}", window)
