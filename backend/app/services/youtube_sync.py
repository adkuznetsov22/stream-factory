from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.youtube_api import (
    fetch_channel_details,
    fetch_playlist_videos,
    fetch_videos_details,
    parse_youtube_channel_ref,
    resolve_channel_id,
)
from app.models import AccountMetricsDaily, SocialAccount, YouTubeChannel, YouTubeVideo
from app.services.virality import calculate_virality_for_youtube


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _classify_video(item: dict[str, Any]) -> tuple[str, str]:
    live_bc = (item.get("live_broadcast_content") or "").lower()
    live_details = item.get("live_streaming_details") or {}
    duration = item.get("duration_seconds")

    live_status = "none"
    if live_bc in {"upcoming", "live"}:
        live_status = live_bc
    elif live_details.get("actualEndTime"):
        live_status = "ended"
    elif live_details.get("actualStartTime"):
        live_status = "live"

    if live_status != "none":
        content_type = "live"
    elif duration is not None and duration <= 60:
        content_type = "short"
    else:
        content_type = "video"

    return content_type, live_status


async def sync_youtube_account(session: AsyncSession, account: SocialAccount) -> dict:
    if account.platform != "YouTube":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not YouTube")

    ref_source = account.url or account.handle
    if not ref_source:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account has no URL or handle")

    try:
        ref = parse_youtube_channel_ref(ref_source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        channel_id = await resolve_channel_id(ref)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)

    details = await fetch_channel_details(channel_id)

    if account.youtube_channel_id != channel_id:
        account.youtube_channel_id = channel_id
        session.add(account)
        await session.flush()

    channel = await session.get(YouTubeChannel, account.id)
    if not channel:
        channel = YouTubeChannel(account_id=account.id, channel_id=channel_id)
    channel.channel_id = channel_id
    channel.title = details.get("title")
    channel.description = details.get("description")
    channel.thumbnail_url = details.get("thumbnail_url")
    channel.banner_url = details.get("banner_url")
    channel.handle = details.get("handle")
    channel.country = details.get("country")
    channel.subscribers = details.get("subscribers")
    channel.views_total = details.get("views_total")
    channel.videos_total = details.get("videos_total")
    channel.last_synced_at = now
    channel.raw_json = details.get("raw")
    session.add(channel)

    uploads_playlist_id = details.get("uploads_playlist_id")
    synced_videos = 0
    synced_shorts = 0
    synced_lives = 0
    status_value = "ok"
    sync_error: str | None = None
    if uploads_playlist_id:
        page_token = None
        pages = 0
        video_ids: list[str] = []
        while pages < 4:
            try:
                playlist_data = await fetch_playlist_videos(
                    uploads_playlist_id, page_token=page_token, page_size=50
                )
                video_ids.extend(playlist_data.get("video_ids", []))
                page_token = playlist_data.get("next_page_token")
                pages += 1
                if not page_token:
                    break
            except Exception as exc:
                status_value = "partial"
                sync_error = f"Не удалось загрузить плейлист: {exc}"
                break
        try:
            for i in range(0, len(video_ids), 50):
                chunk = video_ids[i : i + 50]
                details_list = await fetch_videos_details(chunk)
                for item in details_list:
                    result = await session.execute(
                        select(YouTubeVideo).where(
                            YouTubeVideo.account_id == account.id, YouTubeVideo.video_id == item.get("video_id")
                        )
                    )
                    video = result.scalar_one_or_none()
                    if not video:
                        video = YouTubeVideo(account_id=account.id, video_id=item.get("video_id"))
                    video.title = item.get("title") or ""
                    video.description = item.get("description")
                    video.thumbnail_url = item.get("thumbnail_url")
                    video.published_at = _parse_dt(item.get("published_at"))
                    video.duration_seconds = item.get("duration_seconds")
                    video.views = item.get("views")
                    video.likes = item.get("likes")
                    video.comments = item.get("comments")
                    video.privacy_status = item.get("privacy_status")
                    video.content_type, video.live_status = _classify_video(item)
                    video.scheduled_start_at = _parse_dt(item.get("scheduled_start"))
                    video.actual_start_at = _parse_dt(item.get("actual_start"))
                    video.actual_end_at = _parse_dt(item.get("actual_end"))
                    video.permalink = f"https://www.youtube.com/watch?v={item.get('video_id')}"
                    video.raw = item.get("raw")
                    video.last_synced_at = now
                    video.virality_score = calculate_virality_for_youtube(video, details.get("subscribers"))
                    session.add(video)
                    if video.content_type == "live":
                        synced_lives += 1
                    elif video.content_type == "short":
                        synced_shorts += 1
                    else:
                        synced_videos += 1
        except Exception as exc:
            status_value = "partial"
            sync_error = f"Не удалось загрузить детали видео: {exc}"

    today = date.today()
    existing_metric = await session.scalar(
        select(AccountMetricsDaily).where(
            AccountMetricsDaily.account_id == account.id,
            AccountMetricsDaily.date == today,
        )
    )
    if existing_metric:
        existing_metric.views = details.get("views_total")
        existing_metric.subs = details.get("subscribers")
        existing_metric.posts = details.get("videos_total")
    else:
        session.add(
            AccountMetricsDaily(
                account_id=account.id,
                date=today,
                views=details.get("views_total"),
                subs=details.get("subscribers"),
                posts=details.get("videos_total"),
            )
        )

    account.sync_status = status_value
    account.sync_error = sync_error
    account.last_synced_at = now
    session.add(account)

    await session.commit()

    return {
        "account_id": account.id,
        "channel_id": channel_id,
        "title": details.get("title"),
        "views_total": details.get("views_total"),
        "subscribers": details.get("subscribers"),
        "videos_total": details.get("videos_total"),
        "synced_videos": synced_videos,
        "synced_shorts": synced_shorts,
        "synced_lives": synced_lives,
        "status": status_value,
        "error": sync_error,
    }
