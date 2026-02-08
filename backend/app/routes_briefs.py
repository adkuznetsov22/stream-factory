from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Brief, Candidate, CandidateOrigin, CandidateStatus, Project
from app.schemas import BriefCreate, BriefRead, BriefUpdate, CandidateRead
from app.services.llm_provider import get_llm_provider

router = APIRouter(prefix="/api", tags=["briefs"])
SessionDep = Depends(get_session)


@router.get("/projects/{project_id}/briefs", response_model=list[BriefRead])
async def list_briefs(project_id: int, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    res = await session.execute(
        select(Brief).where(Brief.project_id == project_id).order_by(Brief.created_at.desc())
    )
    return res.scalars().all()


@router.post("/projects/{project_id}/briefs", response_model=BriefRead, status_code=status.HTTP_201_CREATED)
async def create_brief(project_id: int, data: BriefCreate, session: AsyncSession = SessionDep):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    brief = Brief(
        project_id=project_id,
        title=data.title,
        topic=data.topic,
        description=data.description,
        target_platform=data.target_platform,
        style=data.style,
        tone=data.tone,
        language=data.language,
        target_duration_sec=data.target_duration_sec,
        reference_urls=data.reference_urls,
        llm_prompt_template=data.llm_prompt_template,
        prompts=data.prompts,
        assets=data.assets,
        settings=data.settings,
    )
    session.add(brief)
    await session.commit()
    await session.refresh(brief)
    return brief


@router.get("/briefs/{brief_id}", response_model=BriefRead)
async def get_brief(brief_id: int, session: AsyncSession = SessionDep):
    brief = await session.get(Brief, brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@router.patch("/briefs/{brief_id}", response_model=BriefRead)
async def update_brief(brief_id: int, data: BriefUpdate, session: AsyncSession = SessionDep):
    brief = await session.get(Brief, brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(brief, field, value)
    session.add(brief)
    await session.commit()
    await session.refresh(brief)
    return brief


@router.delete("/briefs/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brief(brief_id: int, session: AsyncSession = SessionDep):
    brief = await session.get(Brief, brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    await session.delete(brief)
    await session.commit()
    return {}


@router.post("/briefs/{brief_id}/generate", response_model=CandidateRead)
async def generate_from_brief(brief_id: int, session: AsyncSession = SessionDep):
    """Generate content from a brief via LLM and create a GENERATE candidate."""
    brief = await session.get(Brief, brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    llm = get_llm_provider()
    try:
        result = await llm.generate(
            title=brief.title,
            topic=brief.topic,
            description=brief.description,
            style=brief.style,
            tone=brief.tone,
            language=brief.language,
            target_platform=brief.target_platform,
            target_duration_sec=brief.target_duration_sec,
            reference_urls=brief.reference_urls if isinstance(brief.reference_urls, list) else None,
            llm_prompt_template=brief.llm_prompt_template,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM generation failed: {exc}",
        ) from exc

    meta = result.to_meta()

    candidate = Candidate(
        project_id=brief.project_id,
        platform=brief.target_platform or "generated",
        platform_video_id=f"gen_{brief.id}_{uuid.uuid4().hex[:8]}",
        title=result.title_suggestion or brief.title,
        caption=result.captions_draft,
        origin=CandidateOrigin.generate.value,
        brief_id=brief.id,
        meta=meta,
        status=CandidateStatus.new.value,
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate
