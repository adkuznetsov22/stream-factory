"""
Auto-publishing service for completed tasks.
Handles automatic posting of processed videos to destination platforms.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PublishTask, Project, SocialAccount
from .telegram_notifier import notify_task_completed, notify_task_error

logger = logging.getLogger(__name__)


class AutoPublisher:
    """
    Service to automatically publish completed videos to platforms.
    This is a placeholder implementation - actual platform APIs would need
    to be integrated for real publishing.
    """
    
    async def publish_task(
        self,
        session: AsyncSession,
        task_id: int,
    ) -> dict:
        """
        Publish a completed task to its destination platform.
        
        Returns:
            dict with status and optional permalink/error
        """
        # Get task
        query = select(PublishTask).where(PublishTask.id == task_id)
        result = await session.execute(query)
        task = result.scalars().first()
        
        if not task:
            return {"status": "error", "error": "Task not found"}
        
        if task.status != "done":
            return {"status": "error", "error": f"Task not ready for publishing: {task.status}"}
        
        # Get destination account
        acc_query = select(SocialAccount).where(SocialAccount.id == task.destination_social_account_id)
        acc_result = await session.execute(acc_query)
        account = acc_result.scalars().first()
        
        if not account:
            return {"status": "error", "error": "Destination account not found"}
        
        # Get project for notifications
        proj_query = select(Project).where(Project.id == task.project_id)
        proj_result = await session.execute(proj_query)
        project = proj_result.scalars().first()
        project_name = project.name if project else f"Project #{task.project_id}"
        
        try:
            # Platform-specific publishing
            platform = task.platform.lower()
            
            if platform == "youtube":
                result = await self._publish_youtube(task, account)
            elif platform == "tiktok":
                result = await self._publish_tiktok(task, account)
            elif platform == "instagram":
                result = await self._publish_instagram(task, account)
            elif platform == "vk":
                result = await self._publish_vk(task, account)
            else:
                result = {"status": "error", "error": f"Unsupported platform: {platform}"}
            
            if result.get("status") == "published":
                task.status = "published"
                task.permalink = result.get("permalink")
                task.published_at = datetime.utcnow()
                await session.commit()
                
                await notify_task_completed(
                    task_id=task.id,
                    project_name=project_name,
                    platform=platform,
                )
            else:
                task.status = "error"
                task.error_message = result.get("error", "Publishing failed")
                await session.commit()
                
                await notify_task_error(
                    task_id=task.id,
                    project_name=project_name,
                    platform=platform,
                    error_message=result.get("error"),
                )
            
            return result
            
        except Exception as e:
            logger.exception(f"Error publishing task {task_id}")
            task.status = "error"
            task.error_message = str(e)
            await session.commit()
            
            await notify_task_error(
                task_id=task.id,
                project_name=project_name,
                platform=task.platform,
                error_message=str(e),
            )
            
            return {"status": "error", "error": str(e)}
    
    async def _publish_youtube(self, task: PublishTask, account: SocialAccount) -> dict:
        """
        Publish to YouTube.
        Requires YouTube Data API v3 with upload scope.
        """
        # TODO: Implement actual YouTube upload
        # Would need:
        # 1. OAuth2 credentials for the account
        # 2. google-api-python-client
        # 3. Upload via youtube.videos().insert()
        
        logger.info(f"YouTube publishing not implemented for task {task.id}")
        return {
            "status": "error",
            "error": "YouTube auto-publishing not yet implemented. Please upload manually.",
        }
    
    async def _publish_tiktok(self, task: PublishTask, account: SocialAccount) -> dict:
        """
        Publish to TikTok.
        Requires TikTok API access (limited availability).
        """
        # TODO: Implement TikTok upload
        # TikTok's API for posting is very restricted
        
        logger.info(f"TikTok publishing not implemented for task {task.id}")
        return {
            "status": "error",
            "error": "TikTok auto-publishing not yet implemented. Please upload manually.",
        }
    
    async def _publish_instagram(self, task: PublishTask, account: SocialAccount) -> dict:
        """
        Publish to Instagram.
        Requires Instagram Graph API (Business/Creator accounts only).
        """
        # TODO: Implement Instagram upload
        # Requires:
        # 1. Facebook Business account
        # 2. Instagram Graph API access
        # 3. Container creation -> publish flow
        
        logger.info(f"Instagram publishing not implemented for task {task.id}")
        return {
            "status": "error",
            "error": "Instagram auto-publishing not yet implemented. Please upload manually.",
        }
    
    async def _publish_vk(self, task: PublishTask, account: SocialAccount) -> dict:
        """
        Publish to VK.
        Uses VK API video.save + upload.
        """
        # TODO: Implement VK upload
        # Would need:
        # 1. VK access token with video scope
        # 2. video.save to get upload URL
        # 3. Upload video file
        # 4. Confirm upload
        
        logger.info(f"VK publishing not implemented for task {task.id}")
        return {
            "status": "error",
            "error": "VK auto-publishing not yet implemented. Please upload manually.",
        }
    
    async def process_pending_publications(self, session: AsyncSession) -> int:
        """
        Process all tasks that are ready for auto-publishing.
        Called by scheduler.
        
        Returns:
            Number of tasks processed
        """
        # Find tasks that are done and have auto-publish enabled
        query = (
            select(PublishTask)
            .join(Project, PublishTask.project_id == Project.id)
            .where(and_(
                PublishTask.status == "done",
                Project.mode == "AUTO",
            ))
            .limit(10)
        )
        
        result = await session.execute(query)
        tasks = result.scalars().all()
        
        processed = 0
        for task in tasks:
            try:
                await self.publish_task(session, task.id)
                processed += 1
            except Exception as e:
                logger.error(f"Failed to process task {task.id}: {e}")
        
        return processed


# Global singleton
auto_publisher = AutoPublisher()
