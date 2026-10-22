"""
Author: Joonyoung Ki

Purpose: FastAPI dependencies that resolve the current user from the JWT
cookie. ``get_optional_user`` keeps anonymous access working for the existing
resume/match endpoints; ``get_current_user`` protects account-only endpoints.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from .models import User
from .security import ACCESS_COOKIE_NAME, AuthNotConfiguredError, decode_access_token


async def get_optional_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Return the logged-in user, or None if the cookie is missing or invalid."""
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except AuthNotConfiguredError:
        return None
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


async def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    """Return the logged-in user or raise HTTP 401."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
