from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import SocialAccount, SocialPlatform, YouTubeChannel, YouTubeVideo
from app.services.youtube_sync import sync_youtube_account
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["youtube"])

SessionDep = Depends(get_session)


def _require_key() -> None:
    if not get_settings().youtube_api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YOUTUBE_API_KEY missing")


@router.post("/accounts/{account_id}/youtube/sync")
async def sync_account(account_id: int, session: AsyncSession = SessionDep):
    _require_key()
    account = await session.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    try:
        result = await sync_youtube_account(session, account)
    except HTTPException:
        raise
    except Exception as exc:
        # глобальный handler залогирует stacktrace, клиенту вернем JSON
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "YouTube sync failed", "reason": str(exc)},
        ) from exc
    return {"ok": True, **result}


@router.post("/youtube/sync_all")
async def sync_all(session: AsyncSession = SessionDep):
    _require_key()
    result = await session.execute(select(SocialAccount).where(SocialAccount.platform == SocialPlatform.youtube.value))
    accounts = result.scalars().all()
    total = len(accounts)
    synced = 0
    failed: list[dict] = []
    for account in accounts:
        try:
            await sync_youtube_account(session, account)
            synced += 1
        except HTTPException as exc:
            failed.append({"account_id": account.id, "error": exc.detail})
        except Exception:
            failed.append({"account_id": account.id, "error": "unexpected error"})
    return {"total": total, "synced": synced, "failed": failed}


@router.get("/accounts/{account_id}/youtube/profile")
async def youtube_profile(account_id: int, session: AsyncSession = SessionDep):
    channel = await session.get(YouTubeChannel, account_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not synced")
    return {
        "account_id": account_id,
        "channel_id": channel.channel_id,
        "title": channel.title,
        "description": channel.description,
        "thumbnail_url": channel.thumbnail_url,
        "banner_url": channel.banner_url,
        "handle": channel.handle,
        "country": channel.country,
        "subscribers": channel.subscribers,
        "views_total": channel.views_total,
        "videos_total": channel.videos_total,
        "last_synced_at": channel.last_synced_at.isoformat() if channel.last_synced_at else None,
    }


def _build_content_stmt(
    account_id: int,
    content_type: str,
    cursor: str | None,
    limit: int,
):
    stmt = (
        select(YouTubeVideo)
        .where(YouTubeVideo.account_id == account_id)
        .order_by(YouTubeVideo.published_at.desc(), YouTubeVideo.video_id.desc())
    )
    if content_type != "all":
        stmt = stmt.where(YouTubeVideo.content_type == content_type)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            stmt = stmt.where(YouTubeVideo.published_at < cursor_dt)
        except Exception:
            pass
    return stmt.limit(limit + 1)


def _serialize_video(v: YouTubeVideo) -> dict:
    return {
        "video_id": v.video_id,
        "title": v.title,
        "thumbnail_url": v.thumbnail_url,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "duration_seconds": v.duration_seconds,
        "views": v.views,
        "likes": v.likes,
        "comments": v.comments,
        "privacy_status": v.privacy_status,
        "content_type": v.content_type,
        "live_status": v.live_status or "none",
        "scheduled_start_at": v.scheduled_start_at.isoformat() if v.scheduled_start_at else None,
        "actual_start_at": v.actual_start_at.isoformat() if v.actual_start_at else None,
        "actual_end_at": v.actual_end_at.isoformat() if v.actual_end_at else None,
        "permalink": v.permalink,
    }


@router.get("/accounts/{account_id}/youtube/content")
async def youtube_content(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    type: str = Query(default="all"),
    session: AsyncSession = SessionDep,
):
    if type not in {"all", "video", "short", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid type filter")
    try:
        stmt = _build_content_stmt(account_id, type, cursor, limit)
        result = await session.execute(stmt)
        videos = result.scalars().all()
        has_more = len(videos) > limit
        videos = videos[:limit]
        last_published = next((v.published_at for v in reversed(videos) if v.published_at), None)
        next_cursor = last_published.isoformat() if has_more and last_published else None
        return {
            "items": [_serialize_video(v) for v in videos],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Failed to load YouTube content", "reason": str(exc)},
        ) from exc


@router.get("/accounts/{account_id}/youtube/videos")
async def youtube_videos(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    type: str = Query(default="all"),
    session: AsyncSession = SessionDep,
):
    # alias to content endpoint for backward compatibility
    return await youtube_content(account_id=account_id, limit=limit, cursor=cursor, type=type, session=session)
