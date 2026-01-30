"""
Video Pool Service

Handles video selection from project sources:
- Fetches videos from all source accounts
- Filters by virality score and usage status
- Provides mix of new + top historical content
- Marks videos as used when selected for tasks
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InstagramPost,
    ProjectSource,
    ProjectDestination,
    PublishTask,
    TikTokVideo,
    VKClip,
    VKVideo,
    YouTubeVideo,
    SocialAccount,
)


VideoType = Literal["youtube", "tiktok", "vk_video", "vk_clip", "instagram"]


class VideoPoolService:
    """Service for selecting videos from project sources."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_source_account_ids(self, project_id: int, platform: str | None = None) -> list[int]:
        """Get active source account IDs for a project."""
        query = select(ProjectSource.social_account_id).where(
            ProjectSource.project_id == project_id,
            ProjectSource.is_active == True,
        )
        if platform:
            query = query.where(ProjectSource.platform == platform)
        
        result = await self.session.execute(query)
        return [row[0] for row in result.fetchall()]
    
    async def get_destination_accounts(self, project_id: int, platform: str | None = None) -> list[dict]:
        """Get active destination accounts for a project."""
        query = (
            select(ProjectDestination, SocialAccount)
            .join(SocialAccount, ProjectDestination.social_account_id == SocialAccount.id)
            .where(
                ProjectDestination.project_id == project_id,
                ProjectDestination.is_active == True,
            )
            .order_by(ProjectDestination.priority)
        )
        if platform:
            query = query.where(ProjectDestination.platform == platform)
        
        result = await self.session.execute(query)
        return [
            {
                "destination_id": dest.id,
                "account_id": acc.id,
                "platform": dest.platform,
                "priority": dest.priority,
                "label": acc.label,
            }
            for dest, acc in result.fetchall()
        ]
    
    async def get_available_videos(
        self,
        project_id: int,
        *,
        platform: str | None = None,
        limit: int = 50,
        min_score: float | None = None,
        include_used: bool = False,
        new_only: bool = False,
        new_days: int = 7,
    ) -> list[dict]:
        """
        Get available videos from project sources.
        
        Args:
            project_id: Project ID
            platform: Filter by platform (youtube, tiktok, vk, instagram)
            limit: Maximum videos to return
            min_score: Minimum virality score threshold
            include_used: Include already used videos
            new_only: Only videos from last `new_days` days
            new_days: Days threshold for "new" videos
        """
        source_ids = await self.get_source_account_ids(project_id, platform)
        if not source_ids:
            return []
        
        results = []
        platforms = [platform.lower()] if platform else ["youtube", "tiktok", "vk", "instagram"]
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=new_days) if new_only else None
        
        for plat in platforms:
            videos = await self._fetch_platform_videos(
                plat, source_ids, limit, min_score, include_used, cutoff_date
            )
            results.extend(videos)
        
        # Sort by virality score
        results.sort(key=lambda x: x.get("virality_score") or 0, reverse=True)
        return results[:limit]
    
    async def _fetch_platform_videos(
        self,
        platform: str,
        source_ids: list[int],
        limit: int,
        min_score: float | None,
        include_used: bool,
        cutoff_date: datetime | None,
    ) -> list[dict]:
        """Fetch videos from a specific platform."""
        results = []
        
        if platform == "youtube":
            query = select(YouTubeVideo).where(
                YouTubeVideo.account_id.in_(source_ids),
                YouTubeVideo.virality_score.isnot(None),
            )
            if not include_used:
                query = query.where(YouTubeVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(YouTubeVideo.virality_score >= min_score)
            if cutoff_date:
                query = query.where(YouTubeVideo.published_at >= cutoff_date)
            query = query.order_by(YouTubeVideo.virality_score.desc()).limit(limit)
            
            rows = await self.session.execute(query)
            for video in rows.scalars():
                results.append(self._video_to_dict(video, "youtube"))
        
        elif platform == "tiktok":
            query = select(TikTokVideo).where(
                TikTokVideo.account_id.in_(source_ids),
                TikTokVideo.virality_score.isnot(None),
            )
            if not include_used:
                query = query.where(TikTokVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(TikTokVideo.virality_score >= min_score)
            if cutoff_date:
                query = query.where(TikTokVideo.published_at >= cutoff_date)
            query = query.order_by(TikTokVideo.virality_score.desc()).limit(limit)
            
            rows = await self.session.execute(query)
            for video in rows.scalars():
                results.append(self._video_to_dict(video, "tiktok"))
        
        elif platform == "vk":
            # VK Videos
            query = select(VKVideo).where(
                VKVideo.account_id.in_(source_ids),
                VKVideo.virality_score.isnot(None),
            )
            if not include_used:
                query = query.where(VKVideo.used_in_task_id.is_(None))
            if min_score:
                query = query.where(VKVideo.virality_score >= min_score)
            if cutoff_date:
                query = query.where(VKVideo.published_at >= cutoff_date)
            query = query.order_by(VKVideo.virality_score.desc()).limit(limit)
            
            rows = await self.session.execute(query)
            for video in rows.scalars():
                results.append(self._video_to_dict(video, "vk_video"))
            
            # VK Clips
            query = select(VKClip).where(
                VKClip.account_id.in_(source_ids),
                VKClip.virality_score.isnot(None),
            )
            if not include_used:
                query = query.where(VKClip.used_in_task_id.is_(None))
            if min_score:
                query = query.where(VKClip.virality_score >= min_score)
            if cutoff_date:
                query = query.where(VKClip.published_at >= cutoff_date)
            query = query.order_by(VKClip.virality_score.desc()).limit(limit)
            
            rows = await self.session.execute(query)
            for clip in rows.scalars():
                results.append(self._video_to_dict(clip, "vk_clip"))
        
        elif platform == "instagram":
            query = select(InstagramPost).where(
                InstagramPost.account_id.in_(source_ids),
                InstagramPost.virality_score.isnot(None),
                InstagramPost.media_type.in_(["video", "reel", "igtv"]),  # Only video content
            )
            if not include_used:
                query = query.where(InstagramPost.used_in_task_id.is_(None))
            if min_score:
                query = query.where(InstagramPost.virality_score >= min_score)
            if cutoff_date:
                query = query.where(InstagramPost.published_at >= cutoff_date)
            query = query.order_by(InstagramPost.virality_score.desc()).limit(limit)
            
            rows = await self.session.execute(query)
            for post in rows.scalars():
                results.append(self._video_to_dict(post, "instagram"))
        
        return results
    
    def _video_to_dict(self, video: Any, video_type: VideoType) -> dict:
        """Convert video model to dict."""
        base = {
            "video_type": video_type,
            "db_id": video.id,
            "account_id": video.account_id,
            "virality_score": video.virality_score,
            "published_at": video.published_at.isoformat() if video.published_at else None,
            "used_in_task_id": video.used_in_task_id,
        }
        
        if video_type == "youtube":
            base.update({
                "external_id": video.video_id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "permalink": video.permalink,
                "download_url": f"https://www.youtube.com/watch?v={video.video_id}",
                "views": video.views,
                "content_type": video.content_type,
            })
        elif video_type == "tiktok":
            base.update({
                "external_id": video.video_id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "permalink": video.permalink,
                "download_url": video.video_url or video.permalink,
                "views": video.views,
            })
        elif video_type == "vk_video":
            base.update({
                "external_id": f"video{video.vk_owner_id}_{video.video_id}",
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "permalink": video.permalink,
                "download_url": video.permalink,
                "views": video.views,
            })
        elif video_type == "vk_clip":
            base.update({
                "external_id": f"clip{video.vk_owner_id}_{video.clip_id}",
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "permalink": video.permalink,
                "download_url": video.permalink,
                "views": video.views,
            })
        elif video_type == "instagram":
            base.update({
                "external_id": video.post_id,
                "title": video.caption[:100] if video.caption else None,
                "thumbnail_url": video.thumbnail_url,
                "permalink": video.permalink,
                "download_url": video.media_url or video.permalink,
                "views": video.views,
                "media_type": video.media_type,
            })
        
        return base
    
    async def get_mixed_pool(
        self,
        project_id: int,
        *,
        total_limit: int = 10,
        new_ratio: float = 0.6,
        new_days: int = 7,
        min_score: float | None = None,
        platform: str | None = None,
    ) -> dict:
        """
        Get mixed pool of new and top historical videos.
        
        Args:
            project_id: Project ID
            total_limit: Total videos to return
            new_ratio: Ratio of new videos (0.6 = 60% new, 40% historical)
            new_days: Days threshold for "new" videos
            min_score: Minimum virality score
            platform: Filter by platform
        
        Returns:
            Dict with new_videos, historical_videos, and combined pool
        """
        new_limit = int(total_limit * new_ratio)
        historical_limit = total_limit - new_limit
        
        # Get new videos (last N days)
        new_videos = await self.get_available_videos(
            project_id,
            platform=platform,
            limit=new_limit,
            min_score=min_score,
            new_only=True,
            new_days=new_days,
        )
        
        # Get all available videos for historical (excluding new)
        cutoff = datetime.now(timezone.utc) - timedelta(days=new_days)
        all_videos = await self.get_available_videos(
            project_id,
            platform=platform,
            limit=total_limit * 2,
            min_score=min_score,
        )
        
        # Filter out new videos for historical pool
        new_ids = {(v["video_type"], v["db_id"]) for v in new_videos}
        historical_videos = [
            v for v in all_videos 
            if (v["video_type"], v["db_id"]) not in new_ids
        ][:historical_limit]
        
        # Combine and sort
        combined = new_videos + historical_videos
        combined.sort(key=lambda x: x.get("virality_score") or 0, reverse=True)
        
        return {
            "new_videos": new_videos,
            "historical_videos": historical_videos,
            "pool": combined[:total_limit],
            "new_count": len(new_videos),
            "historical_count": len(historical_videos),
            "total": len(combined[:total_limit]),
        }
    
    async def mark_video_as_used(
        self,
        video_type: VideoType,
        db_id: int,
        task_id: int,
    ) -> bool:
        """Mark a video as used in a task."""
        now = datetime.now(timezone.utc)
        
        model_map = {
            "youtube": YouTubeVideo,
            "tiktok": TikTokVideo,
            "vk_video": VKVideo,
            "vk_clip": VKClip,
            "instagram": InstagramPost,
        }
        
        model = model_map.get(video_type)
        if not model:
            return False
        
        await self.session.execute(
            update(model)
            .where(model.id == db_id)
            .values(used_in_task_id=task_id, used_at=now)
        )
        return True
    
    async def unmark_video(self, video_type: VideoType, db_id: int) -> bool:
        """Remove used mark from a video."""
        model_map = {
            "youtube": YouTubeVideo,
            "tiktok": TikTokVideo,
            "vk_video": VKVideo,
            "vk_clip": VKClip,
            "instagram": InstagramPost,
        }
        
        model = model_map.get(video_type)
        if not model:
            return False
        
        await self.session.execute(
            update(model)
            .where(model.id == db_id)
            .values(used_in_task_id=None, used_at=None)
        )
        return True
