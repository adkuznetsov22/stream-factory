"""
Task Generator Service

Automatically generates PublishTasks from selected videos:
- Selects videos from VideoPool
- Creates tasks for each destination account
- Marks videos as used
- Supports daily limits and scheduling
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Project,
    ProjectDestination,
    PublishTask,
    SocialAccount,
)
from app.services.video_pool import VideoPoolService


class TaskGeneratorService:
    """Service for generating publish tasks from video pool."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.video_pool = VideoPoolService(session)
    
    async def get_project(self, project_id: int) -> Project | None:
        """Get project by ID."""
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()
    
    async def get_today_task_count(self, project_id: int) -> int:
        """Get number of tasks created today for a project."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.session.execute(
            select(func.count(PublishTask.id)).where(
                PublishTask.project_id == project_id,
                PublishTask.created_at >= today_start,
            )
        )
        return result.scalar() or 0
    
    async def generate_tasks(
        self,
        project_id: int,
        *,
        count: int = 5,
        platform: str | None = None,
        min_score: float | None = None,
        new_ratio: float = 0.6,
        new_days: int = 7,
        respect_daily_limit: bool = True,
    ) -> dict:
        """
        Generate publish tasks for a project.
        
        Args:
            project_id: Project ID
            count: Number of tasks to generate
            platform: Filter source videos by platform
            min_score: Minimum virality score
            new_ratio: Ratio of new vs historical videos
            new_days: Days threshold for "new" videos
            respect_daily_limit: Check project's daily_limit setting
        
        Returns:
            Dict with generated tasks info
        """
        project = await self.get_project(project_id)
        if not project:
            return {"error": "Project not found", "tasks_created": 0}
        
        # Check project status
        if project.status == "paused":
            return {"error": "Project is paused", "tasks_created": 0}
        
        # Get project settings
        settings = project.settings_json or {}
        daily_limit = settings.get("daily_limit", 100)
        
        # Check daily limit
        if respect_daily_limit:
            today_count = await self.get_today_task_count(project_id)
            remaining = daily_limit - today_count
            if remaining <= 0:
                return {
                    "error": "Daily limit reached",
                    "tasks_created": 0,
                    "daily_limit": daily_limit,
                    "today_count": today_count,
                }
            count = min(count, remaining)
        
        # Get destination accounts
        destinations = await self.video_pool.get_destination_accounts(project_id, platform)
        if not destinations:
            return {"error": "No destination accounts configured", "tasks_created": 0}
        
        # Get video pool
        pool_result = await self.video_pool.get_mixed_pool(
            project_id,
            total_limit=count,
            new_ratio=new_ratio,
            new_days=new_days,
            min_score=min_score,
            platform=platform,
        )
        
        videos = pool_result["pool"]
        if not videos:
            return {
                "error": "No available videos in pool",
                "tasks_created": 0,
                "pool_info": pool_result,
            }
        
        # Generate tasks
        tasks_created = []
        now = datetime.now(timezone.utc)
        
        # Round-robin distribution to destinations
        dest_index = 0
        
        for video in videos:
            destination = destinations[dest_index % len(destinations)]
            dest_index += 1
            
            # Determine platform for task
            video_type = video["video_type"]
            task_platform = self._get_task_platform(video_type)
            
            # Create task
            task = PublishTask(
                project_id=project_id,
                platform=task_platform,
                destination_social_account_id=destination["account_id"],
                source_social_account_id=video["account_id"],
                external_id=video["external_id"],
                permalink=video.get("permalink"),
                preview_url=video.get("thumbnail_url"),
                download_url=video.get("download_url"),
                caption_text=video.get("title"),
                status="queued",
                preset_id=project.preset_id,
                created_at=now,
            )
            self.session.add(task)
            await self.session.flush()  # Get task ID
            
            # Mark video as used
            await self.video_pool.mark_video_as_used(
                video["video_type"],
                video["db_id"],
                task.id,
            )
            
            tasks_created.append({
                "task_id": task.id,
                "video_type": video["video_type"],
                "external_id": video["external_id"],
                "virality_score": video["virality_score"],
                "destination_account_id": destination["account_id"],
                "destination_label": destination["label"],
            })
        
        await self.session.commit()
        
        return {
            "ok": True,
            "tasks_created": len(tasks_created),
            "tasks": tasks_created,
            "pool_info": {
                "new_count": pool_result["new_count"],
                "historical_count": pool_result["historical_count"],
            },
        }
    
    def _get_task_platform(self, video_type: str) -> str:
        """Map video type to platform string."""
        mapping = {
            "youtube": "YouTube",
            "tiktok": "TikTok",
            "vk_video": "VK",
            "vk_clip": "VK",
            "instagram": "Instagram",
        }
        return mapping.get(video_type, "Unknown")
    
    async def generate_for_all_active_projects(
        self,
        *,
        count_per_project: int = 5,
    ) -> dict:
        """
        Generate tasks for all active projects (for scheduler).
        
        Returns:
            Dict with results per project
        """
        result = await self.session.execute(
            select(Project).where(
                Project.status == "active",
                Project.mode == "AUTO",
            )
        )
        projects = result.scalars().all()
        
        results = {}
        for project in projects:
            settings = project.settings_json or {}
            
            gen_result = await self.generate_tasks(
                project.id,
                count=settings.get("tasks_per_run", count_per_project),
                min_score=settings.get("min_virality_score"),
                new_ratio=settings.get("new_videos_ratio", 0.6),
                new_days=settings.get("new_days", 7),
            )
            results[project.id] = {
                "project_name": project.name,
                **gen_result,
            }
        
        return {
            "projects_processed": len(projects),
            "results": results,
        }
