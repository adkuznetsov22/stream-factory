from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import SocialAccount, SocialPlatform, VKClip, VKPost, VKProfile, VKVideo
from app.services.vk_sync import sync_vk_account
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["vk"])

SessionDep = Depends(get_session)


def _require_vk_key() -> None:
    if not get_settings().vk_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VK_ACCESS_TOKEN missing")


@router.post("/accounts/{account_id}/vk/sync")
async def sync_account(account_id: int, session: AsyncSession = SessionDep):
    account = await session.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if account.platform != SocialPlatform.vk:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not VK")
    _require_vk_key()
    try:
        result = await sync_vk_account(session, account)
        return result
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "VK sync failed", "reason": str(exc)},
        )


@router.get("/accounts/{account_id}/vk/profile")
async def vk_profile(account_id: int, session: AsyncSession = SessionDep):
    result = await session.execute(select(VKProfile).where(VKProfile.account_id == account_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not synced")
    return {
        "account_id": account_id,
        "vk_owner_id": profile.vk_owner_id,
        "screen_name": profile.screen_name,
        "name": profile.name,
        "photo_200": profile.photo_200,
        "is_group": profile.is_group,
        "country": profile.country,
        "description": profile.description,
        "members_count": profile.members_count,
        "followers_count": profile.followers_count,
        "last_synced_at": profile.last_synced_at.isoformat() if profile.last_synced_at else None,
    }


@router.get("/accounts/{account_id}/vk/posts")
async def vk_posts(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
):
    stmt = (
        select(VKPost)
        .where(VKPost.account_id == account_id)
        .order_by(VKPost.published_at.desc(), VKPost.post_id.desc())
    )
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            stmt = stmt.where(VKPost.published_at < cursor_dt)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    result = await session.execute(stmt)
    posts = result.scalars().all()
    has_more = len(posts) > limit
    posts = posts[:limit]
    next_cursor = posts[-1].published_at.isoformat() if has_more and posts else None
    return {
        "items": [
            {
                "post_id": p.post_id,
                "vk_owner_id": p.vk_owner_id,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "text": p.text,
                "permalink": p.permalink,
                "views": p.views,
                "likes": p.likes,
                "reposts": p.reposts,
                "comments": p.comments,
                "attachments_count": p.attachments_count,
            }
            for p in posts
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/accounts/{account_id}/vk/videos")
async def vk_videos(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
):
    try:
        stmt = (
            select(VKVideo)
            .where(VKVideo.account_id == account_id)
            .order_by(VKVideo.published_at.desc(), VKVideo.video_id.desc())
        )
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                stmt = stmt.where(VKVideo.published_at < cursor_dt)
            except Exception:
                pass
        stmt = stmt.limit(limit + 1)
        result = await session.execute(stmt)
        videos = result.scalars().all()
        has_more = len(videos) > limit
        videos = videos[:limit]
        next_cursor = videos[-1].published_at.isoformat() if has_more and videos else None
        return {
            "items": [
                {
                    "video_id": v.video_id,
                    "vk_owner_id": v.vk_owner_id,
                    "title": v.title,
                    "description": v.description,
                    "published_at": v.published_at.isoformat() if v.published_at else None,
                    "duration_seconds": v.duration_seconds,
                    "views": v.views,
                    "likes": v.likes,
                    "comments": v.comments,
                    "reposts": v.reposts,
                    "thumbnail_url": v.thumbnail_url,
                    "permalink": v.permalink,
                }
                for v in videos
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "VK videos failed", "reason": str(exc)},
        )


@router.get("/accounts/{account_id}/vk/clips")
async def vk_clips(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
):
    try:
        stmt = (
            select(VKClip)
            .where(VKClip.account_id == account_id)
            .order_by(VKClip.published_at.desc(), VKClip.clip_id.desc())
        )
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                stmt = stmt.where(VKClip.published_at < cursor_dt)
            except Exception:
                pass
        stmt = stmt.limit(limit + 1)
        result = await session.execute(stmt)
        clips = result.scalars().all()
        has_more = len(clips) > limit
        clips = clips[:limit]
        next_cursor = clips[-1].published_at.isoformat() if has_more and clips else None
        return {
            "items": [
                {
                    "clip_id": c.clip_id,
                    "vk_owner_id": c.vk_owner_id,
                    "title": c.title,
                    "description": c.description,
                    "published_at": c.published_at.isoformat() if c.published_at else None,
                    "duration_seconds": c.duration_seconds,
                    "views": c.views,
                    "likes": c.likes,
                    "comments": c.comments,
                    "reposts": c.reposts,
                    "thumbnail_url": c.thumbnail_url,
                    "permalink": c.permalink,
                }
                for c in clips
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "VK clips failed", "reason": str(exc)},
        )


@router.get("/accounts/{account_id}/vk/content")
async def vk_content(
    account_id: int,
    type: str = Query(default="all"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: AsyncSession = SessionDep,
):
    if type not in {"all", "post", "video", "clip", "short_video"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid type")

    def map_post(p: VKPost) -> dict:
        return {
            "content_type": "post",
            "id": p.post_id,
            "owner_id": p.vk_owner_id,
            "title": (p.text or "")[:80] if p.text else "",
            "text": p.text,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "views": p.views,
            "likes": p.likes,
            "comments": p.comments,
            "reposts": p.reposts,
            "thumbnail_url": None,
            "permalink": p.permalink,
        }

    def map_video(v: VKVideo) -> dict:
        return {
            "content_type": "video",
            "id": v.video_id,
            "owner_id": v.vk_owner_id,
            "title": v.title,
            "text": v.description,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "views": v.views,
            "likes": v.likes,
            "comments": v.comments,
            "reposts": v.reposts,
            "thumbnail_url": v.thumbnail_url,
            "permalink": v.permalink,
        }

    def map_clip(c: VKClip) -> dict:
        return {
            "content_type": c.media_type or "clip",
            "id": c.clip_id,
            "owner_id": c.vk_owner_id,
            "title": c.title,
            "text": c.description,
            "published_at": c.published_at.isoformat() if c.published_at else None,
            "views": c.views,
            "likes": c.likes,
            "comments": c.comments,
            "reposts": c.reposts,
            "thumbnail_url": c.thumbnail_url,
            "permalink": c.permalink,
        }

    try:
        cursor_dt = None
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            except Exception:
                cursor_dt = None

        items: list[dict] = []
        if type in {"all", "post"}:
            stmt_posts = select(VKPost).where(VKPost.account_id == account_id).order_by(VKPost.published_at.desc(), VKPost.post_id.desc())
            if cursor_dt:
                stmt_posts = stmt_posts.where(VKPost.published_at < cursor_dt)
            posts_res = await session.execute(stmt_posts.limit(limit + 1))
            items.extend([map_post(p) for p in posts_res.scalars().all()])
        if type in {"all", "video"}:
            stmt_videos = select(VKVideo).where(VKVideo.account_id == account_id).order_by(VKVideo.published_at.desc(), VKVideo.video_id.desc())
            if cursor_dt:
                stmt_videos = stmt_videos.where(VKVideo.published_at < cursor_dt)
            videos_res = await session.execute(stmt_videos.limit(limit + 1))
            items.extend([map_video(v) for v in videos_res.scalars().all()])
        if type in {"all", "clip", "short_video"}:
            stmt_clips = select(VKClip).where(VKClip.account_id == account_id).order_by(VKClip.published_at.desc(), VKClip.clip_id.desc())
            if cursor_dt:
                stmt_clips = stmt_clips.where(VKClip.published_at < cursor_dt)
            clips_res = await session.execute(stmt_clips.limit(limit + 1))
            for c in clips_res.scalars().all():
                if type == "short_video" and c.media_type != "short_video":
                    continue
                if type == "clip" and c.media_type != "clip":
                    continue
                items.append(map_clip(c))

        items = [i for i in items if i.get("published_at")]
        items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        sliced = items[:limit]
        next_cursor = sliced[-1]["published_at"] if len(items) > limit else None
        return {"items": sliced, "next_cursor": next_cursor, "has_more": bool(next_cursor)}
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "VK content failed", "reason": str(exc)},
        )
