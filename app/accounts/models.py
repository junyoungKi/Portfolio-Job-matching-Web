"""
Author: Joonyoung Ki

Purpose: SQLAlchemy models for user accounts and wishlist items. These tables
are new; the existing ``job_postings`` and ``match_analyses`` tables are not
modified.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..database import Base


class User(Base):
    """A registered account identified by a unique, lower-cased email address."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WishlistItem(Base):
    """
    A job posting saved by a user.

    ``job_id`` intentionally has no foreign key: the nightly cleanup job
    deletes old postings and saved items must survive that. The display fields
    are a snapshot taken at save time so the saved list still renders after the
    original posting is removed.
    """

    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_wishlist_user_job"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id = Column(Integer, nullable=False, index=True)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    skills = Column(Text)
    summary_ko = Column(Text)
    summary_en = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
