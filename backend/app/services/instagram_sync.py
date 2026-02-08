from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.apify_client import run_actor_and_get_dataset_items
from app.models import InstagramPost, InstagramProfile, SocialAccount, SocialPlatform
from app.services.virality import calculate_virality_for_instagram

ACTOR_INSTAGRAM = "scraper-engine/instagram-post-scraper"
DEFAULT_RESULTS_LIMIT = 30


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_int(val: Any) -> int | None:
    try:
        return int(val)
    except Exception:
        return None


def _media_type(value: str | None) -> str:
    if not value:
        return "unknown"
    v = value.lower()
    if "reel" in v:
        return "reel"
    if "video" in v:
        return "video"
    if "image" in v or "photo" in v:
        return "post"
    if "carousel" in v:
        return "post"
    return value


async def sync_instagram_account(session: AsyncSession, account: SocialAccount) -> dict:
    if account.platform != SocialPlatform.instagram:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not Instagram")
    if not account.login:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instagram login is empty")

    now = datetime.now(timezone.utc)
    status_value = "ok"
    sync_error: str | None = None

    profile_url = f"https://www.instagram.com/{account.login.strip().lstrip('@')}/"
    input_payload = {
        "startUrls": [{"url": profile_url}],
        "resultsLimit": DEFAULT_RESULTS_LIMIT,
    }

    try:
        items, meta = await run_actor_and_get_dataset_items(
            ACTOR_INSTAGRAM,
            input_payload,
            clean=True,
            limit=DEFAULT_RESULTS_LIMIT,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
        msg = str(detail)
        account.sync_status = "error"
        account.sync_error = msg
        account.last_synced_at = now
        session.add(account)
        await session.commit()
        # если actor не арендован — возвращаем читаемо
        if isinstance(detail, dict) and detail.get("body") and "actor-is-not-rented" in str(detail.get("body")):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "Actor is not rented. Rent it in Apify Console.",
                    "actor": ACTOR_INSTAGRAM,
                    "body": detail.get("body"),
                },
            ) from exc
        raise
    except Exception as exc:
        account.sync_status = "error"
        account.sync_error = f"Instagram sync failed: {exc}"
        account.last_synced_at = now
        session.add(account)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Instagram sync failed", "reason": str(exc)},
        ) from exc

    profile_data = None
    if items:
        # actor может отдавать профиль отдельно или в элементах
        if isinstance(items[0], dict) and items[0].get("profile"):
            profile_data = items[0].get("profile")
        else:
            # попытка вытащить owner поля из первого поста
            first = items[0]
            profile_data = {
                "username": first.get("ownerUsername") or first.get("username"),
                "full_name": first.get("ownerFullName") or first.get("full_name"),
                "profile_pic_url": first.get("ownerProfilePicUrl") or first.get("profile_pic_url") or first.get("profilePicUrl"),
                "follower_count": first.get("follower_count") or first.get("followers"),
                "following_count": first.get("following_count") or first.get("following"),
                "media_count": first.get("media_count") or first.get("postsCount"),
                "raw_owner": first.get("owner") or None,
            }

    profile = await session.scalar(select(InstagramProfile).where(InstagramProfile.account_id == account.id))
    if not profile:
        profile = InstagramProfile(account_id=account.id)
    profile.username = (profile_data or {}).get("username") or account.login
    profile.full_name = (profile_data or {}).get("full_name") or (profile_data or {}).get("ownerFullName")
    profile.avatar_url = (profile_data or {}).get("profile_pic_url")
    profile.followers = _parse_int((profile_data or {}).get("follower_count"))
    profile.following = _parse_int((profile_data or {}).get("following_count"))
    profile.posts_total = _parse_int((profile_data or {}).get("media_count"))
    profile.raw = profile_data
    profile.last_synced_at = now
    session.add(profile)

    synced = 0
    for item in items:
        post_id = item.get("id") or item.get("shortcode")
        if not post_id:
            continue
        result = await session.execute(
            select(InstagramPost).where(InstagramPost.account_id == account.id, InstagramPost.post_id == post_id)
        )
        post = result.scalar_one_or_none()
        if not post:
            post = InstagramPost(account_id=account.id, post_id=post_id)
        post.caption = item.get("caption") or item.get("title")
        ts = item.get("timestamp") or item.get("takenAt") or item.get("taken_at") or item.get("created_time")
        if isinstance(ts, (int, float)):
            post.published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        else:
            post.published_at = (
                _parse_dt(item.get("timestamp"))
                or _parse_dt(item.get("taken_at") or item.get("takenAt"))
                or _parse_dt(item.get("createdTime") or item.get("created_time"))
                or _parse_dt(item.get("date") or item.get("createdAt"))
                or _parse_dt(item.get("published_at"))
            )
        if not post.published_at:
            post.published_at = now
        post.media_type = _media_type(item.get("media_type") or item.get("type") or item.get("mediaType"))
        post.views = _parse_int(
            item.get("play_count") or item.get("video_view_count") or item.get("views") or item.get("view_count")
        )
        post.likes = _parse_int(item.get("like_count") or item.get("likes") or item.get("likes_count"))
        post.comments = _parse_int(item.get("comment_count") or item.get("comments") or item.get("comments_count"))
        post.thumbnail_url = (
            item.get("thumbnail_url")
            or item.get("thumbnailUrl")
            or item.get("displayUrl")
            or item.get("imageUrl")
            or item.get("display_url")
        )
        post.media_url = item.get("videoUrl") or item.get("video_url") or item.get("media_url") or item.get("displayUrl")
        post.permalink = (
            item.get("permalink")
            or (item.get("shortcode") and f"https://www.instagram.com/p/{item.get('shortcode')}/")
        )
        post.raw = item
        followers = profile.followers if profile else None
        _vr = calculate_virality_for_instagram(post, followers)
        post.virality_score = _vr.score
        session.add(post)
        synced += 1

    account.sync_status = status_value
    account.sync_error = sync_error
    account.last_synced_at = now
    session.add(account)
    await session.commit()

    return {
        "ok": True,
        "status": status_value,
        "error": sync_error,
        "synced_items": synced,
        "account_id": account.id,
    }
