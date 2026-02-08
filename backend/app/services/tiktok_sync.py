from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.apify_client import run_actor_get_items
from app.models import SocialAccount, SocialPlatform, TikTokProfile, TikTokVideo
from app.services.virality import calculate_virality_for_tiktok

ACTOR_TIKTOK = "clockworks/tiktok-scraper"
DEFAULT_RESULTS_PER_PAGE = 30
DEFAULT_MAX_ITEMS = 200


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


def _parse_unix(val: Any) -> datetime | None:
    try:
        ts = int(val)
    except Exception:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _build_profile_url(account: SocialAccount) -> str:
    if account.url and "tiktok.com" in account.url:
        url = account.url.strip()
        if "@" in url:
            return url
        slug = url.split("/")[-1] or account.login
        slug = slug.lstrip("@")
        return f"https://www.tiktok.com/@{slug}"
    slug = (account.login or account.handle or "").strip()
    slug = slug.lstrip("@")
    return f"https://www.tiktok.com/@{slug}"


async def sync_tiktok_account(session: AsyncSession, account: SocialAccount) -> dict:
    if account.platform != SocialPlatform.tiktok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not TikTok")
    if not account.login:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TikTok login is empty")

    now = datetime.now(timezone.utc)
    status_value = "ok"
    sync_error: str | None = None

    profile_url = _build_profile_url(account)
    input_payload = {
        "profiles": [profile_url],
        "resultsPerPage": DEFAULT_RESULTS_PER_PAGE,
        "maxItems": DEFAULT_MAX_ITEMS,
    }

    try:
        items = await run_actor_get_items(ACTOR_TIKTOK, input_payload)
    except HTTPException as exc:
        account.sync_status = "error"
        account.sync_error = str(exc.detail)
        account.last_synced_at = now
        session.add(account)
        await session.commit()
        raise
    except Exception as exc:
        account.sync_status = "error"
        account.sync_error = f"TikTok sync failed: {exc}"
        account.last_synced_at = now
        session.add(account)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TikTok sync failed", "reason": str(exc)},
        ) from exc

    profile_data = None
    author_stats = None
    if items:
        candidate = items[0]
        profile_data = (
            candidate.get("authorMeta")
            or candidate.get("author")
            or candidate.get("user")
            or candidate.get("authorInfo")
        )
        author_stats = candidate.get("authorStats") or (profile_data or {}).get("stats") if profile_data else None
    if profile_data:
        profile = await session.scalar(select(TikTokProfile).where(TikTokProfile.account_id == account.id))
        if not profile:
            profile = TikTokProfile(account_id=account.id)
        profile.username = profile_data.get("uniqueId") or profile_data.get("id") or account.login
        profile.display_name = profile_data.get("nickname") or profile_data.get("name")
        profile.avatar_url = (
            profile_data.get("avatarThumb")
            or profile_data.get("avatarLarger")
            or profile_data.get("avatarMedium")
            or profile_data.get("avatar")
        )
        stats = author_stats or {}
        profile.followers = _parse_int(stats.get("followerCount"))
        profile.following = _parse_int(stats.get("followingCount"))
        profile.likes_total = _parse_int(stats.get("heartCount") or stats.get("diggCount"))
        profile.posts_total = _parse_int(stats.get("videoCount"))
        profile.raw = profile_data
        profile.last_synced_at = now
        session.add(profile)

    synced = 0
    for item in items:
        video_id = item.get("id") or item.get("video_id")
        if not video_id:
            continue
        result = await session.execute(
            select(TikTokVideo).where(TikTokVideo.account_id == account.id, TikTokVideo.video_id == video_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            video = TikTokVideo(account_id=account.id, video_id=video_id)
        video.title = item.get("text") or item.get("desc") or item.get("title")
        video.published_at = (
            _parse_dt(item.get("createTimeISO"))
            or _parse_unix(item.get("createTime"))
            or _parse_dt(item.get("published_at"))
            or now
        )

        video_meta = item.get("videoMeta") or item.get("video") or {}
        duration = _parse_int(video_meta.get("duration") or item.get("duration"))
        if duration and duration > 10000:
            duration = duration // 1000
        video.duration_seconds = duration

        stats = item.get("stats") or {}
        video.views = _parse_int(stats.get("playCount") or stats.get("plays") or stats.get("viewCount"))
        video.likes = _parse_int(stats.get("diggCount") or stats.get("likes") or stats.get("heartCount"))
        video.comments = _parse_int(stats.get("commentCount"))
        video.shares = _parse_int(stats.get("shareCount"))

        video.thumbnail_url = (
            video_meta.get("coverUrl")
            or video_meta.get("cover")
            or video_meta.get("thumbnailUrl")
            or video_meta.get("originCover")
            or video_meta.get("dynamicCover")
            or item.get("thumbnail_url")
        )

        subtitle_links = video_meta.get("subtitleLinks") or []
        subtitle_download = None
        for link in subtitle_links:
            subtitle_download = link.get("downloadLink") or link.get("tiktokLink")
            if subtitle_download:
                break

        video.video_url = (
            item.get("downloadLink")
            or item.get("tiktokLink")
            or video_meta.get("downloadAddr")
            or video_meta.get("downloadLink")
            or subtitle_download
        )

        video.permalink = (
            item.get("webVideoUrl")
            or item.get("permalink")
            or item.get("shareUrl")
            or item.get("link")
            or (
                (profile_data or {}).get("profileUrl")
                and f"{profile_data.get('profileUrl').rstrip('/')}/video/{video_id}"
            )
        )
        video.raw = item
        followers = profile.followers if profile_data else None
        _vr = calculate_virality_for_tiktok(video, followers)
        video.virality_score = _vr.score
        session.add(video)
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
        "login": account.login,
        "profile_url": profile_url,
    }
