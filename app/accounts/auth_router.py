"""
Author: Joonyoung Ki

Purpose: Authentication endpoints: /auth/register, /auth/login, /auth/logout
and /auth/me. Sessions are JWTs stored in an httpOnly cookie.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from .deps import get_current_user
from .models import User
from .rate_limit import (
    clear_login_failures,
    enforce_login_limit,
    enforce_register_limit,
    record_login_failure,
    record_register_attempt,
)
from .security import (
    ACCESS_COOKIE_NAME,
    AuthNotConfiguredError,
    cookie_settings,
    create_access_token,
    get_jwt_secret,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def normalize_email(value: str) -> str:
    """Trim, lower-case and validate an email address, raising ValueError if invalid."""
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise ValueError("Invalid email address")
    return email


class RegisterRequest(BaseModel):
    """Payload for account registration."""

    email: str = Field(max_length=254)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        """Normalize and validate the email field."""
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        """Enforce the minimum password policy: length, a letter and a digit."""
        if len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one digit")
        return value


class LoginRequest(BaseModel):
    """Payload for login; the password policy is not re-checked here."""

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        """Normalize the email field (invalid addresses cannot match any account)."""
        return value.strip().lower()


class UserResponse(BaseModel):
    """Public user representation returned by the auth endpoints."""

    id: int
    email: str


def _issue_cookie(response: Response, user: User) -> None:
    """Create a JWT for the user and attach it as an httpOnly cookie."""
    try:
        token = create_access_token(user.id)
    except AuthNotConfiguredError:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    response.set_cookie(ACCESS_COOKIE_NAME, token, **cookie_settings())


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Create an account and log the new user in."""
    enforce_register_limit(request)
    try:
        get_jwt_secret()
    except AuthNotConfiguredError:
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    existing = await db.execute(select(User.id).where(User.email == body.email))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(email=body.email, password_hash=await hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    await db.refresh(user)

    record_register_attempt(request)
    _issue_cookie(response, user)
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Verify credentials and set the session cookie."""
    enforce_login_limit(request, body.email)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()
    valid = await verify_password(body.password, user.password_hash if user else None)
    if not valid or user is None:
        record_login_failure(request, body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    clear_login_failures(request, body.email)
    _issue_cookie(response, user)
    return UserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
async def logout():
    """Clear the session cookie."""
    settings = cookie_settings()
    response = Response(status_code=204)
    response.delete_cookie(
        ACCESS_COOKIE_NAME,
        path=settings["path"],
        secure=settings["secure"],
        httponly=True,
        samesite=settings["samesite"],
    )
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the logged-in user, or 401 for anonymous callers."""
    return UserResponse(id=user.id, email=user.email)
