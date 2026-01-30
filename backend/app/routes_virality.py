"""
Virality API endpoints

Provides endpoints for fetching top viral content across platforms.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    InstagramPost,
    ProjectSource,
    TikTokVideo,
    VKClip,
    VKVideo,
    YouTubeVideo,
)

router = APIRouter(prefix="/api", tags=["virality"])

SessionDep = Depends(get_session)


@router.get("/videos/top")
async def get_top_videos(
    session: AsyncSession = SessionDep,
    platform: str | None = Query(None, description="Filter by platform: youtube, tiktok, vk, instagram"),
    project_id: int | None = Query(None, description="Filter by project sources"),
    limit: int = Query(50, ge=1, le=200),
    include_used: bool = Query(False, description="Include already used videos"),
    min_score: float | None = Query(None, description="Minimum virality score"),
):
    """
    Get top videos sorted by virality score.
    
    Supports filtering by:
    - platform (youtube, tiktok, vk, instagram)
    - project_id (only videos from project sources)
    - min_score (minimum virality score threshold)
    - include_used (whether to include already used videos)
    """
    results = []
    
    # Get source account IDs if filtering by project
    source_account_ids: set[int] | None = None
    if project_id:
        sources = await session.execute(
            select(ProjectSource.social_account_id).where(
                ProjectSource.project_id == project_id,
                ProjectSource.is_active == True,
            )
        )
        source_account_ids = set(row[0] for row in sources.fetchall())
        if not source_account_ids:
            return {"items": [], "total": 0}
    
    platforms = [platform.lower()] if platform else ["youtube", "tiktok", "vk", "instagram"]
    
    for plat in platforms:
        if plat == "youtube":
            query = select(YouTubeVideo).where(YouTubeVideo.virality_score.isnot(None))
            if source_account_ids:
                query = query.where(YouTubeVideo.account_id.in_(source_account_ids))
            if not include_used:
                query = query.where(YouTubeVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(YouTubeVideo.virality_score >= min_score)
            query = query.order_by(YouTubeVideo.virality_score.desc()).limit(limit)
            rows = await session.execute(query)
            for video in rows.scalars():
                results.append({
                    "platform": "youtube",
                    "id": video.id,
                    "video_id": video.video_id,
                    "account_id": video.account_id,
                    "title": video.title,
                    "views": video.views,
                    "likes": video.likes,
                    "comments": video.comments,
                    "published_at": video.published_at.isoformat() if video.published_at else None,
                    "thumbnail_url": video.thumbnail_url,
                    "permalink": video.permalink,
                    "virality_score": video.virality_score,
                    "used_in_task_id": video.used_in_task_id,
                    "content_type": video.content_type,
                })
        
        elif plat == "tiktok":
            query = select(TikTokVideo).where(TikTokVideo.virality_score.isnot(None))
            if source_account_ids:
                query = query.where(TikTokVideo.account_id.in_(source_account_ids))
            if not include_used:
                query = query.where(TikTokVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(TikTokVideo.virality_score >= min_score)
            query = query.order_by(TikTokVideo.virality_score.desc()).limit(limit)
            rows = await session.execute(query)
            for video in rows.scalars():
                results.append({
                    "platform": "tiktok",
                    "id": video.id,
                    "video_id": video.video_id,
                    "account_id": video.account_id,
                    "title": video.title,
                    "views": video.views,
                    "likes": video.likes,
                    "comments": video.comments,
                    "shares": video.shares,
                    "published_at": video.published_at.isoformat() if video.published_at else None,
                    "thumbnail_url": video.thumbnail_url,
                    "permalink": video.permalink,
                    "virality_score": video.virality_score,
                    "used_in_task_id": video.used_in_task_id,
                })
        
        elif plat == "vk":
            # VK Videos
            query = select(VKVideo).where(VKVideo.virality_score.isnot(None))
            if source_account_ids:
                query = query.where(VKVideo.account_id.in_(source_account_ids))
            if not include_used:
                query = query.where(VKVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(VKVideo.virality_score >= min_score)
            query = query.order_by(VKVideo.virality_score.desc()).limit(limit)
            rows = await session.execute(query)
            for video in rows.scalars():
                results.append({
                    "platform": "vk",
                    "type": "video",
                    "id": video.id,
                    "video_id": video.video_id,
                    "account_id": video.account_id,
                    "title": video.title,
                    "views": video.views,
                    "likes": video.likes,
                    "comments": video.comments,
                    "reposts": video.reposts,
                    "published_at": video.published_at.isoformat() if video.published_at else None,
                    "thumbnail_url": video.thumbnail_url,
                    "permalink": video.permalink,
                    "virality_score": video.virality_score,
                    "used_in_task_id": video.used_in_task_id,
                })
            
            # VK Clips
            query = select(VKClip).where(VKClip.virality_score.isnot(None))
            if source_account_ids:
                query = query.where(VKClip.account_id.in_(source_account_ids))
            if not include_used:
                query = query.where(VKClip.used_in_task_id.is_(None))
            if min_score:
                query = query.where(VKClip.virality_score >= min_score)
            query = query.order_by(VKClip.virality_score.desc()).limit(limit)
            rows = await session.execute(query)
            for clip in rows.scalars():
                results.append({
                    "platform": "vk",
                    "type": "clip",
                    "id": clip.id,
                    "clip_id": clip.clip_id,
                    "account_id": clip.account_id,
                    "title": clip.title,
                    "views": clip.views,
                    "likes": clip.likes,
                    "comments": clip.comments,
                    "reposts": clip.reposts,
                    "published_at": clip.published_at.isoformat() if clip.published_at else None,
                    "thumbnail_url": clip.thumbnail_url,
                    "permalink": clip.permalink,
                    "virality_score": clip.virality_score,
                    "used_in_task_id": clip.used_in_task_id,
                })
        
        elif plat == "instagram":
            query = select(InstagramPost).where(InstagramPost.virality_score.isnot(None))
            if source_account_ids:
                query = query.where(InstagramPost.account_id.in_(source_account_ids))
            if not include_used:
                query = query.where(InstagramPost.used_in_task_id.is_(None))
            if min_score:
                query = query.where(InstagramPost.virality_score >= min_score)
            query = query.order_by(InstagramPost.virality_score.desc()).limit(limit)
            rows = await session.execute(query)
            for post in rows.scalars():
                results.append({
                    "platform": "instagram",
                    "id": post.id,
                    "post_id": post.post_id,
                    "account_id": post.account_id,
                    "caption": post.caption[:200] if post.caption else None,
                    "media_type": post.media_type,
                    "views": post.views,
                    "likes": post.likes,
                    "comments": post.comments,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "thumbnail_url": post.thumbnail_url,
                    "permalink": post.permalink,
                    "virality_score": post.virality_score,
                    "used_in_task_id": post.used_in_task_id,
                })
    
    # Sort all results by virality score
    results.sort(key=lambda x: x.get("virality_score") or 0, reverse=True)
    results = results[:limit]
    
    return {
        "items": results,
        "total": len(results),
    }


@router.get("/projects/{project_id}/viral-content")
async def get_project_viral_content(
    project_id: int,
    session: AsyncSession = SessionDep,
    limit: int = Query(50, ge=1, le=200),
    new_ratio: float = Query(0.6, ge=0, le=1, description="Ratio of new videos vs top historical"),
    min_score: float | None = Query(None),
):
    """
    Get viral content for a project with mix of new and top historical.
    
    - new_ratio=0.6 means 60% recent videos, 40% all-time top
    """
    new_limit = int(limit * new_ratio)
    top_limit = limit - new_limit
    
    # Get all top videos for this project
    all_videos = await get_top_videos(
        session=session,
        project_id=project_id,
        limit=limit * 2,  # Get more to filter
        include_used=False,
        min_score=min_score,
    )
    
    items = all_videos["items"]
    
    # Split into new (last 7 days) and historical
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    
    new_items = []
    historical_items = []
    
    for item in items:
        pub = item.get("published_at")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pub_dt > cutoff:
                    new_items.append(item)
                else:
                    historical_items.append(item)
            except:
                historical_items.append(item)
        else:
            historical_items.append(item)
    
    # Mix according to ratio
    result = new_items[:new_limit] + historical_items[:top_limit]
    result.sort(key=lambda x: x.get("virality_score") or 0, reverse=True)
    
    return {
        "items": result[:limit],
        "total": len(result[:limit]),
        "new_count": len(new_items[:new_limit]),
        "historical_count": len(historical_items[:top_limit]),
    }
