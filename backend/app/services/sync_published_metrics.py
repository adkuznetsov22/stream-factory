"""
Sync metrics for published videos.

Periodically fetches views/likes/comments/shares from platform APIs
for all recently published tasks and stores snapshots in published_video_metrics.

Snapshot policy:
  - First 48 hours after publish: snapshot every tick (scheduler runs every 1–4h)
  - After 48 hours: snapshot once per day (skip if last_metrics_at < 24h ago)
  - Detailed snapshots kept for 30 days, then aggregated to daily/weekly

Enables analytics: candidate virality_score → actual video performance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PublishTask, Candidate, PublishedVideoMetrics
from app.settings import get_settings

logger = logging.getLogger(__name__)

# ── Snapshot policy constants ────────────────────────────────
FRESH_WINDOW_HOURS = 48        # first 48h: snapshot every tick
STALE_INTERVAL_HOURS = 24      # after 48h: max once per 24h
MAX_AGE_DAYS = 90              # fetch metrics for up to 90 days
DETAIL_RETENTION_DAYS = 30     # keep detailed snapshots 30 days
WEEKLY_RETENTION_DAYS = 180    # keep daily aggregates 180 days, then weekly


def _should_snapshot(task: PublishTask, now: datetime) -> bool:
    """Determine if this task needs a new snapshot based on age policy."""
    if not task.published_at:
        return True

    hours_since_publish = (now - task.published_at).total_seconds() / 3600

    if hours_since_publish <= FRESH_WINDOW_HOURS:
        # Fresh video: snapshot every tick
        return True

    # Stale video: check if enough time passed since last snapshot
    if not task.last_metrics_at:
        return True

    hours_since_last = (now - task.last_metrics_at).total_seconds() / 3600
    return hours_since_last >= STALE_INTERVAL_HOURS


async def sync_published_metrics(session: AsyncSession) -> dict:
    """Fetch metrics for all published tasks and save snapshots.

    Respects snapshot policy: frequent for fresh videos, daily for older ones.
    Returns summary dict with counts.
    """
    now = datetime.now(timezone.utc)
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
        return {"synced": 0, "skipped": 0, "errors": 0, "total": 0}

    # Filter by snapshot policy
    tasks_to_sync = [t for t in tasks if _should_snapshot(t, now)]
    skipped = len(tasks) - len(tasks_to_sync)

    if skipped:
        logger.info(f"[sync_metrics] {skipped} tasks skipped (policy: not due yet)")

    if not tasks_to_sync:
        return {"synced": 0, "skipped": skipped, "errors": 0, "total": len(tasks)}

    # Group by platform
    by_platform: dict[str, list[PublishTask]] = {}
    for task in tasks_to_sync:
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

                # Upsert snapshot
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(PublishedVideoMetrics).values(
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
                ).on_conflict_do_update(
                    constraint="uq_pvm_platform_extid_snap",
                    set_={
                        "views": metrics.get("views"),
                        "likes": metrics.get("likes"),
                        "comments": metrics.get("comments"),
                        "shares": metrics.get("shares"),
                        "raw_data": metrics.get("raw"),
                    },
                )
                await session.execute(stmt)

                # Update denormalized last_metrics cache on PublishTask
                task.last_metrics_json = {
                    "views": metrics.get("views"),
                    "likes": metrics.get("likes"),
                    "comments": metrics.get("comments"),
                    "shares": metrics.get("shares"),
                    "hours_since_publish": hours_since,
                }
                task.last_metrics_at = now
                session.add(task)
                synced += 1

            await session.commit()

        except Exception as e:
            logger.error(f"[sync_metrics] Error syncing {platform}: {e}")
            errors += 1
            await session.rollback()

    logger.info(
        f"[sync_metrics] Done: {synced} synced, {skipped} skipped, "
        f"{errors} errors, {len(tasks)} total tasks"
    )
    return {"synced": synced, "skipped": skipped, "errors": errors, "total": len(tasks)}


# ── Snapshot aggregation / cleanup ───────────────────────────

async def aggregate_old_snapshots(session: AsyncSession) -> dict:
    """Roll up old detailed snapshots into daily/weekly aggregates.

    Policy:
      - Snapshots older than 30 days: keep only best-per-day (max views)
      - Snapshots older than 180 days: keep only best-per-week (max views)

    Returns summary with counts of deleted rows.
    """
    now = datetime.now(timezone.utc)
    detail_cutoff = now - timedelta(days=DETAIL_RETENTION_DAYS)
    weekly_cutoff = now - timedelta(days=WEEKLY_RETENTION_DAYS)

    deleted_daily = 0
    deleted_weekly = 0

    # ── Phase 1: >30 days → keep one snapshot per (task_id, day) ──
    # Find IDs to keep: the row with max views per (task_id, date)
    daily_keep = (
        select(
            func.distinct(
                func.first_value(PublishedVideoMetrics.id).over(
                    partition_by=[
                        PublishedVideoMetrics.task_id,
                        func.date_trunc("day", PublishedVideoMetrics.snapshot_at),
                    ],
                    order_by=PublishedVideoMetrics.views.desc().nullslast(),
                )
            )
        )
        .where(and_(
            PublishedVideoMetrics.snapshot_at < detail_cutoff,
            PublishedVideoMetrics.snapshot_at >= weekly_cutoff,
        ))
    ).scalar_subquery()

    # Delete all rows in the 30–180 day window that are NOT the daily best
    del_daily = (
        delete(PublishedVideoMetrics)
        .where(and_(
            PublishedVideoMetrics.snapshot_at < detail_cutoff,
            PublishedVideoMetrics.snapshot_at >= weekly_cutoff,
            PublishedVideoMetrics.id.notin_(daily_keep),
        ))
    )
    result_d = await session.execute(del_daily)
    deleted_daily = result_d.rowcount

    # ── Phase 2: >180 days → keep one snapshot per (task_id, week) ──
    weekly_keep = (
        select(
            func.distinct(
                func.first_value(PublishedVideoMetrics.id).over(
                    partition_by=[
                        PublishedVideoMetrics.task_id,
                        func.date_trunc("week", PublishedVideoMetrics.snapshot_at),
                    ],
                    order_by=PublishedVideoMetrics.views.desc().nullslast(),
                )
            )
        )
        .where(PublishedVideoMetrics.snapshot_at < weekly_cutoff)
    ).scalar_subquery()

    del_weekly = (
        delete(PublishedVideoMetrics)
        .where(and_(
            PublishedVideoMetrics.snapshot_at < weekly_cutoff,
            PublishedVideoMetrics.id.notin_(weekly_keep),
        ))
    )
    result_w = await session.execute(del_weekly)
    deleted_weekly = result_w.rowcount

    await session.commit()

    logger.info(
        f"[aggregate_snapshots] Cleaned up: "
        f"{deleted_daily} daily (>30d), {deleted_weekly} weekly (>180d)"
    )
    return {"deleted_daily": deleted_daily, "deleted_weekly": deleted_weekly}


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
