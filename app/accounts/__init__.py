"""
Author: Joonyoung Ki

Purpose: Account features for the job matching service: email/password
authentication (JWT in an httpOnly cookie) and a per-user wishlist of job
postings. Importing this package registers the account tables on the shared
SQLAlchemy metadata so the existing ``create_all`` lifespan hook creates them.
"""

from . import models  # noqa: F401  (registers tables on Base.metadata)
from .auth_router import router as auth_router
from .wishlist_router import router as wishlist_router

__all__ = ["auth_router", "wishlist_router"]
