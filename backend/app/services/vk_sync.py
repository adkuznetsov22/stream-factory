from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.vk_api import fetch_wall, parse_vk_ref, resolve_owner
from app.models import AccountMetricsDaily, SocialAccount, SocialPlatform, VKClip, VKPost, VKProfile, VKVideo
from app.services.virality import calculate_virality_for_vk
from app.settings import get_settings

settings = get_settings()


async def sync_vk_account(session: AsyncSession, account: SocialAccount, limit: int | None = None) -> dict:
    if account.platform != SocialPlatform.vk:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not VK")
    if not settings.vk_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VK_ACCESS_TOKEN missing")

    source = account.url or account.login or account.handle
    if not source:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account has no URL or login")

    ref = parse_vk_ref(source)
    owner_info = await resolve_owner(ref)
    owner_id = owner_info["owner_id"]
    is_group = owner_info.get("is_group", False)

    profile = await session.scalar(select(VKProfile).where(VKProfile.account_id == account.id))
    if not profile:
        profile = VKProfile(account_id=account.id, vk_owner_id=owner_id)
    profile.vk_owner_id = owner_id
    profile.is_group = is_group
    profile.screen_name = owner_info.get("screen_name")
    profile.name = owner_info.get("name", "")
    profile.photo_200 = owner_info.get("photo_200")
    profile.country = owner_info.get("country")
    profile.description = owner_info.get("description")
    profile.members_count = owner_info.get("members_count")
    profile.followers_count = owner_info.get("followers_count")
    profile.last_synced_at = datetime.now(timezone.utc)
    session.add(profile)
    await session.flush()

    max_posts = limit or settings.vk_default_posts_limit
    raw_posts = await fetch_wall(owner_id, max_posts)
    synced_posts = 0
    for item in raw_posts:
        post_id = item.get("id")
        if post_id is None:
            continue
        published_at = item.get("date")
        published_dt = datetime.fromtimestamp(published_at, tz=timezone.utc) if published_at else None
        res = await session.execute(
            select(VKPost).where(VKPost.account_id == account.id, VKPost.post_id == int(post_id))
        )
        post = res.scalar_one_or_none()
        if not post:
            post = VKPost(account_id=account.id, post_id=int(post_id), vk_owner_id=owner_id)
        post.vk_owner_id = owner_id
        post.published_at = published_dt
        post.text = item.get("text")
        post.permalink = f"https://vk.com/wall{owner_id}_{post_id}"
        post.views = (item.get("views") or {}).get("count") if isinstance(item.get("views"), dict) else item.get("views")
        post.likes = (item.get("likes") or {}).get("count") if isinstance(item.get("likes"), dict) else item.get("likes")
        post.reposts = (item.get("reposts") or {}).get("count") if isinstance(item.get("reposts"), dict) else item.get("reposts")
        post.comments = (item.get("comments") or {}).get("count") if isinstance(item.get("comments"), dict) else item.get("comments")
        attachments = item.get("attachments") or []
        post.attachments_count = len(attachments) if isinstance(attachments, list) else None
        post.raw = item
        post.last_synced_at = datetime.now(timezone.utc)
        session.add(post)
        synced_posts += 1

    synced_videos = 0
    synced_clips = 0

    # attachments: video / clip / short_video
    for item in raw_posts:
        attachments = item.get("attachments") or []
        published_at = item.get("date")
        published_dt = datetime.fromtimestamp(published_at, tz=timezone.utc) if published_at else None
        for att in attachments:
            att_type = att.get("type")
            data = att.get(att_type) if isinstance(att, dict) else None
            if not data:
                continue
            if att_type == "video":
                vid = data.get("id")
                if vid is None:
                    continue
                res = await session.execute(
                    select(VKVideo).where(
                        VKVideo.account_id == account.id,
                        VKVideo.vk_owner_id == owner_id,
                        VKVideo.video_id == int(vid),
                    )
                )
                video = res.scalar_one_or_none()
                if not video:
                    video = VKVideo(account_id=account.id, vk_owner_id=owner_id, video_id=int(vid))
                video.vk_full_id = f"{owner_id}_{vid}"
                video.title = data.get("title")
                video.description = data.get("description")
                video.published_at = published_dt
                video.duration_seconds = data.get("duration")
                video.views = (data.get("views") or {}).get("count") if isinstance(data.get("views"), dict) else data.get("views")
                video.likes = (data.get("likes") or {}).get("count") if isinstance(data.get("likes"), dict) else data.get("likes")
                video.comments = (data.get("comments") or {}).get("count") if isinstance(data.get("comments"), dict) else data.get("comments")
                video.reposts = (data.get("reposts") or {}).get("count") if isinstance(data.get("reposts"), dict) else data.get("reposts")
                thumb = None
                if isinstance(data.get("image"), list) and data["image"]:
                    thumb = data["image"][-1].get("url")
                video.thumbnail_url = thumb or data.get("photo_800") or data.get("photo_320")
                video.permalink = f"https://vk.com/video{data.get('owner_id') or owner_id}_{vid}"
                video.raw = data
                video.updated_at = datetime.now(timezone.utc)
                video.virality_score = calculate_virality_for_vk(video, profile.members_count or profile.followers_count)
                session.add(video)
                synced_videos += 1
            if att_type in {"clip", "short_video"}:
                cid = data.get("id")
                if cid is None:
                    continue
                res = await session.execute(
                    select(VKClip).where(
                        VKClip.account_id == account.id,
                        VKClip.vk_owner_id == owner_id,
                        VKClip.clip_id == int(cid),
                    )
                )
                clip = res.scalar_one_or_none()
                if not clip:
                    clip = VKClip(account_id=account.id, vk_owner_id=owner_id, clip_id=int(cid))
                clip.media_type = att_type
                clip.vk_full_id = f"{owner_id}_{cid}"
                clip.title = data.get("title") or data.get("description")
                clip.description = data.get("description")
                clip.published_at = published_dt
                clip.duration_seconds = data.get("duration")
                clip.views = (data.get("views") or {}).get("count") if isinstance(data.get("views"), dict) else data.get("views")
                clip.likes = (data.get("likes") or {}).get("count") if isinstance(data.get("likes"), dict) else data.get("likes")
                clip.comments = (data.get("comments") or {}).get("count") if isinstance(data.get("comments"), dict) else data.get("comments")
                clip.reposts = (data.get("reposts") or {}).get("count") if isinstance(data.get("reposts"), dict) else data.get("reposts")
                thumb = None
                if isinstance(data.get("image"), list) and data["image"]:
                    thumb = data["image"][-1].get("url")
                clip.thumbnail_url = thumb
                clip.permalink = data.get("url") or data.get("player")
                clip.raw = data
                clip.updated_at = datetime.now(timezone.utc)
                clip.virality_score = calculate_virality_for_vk(clip, profile.members_count or profile.followers_count)
                session.add(clip)
                synced_clips += 1

    today = date.today()
    existing_metric = await session.scalar(
        select(AccountMetricsDaily).where(
            AccountMetricsDaily.account_id == account.id,
            AccountMetricsDaily.date == today,
        )
    )
    subs_value = profile.members_count or profile.followers_count
    posts_total = None
    if raw_posts:
        posts_total = await session.scalar(
            select(func.count()).select_from(VKPost).where(VKPost.account_id == account.id)
        )
    if existing_metric:
        existing_metric.subs = subs_value
        existing_metric.posts = posts_total
    else:
        session.add(
            AccountMetricsDaily(
                account_id=account.id,
                date=today,
                subs=subs_value,
                posts=posts_total,
            )
        )

    status_value = "ok"
    errors: dict[str, str | None] = {"videos": None, "clips": None}
    account.sync_status = status_value
    account.sync_error = None
    account.last_synced_at = datetime.now(timezone.utc)
    session.add(account)
    await session.commit()

    return {
        "ok": True,
        "status": status_value,
        "errors": errors,
        "account_id": account.id,
        "vk_owner_id": owner_id,
        "name": profile.name,
        "synced_posts": synced_posts,
        "synced_videos": synced_videos,
        "synced_clips": synced_clips,
        "subs": subs_value,
        "posts_total": posts_total,
    }
