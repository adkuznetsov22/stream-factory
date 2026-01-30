from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from app.settings import get_settings

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YT_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def parse_youtube_channel_ref(url: str) -> dict:
    ref = url.strip()
    if ref.startswith("@"):
        return {"type": "handle", "value": ref.lstrip("@")}
    if "youtube.com/channel/" in ref:
        parts = ref.split("/channel/")
        channel_id = parts[-1].split("/")[0]
        if channel_id:
            return {"type": "channel_id", "value": channel_id}
    if "youtube.com/@" in ref:
        parts = ref.split("youtube.com/@")
        handle = parts[-1].split("/")[0]
        if handle:
            return {"type": "handle", "value": handle}
    raise ValueError("Не удалось распознать ссылку или handle YouTube")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0)


async def resolve_channel_id(ref: dict) -> str:
    if ref["type"] == "channel_id":
        return ref["value"]
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    async with _client() as client:
        params = {
            "part": "snippet",
            "type": "channel",
            "maxResults": 1,
            "q": ref["value"],
            "key": settings.youtube_api_key,
        }
        try:
            resp = await client.get(YT_SEARCH_URL, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            # single retry
            resp = await client.get(YT_SEARCH_URL, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"YouTube search error: {resp.status_code}")
        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise LookupError("channel not found")
        item = items[0]
        channel_id = (
            item.get("snippet", {}).get("channelId")
            or item.get("id", {}).get("channelId")
        )
        if not channel_id:
            raise LookupError("channel not found")
        return channel_id


async def fetch_channel_stats(channel_id: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    params = {
        "part": "statistics,snippet",
        "id": channel_id,
        "key": settings.youtube_api_key,
    }
    async with _client() as client:
        try:
            resp = await client.get(YT_CHANNELS_URL, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            resp = await client.get(YT_CHANNELS_URL, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube channels error: {resp.status_code}")
    data = resp.json()
    items = data.get("items", [])
    if not items:
        raise LookupError("channel not found")
    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    return {
        "title": snippet.get("title"),
        "customUrl": snippet.get("customUrl"),
        "publishedAt": snippet.get("publishedAt"),
        "subscriberCount": int(stats.get("subscriberCount", 0)) if stats.get("subscriberCount") is not None else None,
        "viewCount": int(stats.get("viewCount", 0)) if stats.get("viewCount") is not None else None,
        "videoCount": int(stats.get("videoCount", 0)) if stats.get("videoCount") is not None else None,
        "channelId": item.get("id") or channel_id,
    }


async def fetch_channel_details(channel_id: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    params = {
        "part": "snippet,statistics,brandingSettings,contentDetails",
        "id": channel_id,
        "key": settings.youtube_api_key,
    }
    async with _client() as client:
        try:
            resp = await client.get(YT_CHANNELS_URL, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            resp = await client.get(YT_CHANNELS_URL, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube channels error: {resp.status_code}")
    data = resp.json()
    items = data.get("items", [])
    if not items:
        raise LookupError("channel not found")
    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    branding = item.get("brandingSettings", {}) or {}
    images = branding.get("image", {}) or {}
    content = item.get("contentDetails", {}) or {}
    uploads_playlist_id = content.get("relatedPlaylists", {}).get("uploads")
    return {
        "channel_id": item.get("id") or channel_id,
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "thumbnail_url": (snippet.get("thumbnails") or {}).get("high", {}).get("url")
        or (snippet.get("thumbnails") or {}).get("default", {}).get("url"),
        "banner_url": images.get("bannerExternalUrl"),
        "handle": snippet.get("customUrl") or snippet.get("title"),
        "country": snippet.get("country"),
        "subscribers": int(stats.get("subscriberCount", 0)) if stats.get("subscriberCount") is not None else None,
        "views_total": int(stats.get("viewCount", 0)) if stats.get("viewCount") is not None else None,
        "videos_total": int(stats.get("videoCount", 0)) if stats.get("videoCount") is not None else None,
        "uploads_playlist_id": uploads_playlist_id,
        "raw": item,
    }


async def fetch_playlist_videos(playlist_id: str, page_token: str | None = None, page_size: int = 50) -> dict:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": page_size,
        "key": settings.youtube_api_key,
    }
    if page_token:
        params["pageToken"] = page_token
    async with _client() as client:
        try:
            resp = await client.get(YT_PLAYLIST_ITEMS_URL, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            resp = await client.get(YT_PLAYLIST_ITEMS_URL, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube playlistItems error: {resp.status_code}")
    data = resp.json()
    video_ids = [item["contentDetails"]["videoId"] for item in data.get("items", []) if item.get("contentDetails")]
    return {
        "video_ids": video_ids,
        "next_page_token": data.get("nextPageToken"),
    }


def _parse_iso8601_duration(duration: str | None) -> int | None:
    if not duration:
        return None
    # Simple parser for PT#H#M#S
    total = 0
    num = ""
    duration = duration.replace("PT", "")
    units = {"H": 3600, "M": 60, "S": 1}
    for ch in duration:
        if ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ""
    return total if total > 0 else None


async def fetch_videos_details(video_ids: list[str]) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    if not video_ids:
        return []
    params = {
        "part": "snippet,contentDetails,statistics,status",
        "id": ",".join(video_ids),
        "key": settings.youtube_api_key,
    }
    async with _client() as client:
        try:
            resp = await client.get(YT_VIDEOS_URL, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            resp = await client.get(YT_VIDEOS_URL, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube videos error: {resp.status_code}")
    data = resp.json()
    items = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {}) or {}
        stats = item.get("statistics", {}) or {}
        content = item.get("contentDetails", {}) or {}
        status = item.get("status", {}) or {}
        items.append(
            {
                "video_id": item.get("id"),
                "title": snippet.get("title") or "",
                "description": snippet.get("description"),
                "thumbnail_url": (snippet.get("thumbnails") or {}).get("high", {}).get("url")
                or (snippet.get("thumbnails") or {}).get("default", {}).get("url"),
                "published_at": snippet.get("publishedAt"),
                "duration_seconds": _parse_iso8601_duration(content.get("duration")),
                "views": int(stats.get("viewCount", 0)) if stats.get("viewCount") is not None else None,
                "likes": int(stats.get("likeCount", 0)) if stats.get("likeCount") is not None else None,
                "comments": int(stats.get("commentCount", 0)) if stats.get("commentCount") is not None else None,
                "privacy_status": status.get("privacyStatus"),
                "live_broadcast_content": snippet.get("liveBroadcastContent"),
                "live_streaming_details": item.get("liveStreamingDetails") or {},
                "scheduled_start": (item.get("liveStreamingDetails") or {}).get("scheduledStartTime"),
                "actual_start": (item.get("liveStreamingDetails") or {}).get("actualStartTime"),
                "actual_end": (item.get("liveStreamingDetails") or {}).get("actualEndTime"),
                "raw": item,
            }
        )
    return items
