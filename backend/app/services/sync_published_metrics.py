"""
Sync metrics for published videos.

Periodically fetches views/likes/comments/shares from platform APIs
for all recently published tasks and stores snapshots in published_video_metrics.

Enables analytics: candidate virality_score → actual video performance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PublishTask, Candidate, PublishedVideoMetrics
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Fetch metrics for videos published within the last N days
MAX_AGE_DAYS = 30


async def sync_published_metrics(session: AsyncSession) -> dict:
    """Fetch metrics for all published tasks and save snapshots.

    Returns summary dict with counts.
    """
    now = datetime.now(timezone.utc)

    # Get published tasks with external_id (last MAX_AGE_DAYS)
    from datetime import timedelta
    cutoff = now - timedelta(days=MAX_AGE_DAYS)

    query = (
        select(PublishTask)
        .where(and_(
            PublishTask.status == "published",
            PublishTask.published_external_id.isnot(None),
            PublishTask.published_at >= cutoff,
        ))
    )
    result = await session.execute(query)
    tasks = result.scalars().all()

    if not tasks:
        logger.info("[sync_metrics] No published tasks to sync")
        return {"synced": 0, "errors": 0, "total": 0}

    # Group by platform
    by_platform: dict[str, list[PublishTask]] = {}
    for task in tasks:
        platform = (task.platform or "").lower()
        by_platform.setdefault(platform, []).append(task)

    synced = 0
    errors = 0

    for platform, platform_tasks in by_platform.items():
        try:
            fetcher = _get_metrics_fetcher(platform)
            if not fetcher:
                logger.debug(f"[sync_metrics] No fetcher for platform '{platform}', skipping {len(platform_tasks)} tasks")
                continue

            metrics_map = await fetcher(platform_tasks)

            for task in platform_tasks:
                ext_id = task.published_external_id
                metrics = metrics_map.get(ext_id)
                if not metrics:
                    continue

                # Compute hours since publish
                hours_since = None
                if task.published_at:
                    delta = now - task.published_at
                    hours_since = int(delta.total_seconds() / 3600)

                # Find linked candidate
                candidate_id = None
                cand_q = await session.execute(
                    select(Candidate.id).where(Candidate.linked_publish_task_id == task.id)
                )
                cand_row = cand_q.first()
                if cand_row:
                    candidate_id = cand_row[0]

                snapshot = PublishedVideoMetrics(
                    task_id=task.id,
                    candidate_id=candidate_id,
                    platform=platform,
                    external_id=ext_id,
                    views=metrics.get("views"),
                    likes=metrics.get("likes"),
                    comments=metrics.get("comments"),
                    shares=metrics.get("shares"),
                    snapshot_at=now,
                    hours_since_publish=hours_since,
                    raw_data=metrics.get("raw"),
                )
                session.add(snapshot)
                synced += 1

            await session.commit()

        except Exception as e:
            logger.error(f"[sync_metrics] Error syncing {platform}: {e}")
            errors += 1
            await session.rollback()

    logger.info(f"[sync_metrics] Done: {synced} synced, {errors} errors, {len(tasks)} total tasks")
    return {"synced": synced, "errors": errors, "total": len(tasks)}


# ── Platform-specific metric fetchers ────────────────────────

MetricsMap = dict[str, dict[str, Any]]  # external_id -> {views, likes, comments, shares, raw}


def _get_metrics_fetcher(platform: str):
    """Return async fetcher function for a platform."""
    return {
        "youtube": _fetch_youtube_metrics,
        "tiktok": _fetch_tiktok_metrics,
        "instagram": _fetch_instagram_metrics,
        "vk": _fetch_vk_metrics,
    }.get(platform)


async def _fetch_youtube_metrics(tasks: list[PublishTask]) -> MetricsMap:
    """Fetch metrics for YouTube videos using YouTube Data API."""
    settings = get_settings()
    if not settings.youtube_api_key:
        logger.warning("[sync_metrics] YOUTUBE_API_KEY missing, skipping YouTube metrics")
        return {}

    from app.integrations.youtube_api import fetch_videos_details

    video_ids = [t.published_external_id for t in tasks if t.published_external_id]
    if not video_ids:
        return {}

    # YouTube API allows up to 50 IDs per request
    result: MetricsMap = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            items = await fetch_videos_details(batch)
            for item in items:
                vid = item.get("video_id")
                if vid:
                    result[vid] = {
                        "views": item.get("views"),
                        "likes": item.get("likes"),
                        "comments": item.get("comments"),
                        "shares": None,  # YouTube API doesn't expose shares
                        "raw": {k: v for k, v in item.items() if k != "raw"},
                    }
        except Exception as e:
            logger.error(f"[sync_metrics] YouTube batch fetch error: {e}")

    return result


async def _fetch_tiktok_metrics(tasks: list[PublishTask]) -> MetricsMap:
    """Fetch metrics for TikTok videos via Apify scraper."""
    settings = get_settings()
    if not settings.apify_token:
        logger.warning("[sync_metrics] APIFY_TOKEN missing, skipping TikTok metrics")
        return {}

    from app.integrations.apify_client import run_actor_get_items

    result: MetricsMap = {}
    urls = []
    url_to_ext_id: dict[str, str] = {}

    for task in tasks:
        if task.published_url and task.published_external_id:
            urls.append(task.published_url)
            url_to_ext_id[task.published_url] = task.published_external_id

    if not urls:
        return result

    try:
        items = await run_actor_get_items(
            "clockworks/tiktok-scraper",
            {"startUrls": [{"url": u} for u in urls], "resultsPerPage": len(urls)},
            timeout_s=120,
        )
        for item in (items or []):
            video_id = str(item.get("id", ""))
            stats = item.get("stats") or item.get("statsV2") or {}
            if video_id:
                result[video_id] = {
                    "views": _safe_int(stats.get("playCount") or item.get("playCount")),
                    "likes": _safe_int(stats.get("diggCount") or item.get("diggCount")),
                    "comments": _safe_int(stats.get("commentCount") or item.get("commentCount")),
                    "shares": _safe_int(stats.get("shareCount") or item.get("shareCount")),
                    "raw": {"id": video_id, "stats": stats},
                }
    except Exception as e:
        logger.error(f"[sync_metrics] TikTok Apify error: {e}")

    return result


async def _fetch_instagram_metrics(tasks: list[PublishTask]) -> MetricsMap:
    """Fetch metrics for Instagram Reels via Apify scraper."""
    settings = get_settings()
    if not settings.apify_token:
        logger.warning("[sync_metrics] APIFY_TOKEN missing, skipping Instagram metrics")
        return {}

    from app.integrations.apify_client import run_actor_and_get_dataset_items

    result: MetricsMap = {}
    urls = [t.published_url for t in tasks if t.published_url]
    if not urls:
        return result

    try:
        items, _meta = await run_actor_and_get_dataset_items(
            "scraper-engine/instagram-post-scraper",
            {"directUrls": urls, "resultsLimit": len(urls)},
            timeout_s=120,
        )
        for item in (items or []):
            shortcode = item.get("shortCode") or item.get("code") or item.get("shortcode")
            media_id = str(item.get("id", ""))
            ext_id = media_id or shortcode

            # Match back to task external_id
            for task in tasks:
                if task.published_external_id in (media_id, shortcode):
                    ext_id = task.published_external_id
                    break

            if ext_id:
                result[ext_id] = {
                    "views": _safe_int(item.get("videoViewCount") or item.get("video_view_count")),
                    "likes": _safe_int(item.get("likesCount") or item.get("likes")),
                    "comments": _safe_int(item.get("commentsCount") or item.get("comments")),
                    "shares": None,
                    "raw": {"id": ext_id, "shortcode": shortcode},
                }
    except Exception as e:
        logger.error(f"[sync_metrics] Instagram Apify error: {e}")

    return result


async def _fetch_vk_metrics(tasks: list[PublishTask]) -> MetricsMap:
    """Fetch metrics for VK videos via VK API video.get."""
    settings = get_settings()
    if not settings.vk_access_token:
        logger.warning("[sync_metrics] VK_ACCESS_TOKEN missing, skipping VK metrics")
        return {}

    import httpx

    result: MetricsMap = {}
    # VK external_id format: "owner_id_video_id" e.g. "-12345_67890"
    videos_param = ",".join(
        t.published_external_id for t in tasks if t.published_external_id
    )
    if not videos_param:
        return result

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.vk.com/method/video.get",
                params={
                    "access_token": settings.vk_access_token,
                    "v": settings.vk_api_version,
                    "videos": videos_param,
                    "extended": 0,
                },
            )
        data = resp.json()
        items = data.get("response", {}).get("items", [])

        for item in items:
            owner_id = item.get("owner_id")
            video_id = item.get("id")
            ext_id = f"{owner_id}_{video_id}"

            result[ext_id] = {
                "views": _safe_int(item.get("views")),
                "likes": _safe_int((item.get("likes") or {}).get("count")),
                "comments": _safe_int((item.get("comments") or {}).get("count")),
                "shares": _safe_int((item.get("reposts") or {}).get("count")),
                "raw": {"owner_id": owner_id, "video_id": video_id},
            }
    except Exception as e:
        logger.error(f"[sync_metrics] VK API error: {e}")

    return result


def _safe_int(val) -> int | None:
    """Safely convert value to int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
