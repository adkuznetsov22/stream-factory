"""
Scheduler Service

Manages automatic task generation for projects:
- Runs periodic jobs for active AUTO-mode projects
- Configurable intervals per project
- Sync scheduling for all platforms
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import Project
from app.settings import get_settings

logger = logging.getLogger("scheduler")


class SchedulerService:
    """Service for scheduling automatic task generation."""
    
    _instance: "SchedulerService | None" = None
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._session_factory: async_sessionmaker | None = None
        self._running = False
    
    @classmethod
    def get_instance(cls) -> "SchedulerService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def configure(self, database_url: str):
        """Configure database connection."""
        engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    async def _get_session(self) -> AsyncSession:
        """Get database session."""
        if not self._session_factory:
            settings = get_settings()
            self.configure(settings.database_url)
        return self._session_factory()
    
    def start(self):
        """Start the scheduler."""
        if self._running:
            return
        
        # Add default jobs
        self.scheduler.add_job(
            self._run_task_generation,
            IntervalTrigger(minutes=30),
            id="task_generation",
            name="Auto task generation",
            replace_existing=True,
        )
        
        self.scheduler.add_job(
            self._run_sync_accounts,
            IntervalTrigger(hours=6),
            id="sync_accounts",
            name="Sync source accounts",
            replace_existing=True,
        )
        
        self.scheduler.start()
        self._running = True
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if not self._running:
            return
        self.scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
    
    async def _run_task_generation(self):
        """Run task generation for all active AUTO projects."""
        logger.info("Running scheduled task generation")
        
        async with await self._get_session() as session:
            from app.services.task_generator import TaskGeneratorService
            
            generator = TaskGeneratorService(session)
            result = await generator.generate_for_all_active_projects()
            
            logger.info(
                "Task generation completed: %d projects processed",
                result.get("projects_processed", 0)
            )
            return result
    
    async def _run_sync_accounts(self):
        """Sync all source accounts for active projects."""
        logger.info("Running scheduled account sync")
        
        async with await self._get_session() as session:
            from app.models import ProjectSource, SocialAccount
            
            # Get all active sources
            result = await session.execute(
                select(ProjectSource, SocialAccount, Project)
                .join(SocialAccount, ProjectSource.social_account_id == SocialAccount.id)
                .join(Project, ProjectSource.project_id == Project.id)
                .where(
                    ProjectSource.is_active == True,
                    Project.status == "active",
                    Project.mode == "AUTO",
                )
            )
            
            sources = result.fetchall()
            synced = 0
            errors = []
            
            for source, account, project in sources:
                try:
                    await self._sync_account(session, account)
                    synced += 1
                except Exception as e:
                    logger.error("Failed to sync account %d: %s", account.id, e)
                    errors.append({"account_id": account.id, "error": str(e)})
            
            logger.info("Account sync completed: %d synced, %d errors", synced, len(errors))
            return {"synced": synced, "errors": errors}
    
    async def _sync_account(self, session: AsyncSession, account):
        """Sync a single account based on platform."""
        platform = account.platform.value.lower() if hasattr(account.platform, 'value') else str(account.platform).lower()
        
        if platform == "youtube":
            from app.services.youtube_sync import sync_youtube_account
            await sync_youtube_account(session, account.id)
        elif platform == "tiktok":
            from app.services.tiktok_sync import sync_tiktok_account
            await sync_tiktok_account(session, account.id)
        elif platform == "vk":
            from app.services.vk_sync import sync_vk_account
            await sync_vk_account(session, account.id)
        elif platform == "instagram":
            from app.services.instagram_sync import sync_instagram_account
            await sync_instagram_account(session, account.id)
    
    def add_project_job(
        self,
        project_id: int,
        interval_minutes: int = 60,
        tasks_per_run: int = 5,
    ):
        """Add a custom job for a specific project."""
        job_id = f"project_{project_id}_tasks"
        
        async def project_task():
            async with await self._get_session() as session:
                from app.services.task_generator import TaskGeneratorService
                generator = TaskGeneratorService(session)
                return await generator.generate_tasks(project_id, count=tasks_per_run)
        
        self.scheduler.add_job(
            project_task,
            IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name=f"Project {project_id} task generation",
            replace_existing=True,
        )
        logger.info("Added job for project %d (interval: %d min)", project_id, interval_minutes)
    
    def remove_project_job(self, project_id: int):
        """Remove job for a specific project."""
        job_id = f"project_{project_id}_tasks"
        try:
            self.scheduler.remove_job(job_id)
            logger.info("Removed job for project %d", project_id)
        except Exception:
            pass
    
    def get_jobs(self) -> list[dict]:
        """Get list of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            })
        return jobs
    
    async def run_now(self, job_id: str) -> dict:
        """Run a job immediately."""
        job = self.scheduler.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}
        
        try:
            result = await job.func()
            return {"ok": True, "result": result}
        except Exception as e:
            logger.error("Failed to run job %s: %s", job_id, e)
            return {"error": str(e)}


# Global instance
scheduler_service = SchedulerService.get_instance()
