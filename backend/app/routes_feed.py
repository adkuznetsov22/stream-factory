from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Candidate, CandidateStatus, Project, ProjectDestination, PublishTask
from app.schemas import (
    CandidateApproveResponse,
    CandidateCreate,
    CandidateRateRequest,
    CandidateRead,
)

router = APIRouter(prefix="/api", tags=["feed"])
SessionDep = Depends(get_session)


@router.get("/projects/{project_id}/feed", response_model=list[CandidateRead])
async def get_project_feed(
    project_id: int,
    min_score: float | None = Query(None, description="Minimum virality score"),
    platform: str | None = Query(None, description="Filter by platform"),
    include_used: bool = Query(False, description="Include USED candidates"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: NEW, APPROVED, REJECTED, USED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = SessionDep,
):
    """Get feed of video candidates for a project."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    q = select(Candidate).where(Candidate.project_id == project_id)

    if min_score is not None:
        q = q.where(Candidate.virality_score >= min_score)

    if platform:
        q = q.where(Candidate.platform == platform)

    if status_filter:
        q = q.where(Candidate.status == status_filter.upper())
    elif not include_used:
        q = q.where(Candidate.status != CandidateStatus.used.value)

    q = q.order_by(Candidate.virality_score.desc().nullslast(), Candidate.created_at.desc())
    q = q.limit(limit).offset(offset)

    res = await session.execute(q)
    return res.scalars().all()


@router.post("/projects/{project_id}/feed", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    project_id: int,
    data: CandidateCreate,
    session: AsyncSession = SessionDep,
):
    """Add a candidate to project feed (used by sync services)."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for duplicate
    existing = await session.execute(
        select(Candidate).where(
            Candidate.project_id == project_id,
            Candidate.platform == data.platform,
            Candidate.platform_video_id == data.platform_video_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Candidate already exists for this video")

    candidate = Candidate(
        project_id=project_id,
        platform=data.platform,
        platform_video_id=data.platform_video_id,
        url=data.url,
        author=data.author,
        title=data.title,
        caption=data.caption,
        thumbnail_url=data.thumbnail_url,
        published_at=data.published_at,
        views=data.views,
        likes=data.likes,
        comments=data.comments,
        shares=data.shares,
        subscribers=data.subscribers,
        virality_score=data.virality_score,
        virality_factors=data.virality_factors,
        status=CandidateStatus.new.value,
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


@router.post("/projects/{project_id}/feed/{candidate_id}/approve", response_model=CandidateApproveResponse)
async def approve_candidate(
    project_id: int,
    candidate_id: int,
    session: AsyncSession = SessionDep,
):
    """Approve candidate → create PublishTask and link it."""
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(status_code=404, detail="Candidate not found in this project")

    if candidate.status not in (CandidateStatus.new.value, CandidateStatus.rejected.value):
        raise HTTPException(status_code=400, detail=f"Cannot approve candidate with status {candidate.status}")

    # Get project with destinations
    res = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.destinations))
    )
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.destinations:
        raise HTTPException(status_code=400, detail="Project has no destinations configured")

    # Pick first active destination
    dest = next((d for d in project.destinations if d.is_active), None)
    if not dest:
        raise HTTPException(status_code=400, detail="No active destination found")

    # Create PublishTask
    task = PublishTask(
        project_id=project_id,
        platform=dest.platform,
        destination_social_account_id=dest.social_account_id,
        external_id=candidate.platform_video_id,
        permalink=candidate.url,
        preview_url=candidate.thumbnail_url,
        download_url=candidate.url,
        caption_text=candidate.caption or candidate.title,
        status="queued",
        preset_id=project.preset_id,
        total_steps=0,
    )
    session.add(task)
    await session.flush()  # get task.id

    # Link candidate to task
    candidate.status = CandidateStatus.approved.value
    candidate.linked_publish_task_id = task.id
    candidate.reviewed_at = datetime.now(timezone.utc)
    session.add(candidate)

    await session.commit()
    await session.refresh(candidate)

    return CandidateApproveResponse(
        candidate_id=candidate.id,
        task_id=task.id,
        status=candidate.status,
    )


@router.post("/projects/{project_id}/feed/{candidate_id}/reject", response_model=CandidateRead)
async def reject_candidate(
    project_id: int,
    candidate_id: int,
    session: AsyncSession = SessionDep,
):
    """Reject a candidate."""
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(status_code=404, detail="Candidate not found in this project")

    if candidate.status not in (CandidateStatus.new.value, CandidateStatus.approved.value):
        raise HTTPException(status_code=400, detail=f"Cannot reject candidate with status {candidate.status}")

    candidate.status = CandidateStatus.rejected.value
    candidate.reviewed_at = datetime.now(timezone.utc)
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


@router.post("/projects/{project_id}/feed/{candidate_id}/rate", response_model=CandidateRead)
async def rate_candidate(
    project_id: int,
    candidate_id: int,
    data: CandidateRateRequest,
    session: AsyncSession = SessionDep,
):
    """Set manual rating (1-5) for a candidate."""
    if data.manual_rating < 1 or data.manual_rating > 5:
        raise HTTPException(status_code=400, detail="manual_rating must be 1-5")

    candidate = await session.get(Candidate, candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(status_code=404, detail="Candidate not found in this project")

    candidate.manual_rating = data.manual_rating
    if data.notes is not None:
        candidate.notes = data.notes
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate
