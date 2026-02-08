from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.services.dedupe import compute_candidate_signature, find_duplicate
from app.services.simhash import compute_text_simhash, simhash_to_hex
from app.services.topic_guard import ensure_candidate_topic_meta
from app.models import (
    Brief,
    Candidate,
    CandidateOrigin,
    CandidateStatus,
    InstagramPost,
    InstagramProfile,
    Project,
    ProjectDestination,
    ProjectSource,
    PublishTask,
    SocialAccount,
    TikTokProfile,
    TikTokVideo,
    VKClip,
    VKProfile,
    VKVideo,
    YouTubeChannel,
    YouTubeVideo,
)
from app.schemas import (
    CandidateApproveRequest,
    CandidateApproveResponse,
    CandidateCreate,
    CandidateRateRequest,
    CandidateRead,
)
from app.services.virality import calculate_virality_score

router = APIRouter(prefix="/api", tags=["feed"])
SessionDep = Depends(get_session)


@router.get("/projects/{project_id}/feed", response_model=list[CandidateRead])
async def get_project_feed(
    project_id: int,
    min_score: float | None = Query(None, description="Minimum virality score"),
    platform: str | None = Query(None, description="Filter by platform"),
    include_used: bool = Query(False, description="Include USED candidates"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: NEW, APPROVED, REJECTED, USED"),
    origin: str | None = Query(None, description="Filter by origin: REPURPOSE, GENERATE"),
    brief_id: int | None = Query(None, description="Filter by brief_id"),
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

    if origin:
        q = q.where(Candidate.origin == origin.upper())

    if brief_id is not None:
        q = q.where(Candidate.brief_id == brief_id)

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
        origin=data.origin,
        brief_id=data.brief_id,
        meta=data.meta,
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
    body: CandidateApproveRequest | None = None,
    session: AsyncSession = SessionDep,
):
    """Approve candidate → create PublishTask and link it.

    Если в body передан destination_id — используется указанный destination.
    Иначе — первый активный destination проекта.
    """
    if body is None:
        body = CandidateApproveRequest()

    candidate = await session.get(Candidate, candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(status_code=404, detail="Candidate not found in this project")

    if candidate.status not in (CandidateStatus.new.value, CandidateStatus.rejected.value):
        raise HTTPException(status_code=400, detail=f"Cannot approve candidate with status {candidate.status}")

    # Exact duplicate check via content_signature
    sig = (candidate.meta or {}).get("content_signature")
    if sig:
        dup = await find_duplicate(session, project_id, sig, exclude_candidate_id=candidate.id)
        if dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate",
                    "duplicate_candidate_id": dup.id,
                    "message": f"Duplicate of candidate #{dup.id} (status={dup.status})",
                },
            )

    # Near-duplicate check via SimHash
    sh_hex = (candidate.meta or {}).get("content_simhash64")
    if sh_hex:
        from app.services.simhash import find_near_duplicate
        # Load project for dedupe_settings threshold
        _proj = await session.get(Project, project_id)
        _dedupe = ((_proj.meta or {}).get("dedupe_settings") or {}) if _proj else {}
        _max_dist = _dedupe.get("simhash_max_distance", 6)
        near_dup, dist = await find_near_duplicate(
            session, project_id, sh_hex,
            max_distance=_max_dist, exclude_id=candidate.id,
        )
        if near_dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "near_duplicate",
                    "duplicate_candidate_id": near_dup.id,
                    "distance": dist,
                    "message": f"Near-duplicate of candidate #{near_dup.id} (distance={dist})",
                },
            )

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

    # Resolve destination
    dest = None
    if body.destination_id:
        dest = next((d for d in project.destinations if d.id == body.destination_id), None)
        if not dest:
            raise HTTPException(
                status_code=404,
                detail=f"Destination #{body.destination_id} not found in this project",
            )
        if not dest.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Destination #{body.destination_id} is not active",
            )
    else:
        dest = next((d for d in project.destinations if d.is_active), None)
        if not dest:
            raise HTTPException(status_code=400, detail="No active destination found")

    # For GENERATE candidates, load brief data into task metadata
    is_generate = candidate.origin == CandidateOrigin.generate.value
    task_meta = None
    if is_generate:
        brief = await session.get(Brief, candidate.brief_id) if candidate.brief_id else None
        task_meta = {
            "origin": "GENERATE",
            "candidate_meta": candidate.meta or {},
            "brief": {
                "id": brief.id,
                "title": brief.title,
                "topic": brief.topic,
                "style": brief.style,
                "tone": brief.tone,
                "language": brief.language,
                "target_duration_sec": brief.target_duration_sec,
                "target_platform": brief.target_platform,
                "llm_prompt_template": brief.llm_prompt_template,
            } if brief else {},
        }

    # Create PublishTask
    task = PublishTask(
        project_id=project_id,
        platform=dest.platform,
        destination_social_account_id=dest.social_account_id,
        external_id=candidate.platform_video_id,
        permalink=candidate.url if not is_generate else None,
        preview_url=candidate.thumbnail_url,
        download_url=candidate.url if not is_generate else None,
        caption_text=candidate.caption or candidate.title,
        status="queued",
        preset_id=project.preset_id,
        total_steps=0,
        artifacts=task_meta,
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
        destination_platform=dest.platform,
        destination_account_id=dest.social_account_id,
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


# ── Sync sources into feed ─────────────────────────────────────

async def _get_subscribers(session: AsyncSession, account_id: int, platform: str) -> int | None:
    """Get subscriber/follower count for an account."""
    if platform == "TikTok":
        profile = await session.scalar(select(TikTokProfile).where(TikTokProfile.account_id == account_id))
        return profile.followers if profile else None
    elif platform == "YouTube":
        channel = await session.scalar(select(YouTubeChannel).where(YouTubeChannel.account_id == account_id))
        return channel.subscribers if channel else None
    elif platform == "VK":
        profile = await session.scalar(select(VKProfile).where(VKProfile.account_id == account_id))
        return profile.members_count or profile.followers_count if profile else None
    elif platform == "Instagram":
        profile = await session.scalar(select(InstagramProfile).where(InstagramProfile.account_id == account_id))
        return profile.followers if profile else None
    return None


async def _upsert_candidate(
    session: AsyncSession,
    project_id: int,
    platform: str,
    platform_video_id: str,
    *,
    url: str | None,
    author: str | None,
    title: str | None,
    caption: str | None,
    thumbnail_url: str | None,
    published_at: datetime | None,
    views: int | None,
    likes: int | None,
    comments: int | None,
    shares: int | None,
    subscribers: int | None,
) -> tuple[Candidate, bool]:
    """Upsert a candidate. Returns (candidate, is_new)."""
    res = await session.execute(
        select(Candidate).where(
            Candidate.project_id == project_id,
            Candidate.platform == platform,
            Candidate.platform_video_id == platform_video_id,
        )
    )
    candidate = res.scalar_one_or_none()
    is_new = candidate is None

    if is_new:
        candidate = Candidate(
            project_id=project_id,
            platform=platform,
            platform_video_id=platform_video_id,
            status=CandidateStatus.new.value,
        )

    candidate.url = url
    candidate.author = author
    candidate.title = title
    candidate.caption = caption
    candidate.thumbnail_url = thumbnail_url
    candidate.published_at = published_at
    candidate.views = views
    candidate.likes = likes
    candidate.comments = comments
    candidate.shares = shares
    candidate.subscribers = subscribers
    _vr = calculate_virality_score(
        views=views, likes=likes, comments=comments, shares=shares,
        published_at=published_at, subscribers=subscribers,
    )
    candidate.virality_score = _vr.score
    candidate.virality_factors = _vr.factors

    # Compute content signature for deduplication
    sig, sig_source = compute_candidate_signature(candidate)
    if sig:
        meta = candidate.meta or {}
        meta["content_signature"] = sig
        meta["content_signature_source"] = sig_source
        candidate.meta = meta

    # Compute simhash for near-duplicate detection
    from app.services.dedupe import extract_candidate_text
    cand_text, _ = extract_candidate_text(candidate)
    if cand_text:
        sh = compute_text_simhash(cand_text)
        meta = candidate.meta or {}
        meta["content_simhash64"] = simhash_to_hex(sh)
        meta["content_simhash_source"] = sig_source
        candidate.meta = meta

    # Extract topic tags + signature for topic anti-repeat guard
    ensure_candidate_topic_meta(candidate)

    session.add(candidate)
    return candidate, is_new


async def _sync_tiktok_source(session: AsyncSession, project_id: int, source: ProjectSource) -> tuple[int, int]:
    """Sync TikTok videos from a source account into candidates. Returns (added, updated)."""
    added, updated = 0, 0
    account_id = source.social_account_id
    subs = await _get_subscribers(session, account_id, "TikTok")
    account = await session.get(SocialAccount, account_id)
    author = account.handle if account else None

    res = await session.execute(
        select(TikTokVideo).where(TikTokVideo.account_id == account_id).order_by(TikTokVideo.published_at.desc().nullslast())
    )
    for video in res.scalars().all():
        _, is_new = await _upsert_candidate(
            session, project_id, "TikTok", video.video_id,
            url=video.permalink, author=author, title=video.title, caption=video.title,
            thumbnail_url=video.thumbnail_url, published_at=video.published_at,
            views=video.views, likes=video.likes, comments=video.comments,
            shares=video.shares, subscribers=subs,
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated


async def _sync_youtube_source(session: AsyncSession, project_id: int, source: ProjectSource) -> tuple[int, int]:
    added, updated = 0, 0
    account_id = source.social_account_id
    subs = await _get_subscribers(session, account_id, "YouTube")
    account = await session.get(SocialAccount, account_id)
    author = account.handle if account else None

    res = await session.execute(
        select(YouTubeVideo).where(YouTubeVideo.account_id == account_id).order_by(YouTubeVideo.published_at.desc().nullslast())
    )
    for video in res.scalars().all():
        _, is_new = await _upsert_candidate(
            session, project_id, "YouTube", video.video_id,
            url=video.permalink, author=author, title=video.title, caption=video.description,
            thumbnail_url=video.thumbnail_url, published_at=video.published_at,
            views=video.views, likes=video.likes, comments=video.comments,
            shares=None, subscribers=subs,
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated


async def _sync_vk_source(session: AsyncSession, project_id: int, source: ProjectSource) -> tuple[int, int]:
    added, updated = 0, 0
    account_id = source.social_account_id
    subs = await _get_subscribers(session, account_id, "VK")
    account = await session.get(SocialAccount, account_id)
    author = account.handle if account else None

    res = await session.execute(
        select(VKVideo).where(VKVideo.account_id == account_id).order_by(VKVideo.published_at.desc().nullslast())
    )
    for video in res.scalars().all():
        vid_id = video.vk_full_id or f"{video.vk_owner_id}_{video.video_id}"
        _, is_new = await _upsert_candidate(
            session, project_id, "VK", vid_id,
            url=video.permalink, author=author, title=video.title, caption=video.description,
            thumbnail_url=video.thumbnail_url, published_at=video.published_at,
            views=video.views, likes=video.likes, comments=video.comments,
            shares=video.reposts, subscribers=subs,
        )
        if is_new:
            added += 1
        else:
            updated += 1

    # Also sync VK clips
    res = await session.execute(
        select(VKClip).where(VKClip.account_id == account_id).order_by(VKClip.published_at.desc().nullslast())
    )
    for clip in res.scalars().all():
        clip_id = f"clip_{clip.vk_owner_id}_{clip.clip_id}"
        _, is_new = await _upsert_candidate(
            session, project_id, "VK", clip_id,
            url=clip.permalink, author=author, title=clip.title, caption=clip.description,
            thumbnail_url=clip.thumbnail_url, published_at=clip.published_at,
            views=clip.views, likes=clip.likes, comments=clip.comments,
            shares=getattr(clip, "reposts", None), subscribers=subs,
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated


async def _sync_instagram_source(session: AsyncSession, project_id: int, source: ProjectSource) -> tuple[int, int]:
    added, updated = 0, 0
    account_id = source.social_account_id
    subs = await _get_subscribers(session, account_id, "Instagram")
    account = await session.get(SocialAccount, account_id)
    author = account.handle if account else None

    res = await session.execute(
        select(InstagramPost).where(InstagramPost.account_id == account_id).order_by(InstagramPost.published_at.desc().nullslast())
    )
    for post in res.scalars().all():
        _, is_new = await _upsert_candidate(
            session, project_id, "Instagram", post.post_id,
            url=post.permalink, author=author, title=None, caption=post.caption,
            thumbnail_url=post.thumbnail_url, published_at=post.published_at,
            views=post.views, likes=post.likes, comments=post.comments,
            shares=None, subscribers=subs,
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated


_PLATFORM_SYNCERS = {
    "TikTok": _sync_tiktok_source,
    "YouTube": _sync_youtube_source,
    "VK": _sync_vk_source,
    "Instagram": _sync_instagram_source,
}


@router.post("/projects/{project_id}/sync-sources")
async def sync_project_sources(
    project_id: int,
    session: AsyncSession = SessionDep,
):
    """Sync all project sources into the candidate feed.

    Reads existing platform videos (TikTok, YouTube, VK, Instagram) from
    each ProjectSource account, upserts into Candidate table, and recalculates
    virality scores.
    """
    res = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.sources))
    )
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.sources:
        raise HTTPException(status_code=400, detail="Project has no sources configured")

    total_added = 0
    total_updated = 0
    source_results = []

    for source in project.sources:
        if not source.is_active:
            continue
        syncer = _PLATFORM_SYNCERS.get(source.platform)
        if not syncer:
            source_results.append({
                "source_id": source.id,
                "platform": source.platform,
                "account_id": source.social_account_id,
                "status": "skipped",
                "reason": f"Unsupported platform: {source.platform}",
            })
            continue
        try:
            added, updated = await syncer(session, project_id, source)
            total_added += added
            total_updated += updated
            source_results.append({
                "source_id": source.id,
                "platform": source.platform,
                "account_id": source.social_account_id,
                "status": "ok",
                "added": added,
                "updated": updated,
            })
        except Exception as exc:
            source_results.append({
                "source_id": source.id,
                "platform": source.platform,
                "account_id": source.social_account_id,
                "status": "error",
                "error": str(exc),
            })

    await session.commit()

    # Get top-5 by virality_score
    top5_res = await session.execute(
        select(Candidate)
        .where(Candidate.project_id == project_id)
        .order_by(Candidate.virality_score.desc().nullslast())
        .limit(5)
    )
    top5 = [
        {
            "id": c.id,
            "platform": c.platform,
            "author": c.author,
            "title": c.title,
            "virality_score": c.virality_score,
            "views": c.views,
            "status": c.status,
        }
        for c in top5_res.scalars().all()
    ]

    return {
        "project_id": project_id,
        "total_added": total_added,
        "total_updated": total_updated,
        "sources": source_results,
        "top5": top5,
    }
