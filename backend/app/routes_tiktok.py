from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import SocialAccount, SocialPlatform, TikTokProfile, TikTokVideo
from app.services.tiktok_sync import sync_tiktok_account
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["tiktok"])

SessionDep = Depends(get_session)


def _require_apify() -> None:
    if not get_settings().apify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="APIFY_TOKEN missing")


@router.post("/accounts/{account_id}/tiktok/sync")
async def tiktok_sync(account_id: int, session: AsyncSession = SessionDep):
    _require_apify()
    account = await session.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    account.sync_status = "running"
    session.add(account)
    await session.commit()
    try:
        return await sync_tiktok_account(session, account)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TikTok sync failed", "reason": str(exc)},
        ) from exc


@router.get("/accounts/{account_id}/tiktok/profile")
async def tiktok_profile(account_id: int, session: AsyncSession = SessionDep):
    profile = await session.scalar(select(TikTokProfile).where(TikTokProfile.account_id == account_id))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not synced")
    return {
        "account_id": account_id,
        "username": profile.username,
        "display_name": profile.display_name,
        "avatar_url": profile.avatar_url,
        "followers": profile.followers,
        "following": profile.following,
        "likes_total": profile.likes_total,
        "posts_total": profile.posts_total,
        "last_synced_at": profile.last_synced_at.isoformat() if profile.last_synced_at else None,
    }


@router.get("/accounts/{account_id}/tiktok/content")
async def tiktok_content(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    type: str = Query(default="all"),
    session: AsyncSession = SessionDep,
):
    if type not in {"all", "video"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid type filter")
    try:
        def _content_type(video: TikTokVideo) -> str:
            if video.duration_seconds is not None and video.duration_seconds <= 180:
                return "short"
            return "video"

        stmt = (
            select(TikTokVideo)
            .where(TikTokVideo.account_id == account_id)
            .order_by(TikTokVideo.published_at.desc(), TikTokVideo.video_id.desc())
            .limit(limit + 1)
        )
        if cursor:
            cursor_dt: datetime | None = None
            cursor_vid: str | None = None
            if "|" in cursor:
                cursor_dt_str, cursor_vid = cursor.split("|", 1)
                try:
                    cursor_dt = datetime.fromisoformat(cursor_dt_str.replace("Z", "+00:00"))
                except Exception:
                    cursor_dt = None
            else:
                try:
                    cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                except Exception:
                    cursor_dt = None

            if cursor_dt and cursor_vid:
                stmt = stmt.where(
                    (TikTokVideo.published_at < cursor_dt)
                    | ((TikTokVideo.published_at == cursor_dt) & (TikTokVideo.video_id < cursor_vid))
                )
            elif cursor_dt:
                stmt = stmt.where(TikTokVideo.published_at < cursor_dt)
            elif cursor_vid:
                stmt = stmt.where(TikTokVideo.video_id < cursor_vid)
        result = await session.execute(stmt)
        items = result.scalars().all()
        has_more = len(items) > limit
        items = items[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            last_time = last.published_at or datetime.now()
            next_cursor = f"{last_time.isoformat()}|{last.video_id}"
        return {
            "items": [
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "thumbnail_url": v.thumbnail_url,
                    "preview_url": v.thumbnail_url,
                    "published_at": v.published_at.isoformat() if v.published_at else None,
                    "duration_seconds": v.duration_seconds,
                    "content_type": _content_type(v),
                    "views": v.views,
                    "likes": v.likes,
                    "comments": v.comments,
                    "shares": v.shares,
                    "permalink": v.permalink,
                    "download_url": v.video_url,
                    "media_url": v.video_url,
                    "has_download": bool(v.video_url),
                }
                for v in items
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Failed to load TikTok content", "reason": str(exc)},
        ) from exc
