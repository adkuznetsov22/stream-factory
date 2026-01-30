from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import InstagramPost, InstagramProfile, SocialAccount, SocialPlatform
from app.services.instagram_sync import sync_instagram_account
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["instagram"])

SessionDep = Depends(get_session)


def _require_apify() -> None:
    if not get_settings().apify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="APIFY_TOKEN missing")


@router.post("/accounts/{account_id}/instagram/sync")
async def instagram_sync(account_id: int, session: AsyncSession = SessionDep):
    _require_apify()
    account = await session.get(SocialAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    account.sync_status = "running"
    session.add(account)
    await session.commit()
    try:
        return await sync_instagram_account(session, account)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Instagram sync failed", "reason": str(exc)},
        ) from exc


@router.get("/accounts/{account_id}/instagram/profile")
async def instagram_profile(account_id: int, session: AsyncSession = SessionDep):
    profile = await session.scalar(select(InstagramProfile).where(InstagramProfile.account_id == account_id))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not synced")
    return {
        "account_id": account_id,
        "username": profile.username,
        "full_name": profile.full_name,
        "avatar_url": profile.avatar_url,
        "followers": profile.followers,
        "following": profile.following,
        "posts_total": profile.posts_total,
        "last_synced_at": profile.last_synced_at.isoformat() if profile.last_synced_at else None,
    }


@router.get("/accounts/{account_id}/instagram/content")
async def instagram_content(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    type: str = Query(default="all"),
    session: AsyncSession = SessionDep,
):
    if type not in {"all", "post", "reel", "video"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid type filter")
    try:
        def _content_type_from_media(media_type: str | None, raw: dict | None) -> str:
            if media_type:
                mt = media_type.lower()
                if "reel" in mt or "video" in mt:
                    return "video"
                if "carousel" in mt or "sidecar" in mt:
                    return "carousel"
                if "post" in mt or "photo" in mt or "image" in mt:
                    return "photo"
            if raw and isinstance(raw, dict):
                if raw.get("is_video") is True:
                    return "video"
                if raw.get("children") or raw.get("carousel_media"):
                    return "carousel"
            return "unknown"

        stmt = (
            select(InstagramPost)
            .where(InstagramPost.account_id == account_id)
            .order_by(InstagramPost.published_at.desc(), InstagramPost.post_id.desc())
            .limit(limit + 1)
        )
        if type != "all":
            stmt = stmt.where(InstagramPost.media_type == type)

        cursor_time: datetime | None = None
        cursor_post: str | None = None
        if cursor:
            if "|" in cursor:
                cursor_time_str, cursor_post = cursor.split("|", 1)
                try:
                    cursor_time = datetime.fromisoformat(cursor_time_str.replace("Z", "+00:00"))
                except Exception:
                    cursor_time = None
            else:
                try:
                    cursor_time = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                except Exception:
                    cursor_time = None
        if cursor_time and cursor_post:
            stmt = stmt.where(
                (InstagramPost.published_at < cursor_time)
                | ((InstagramPost.published_at == cursor_time) & (InstagramPost.post_id < cursor_post))
            )
        elif cursor_time:
            stmt = stmt.where(InstagramPost.published_at < cursor_time)
        elif cursor_post:
            stmt = stmt.where(InstagramPost.post_id < cursor_post)

        result = await session.execute(stmt)
        items = result.scalars().all()
        has_more = len(items) > limit
        items = items[:limit]

        # published_at fallback to now for output
        now_iso = datetime.now().astimezone().isoformat()
        serialized = [
            {
                "post_id": p.post_id,
                "caption": p.caption,
                "published_at": (p.published_at.isoformat() if p.published_at else now_iso),
                "media_type": p.media_type,
                "content_type": _content_type_from_media(p.media_type, p.raw),
                "views": p.views,
                "likes": p.likes,
                "comments": p.comments,
                "thumbnail_url": p.thumbnail_url,
                "preview_url": p.thumbnail_url or p.media_url,
                "media_url": p.media_url,
                "download_url": p.media_url if p.media_url else None,
                "has_download": bool(p.media_url),
                "permalink": p.permalink,
            }
            for p in items
        ]

        next_cursor = None
        if has_more and serialized:
            last_item = serialized[-1]
            next_cursor = f"{last_item['published_at']}|{last_item['post_id']}"

        return {
            "items": serialized,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Failed to load Instagram content", "reason": str(exc)},
        ) from exc
