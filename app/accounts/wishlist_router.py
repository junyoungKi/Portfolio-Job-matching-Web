"""
Author: Joonyoung Ki

Purpose: Wishlist endpoints for logged-in users: list saved job postings
(GET /wishlist), save one (POST /wishlist) and remove one
(DELETE /wishlist/{job_id}).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models as core_models
from ..database import get_db
from .deps import get_current_user
from .models import User, WishlistItem

router = APIRouter(prefix="/wishlist", tags=["wishlist"])

# Postgres INTEGER upper bound; larger ids can never exist and would raise a driver error.
MAX_JOB_ID = 2_147_483_647


class WishlistAddRequest(BaseModel):
    """Payload for saving a job posting."""

    job_id: int = Field(ge=1, le=MAX_JOB_ID)


class WishlistItemResponse(BaseModel):
    """A saved job posting as returned to the client."""

    id: int
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    skills: Optional[str] = None
    summary_ko: Optional[str] = None
    summary_en: Optional[str] = None
    saved_at: str


def _to_response(item: WishlistItem) -> WishlistItemResponse:
    """Convert a database row to the response model; ``id`` is the job posting id."""
    return WishlistItemResponse(
        id=item.job_id,
        title=item.title,
        company=item.company,
        location=item.location,
        salary=item.salary,
        skills=item.skills,
        summary_ko=item.summary_ko,
        summary_en=item.summary_en,
        saved_at=item.created_at.isoformat() if item.created_at else "",
    )


@router.get("", response_model=List[WishlistItemResponse])
async def list_wishlist(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Return the user's saved jobs, newest first."""
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .order_by(desc(WishlistItem.created_at), desc(WishlistItem.id))
    )
    return [_to_response(item) for item in result.scalars().all()]


@router.post("", response_model=WishlistItemResponse, status_code=201)
async def add_to_wishlist(
    body: WishlistAddRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a job posting; saving an already saved job is a no-op that returns 200."""
    existing = await db.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.job_id == body.job_id
        )
    )
    item = existing.scalars().first()
    if item is not None:
        response.status_code = 200
        return _to_response(item)

    job_result = await db.execute(
        select(core_models.JobPosting).where(
            core_models.JobPosting.id == body.job_id,
            core_models.JobPosting.company != "USER_UPLOAD",
        )
    )
    job = job_result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    analysis_result = await db.execute(
        select(core_models.MatchAnalysis)
        .where(core_models.MatchAnalysis.job_id == job.id)
        .order_by(desc(core_models.MatchAnalysis.id))
        .limit(1)
    )
    analysis = analysis_result.scalars().first()

    item = WishlistItem(
        user_id=user.id,
        job_id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        salary=job.salary,
        skills=job.skills,
        summary_ko=analysis.summary_ko if analysis else None,
        summary_en=analysis.summary_en if analysis else None,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent request saved the same job first; treat it as already saved.
        await db.rollback()
        existing = await db.execute(
            select(WishlistItem).where(
                WishlistItem.user_id == user.id, WishlistItem.job_id == body.job_id
            )
        )
        item = existing.scalars().first()
        if item is None:
            raise HTTPException(status_code=409, detail="Could not save job")
        response.status_code = 200
        return _to_response(item)
    await db.refresh(item)
    return _to_response(item)


@router.delete("/{job_id}", status_code=204)
async def remove_from_wishlist(
    job_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a saved job; removing one that is not saved still returns 204."""
    if job_id < 1 or job_id > MAX_JOB_ID:
        return Response(status_code=204)
    await db.execute(
        delete(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.job_id == job_id
        )
    )
    await db.commit()
    return Response(status_code=204)
