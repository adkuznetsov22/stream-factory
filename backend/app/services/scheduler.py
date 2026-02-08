"""
Scheduler Service

Manages automatic task generation for projects:
- Runs periodic jobs for active AUTO-mode projects
- Configurable intervals per project
- Sync scheduling for all platforms

Single-leader election via Postgres advisory locks:
- Only the instance that acquires the lock executes the tick
- Other instances silently skip
- Controlled by SCHEDULER_ENABLED env (default: true)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import Project
from app.settings import get_settings

logger = logging.getLogger("scheduler")

# Advisory lock keys (arbitrary int64 — unique per job type)
LOCK_TASK_GENERATION = 900_001
LOCK_SYNC_ACCOUNTS = 900_002
LOCK_SYNC_PUBLISHED_METRICS = 900_003
LOCK_AGGREGATE_SNAPSHOTS = 900_004
LOCK_CALIBRATE_SCORING = 900_005
LOCK_AUTO_APPROVE = 900_006
LOCK_AUTO_PROCESS = 900_007


class SchedulerService:
    """Service for scheduling automatic task generation.

    Uses Postgres pg_try_advisory_lock on each tick so that only
    one backend instance (the leader) executes the job while
    other instances skip silently.
    """
    
    _instance: "SchedulerService | None" = None
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._session_factory: async_sessionmaker | None = None
        self._running = False
        self._leader_logged = False
    
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
    
    async def _try_advisory_lock(self, session: AsyncSession, lock_key: int) -> bool:
        """Try to acquire a Postgres session-level advisory lock (non-blocking).

        Returns True if this instance acquired the lock (is leader for this tick).
        The lock is automatically released when the session/connection closes.
        """
        result = await session.execute(text(f"SELECT pg_try_advisory_lock({lock_key})"))
        acquired = result.scalar()
        return bool(acquired)

    async def _release_advisory_lock(self, session: AsyncSession, lock_key: int):
        """Explicitly release advisory lock after job completion."""
        await session.execute(text(f"SELECT pg_advisory_unlock({lock_key})"))

    def start(self):
        """Start the scheduler (respects SCHEDULER_ENABLED env)."""
        settings = get_settings()
        if not settings.scheduler_enabled:
            logger.info("Scheduler DISABLED by SCHEDULER_ENABLED=false — skipping start")
            return

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

        self.scheduler.add_job(
            self._run_sync_published_metrics,
            IntervalTrigger(hours=1),
            id="sync_published_metrics",
            name="Sync published video metrics",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._run_aggregate_snapshots,
            IntervalTrigger(hours=24),
            id="aggregate_snapshots",
            name="Aggregate old metric snapshots",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._run_calibrate_scoring,
            IntervalTrigger(hours=24),
            id="calibrate_scoring",
            name="Calibrate scoring thresholds",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._run_auto_approve,
            IntervalTrigger(minutes=60),
            id="auto_approve",
            name="Auto-approve candidates",
            replace_existing=True,
        )

        # Auto-process: start pipeline for queued tasks
        settings = get_settings()
        if settings.auto_process_enabled:
            self.scheduler.add_job(
                self._run_auto_process,
                IntervalTrigger(minutes=settings.auto_process_interval_minutes),
                id="auto_process",
                name="Auto-process queued tasks",
                replace_existing=True,
            )
        
        self.scheduler.start()
        self._running = True
        logger.info("Scheduler started (single-leader mode via advisory locks)")
    
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
        """Run task generation for all active AUTO projects.

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_TASK_GENERATION)
            if not acquired:
                logger.debug("[task_generation] Advisory lock not acquired — another instance is leader, skipping tick")
                return None

            try:
                logger.info("[task_generation] LEADER — running task generation")
                from app.services.task_generator import TaskGeneratorService

                generator = TaskGeneratorService(session)
                result = await generator.generate_for_all_active_projects()

                logger.info(
                    "[task_generation] Completed: %d projects processed",
                    result.get("projects_processed", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_TASK_GENERATION)
    
    async def _run_sync_accounts(self):
        """Sync all source accounts for active projects.

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_SYNC_ACCOUNTS)
            if not acquired:
                logger.debug("[sync_accounts] Advisory lock not acquired — another instance is leader, skipping tick")
                return None

            try:
                logger.info("[sync_accounts] LEADER — running account sync")
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

                logger.info("[sync_accounts] Completed: %d synced, %d errors", synced, len(errors))
                return {"synced": synced, "errors": errors}
            finally:
                await self._release_advisory_lock(session, LOCK_SYNC_ACCOUNTS)
    
    async def _run_sync_published_metrics(self):
        """Sync metrics for published videos (views, likes, comments, shares).

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_SYNC_PUBLISHED_METRICS)
            if not acquired:
                logger.debug("[sync_published_metrics] Advisory lock not acquired — skipping tick")
                return None

            try:
                logger.info("[sync_published_metrics] LEADER — syncing published video metrics")
                from app.services.sync_published_metrics import sync_published_metrics

                result = await sync_published_metrics(session)

                logger.info(
                    "[sync_published_metrics] Completed: %d synced, %d errors",
                    result.get("synced", 0),
                    result.get("errors", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_SYNC_PUBLISHED_METRICS)

    async def _run_aggregate_snapshots(self):
        """Aggregate old metric snapshots (>30d → daily, >180d → weekly).

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_AGGREGATE_SNAPSHOTS)
            if not acquired:
                logger.debug("[aggregate_snapshots] Advisory lock not acquired — skipping tick")
                return None

            try:
                logger.info("[aggregate_snapshots] LEADER — aggregating old snapshots")
                from app.services.sync_published_metrics import aggregate_old_snapshots

                result = await aggregate_old_snapshots(session)

                logger.info(
                    "[aggregate_snapshots] Completed: %d daily, %d weekly deleted",
                    result.get("deleted_daily", 0),
                    result.get("deleted_weekly", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_AGGREGATE_SNAPSHOTS)

    async def _run_calibrate_scoring(self):
        """Calibrate scoring thresholds for all projects (daily).

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_CALIBRATE_SCORING)
            if not acquired:
                logger.debug("[calibrate_scoring] Advisory lock not acquired — skipping tick")
                return None

            try:
                logger.info("[calibrate_scoring] LEADER — calibrating scoring thresholds")
                from app.services.calibrate_scoring import calibrate_all_projects

                result = await calibrate_all_projects(session)

                logger.info(
                    "[calibrate_scoring] Completed: %d calibrated, %d skipped",
                    result.get("calibrated", 0),
                    result.get("skipped", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_CALIBRATE_SCORING)

    async def _run_auto_approve(self):
        """Auto-approve candidates for all enabled projects (hourly).

        Protected by advisory lock — only one instance executes per tick.
        """
        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_AUTO_APPROVE)
            if not acquired:
                logger.debug("[auto_approve] Advisory lock not acquired — skipping tick")
                return None

            try:
                logger.info("[auto_approve] LEADER — running auto-approve")
                from app.services.auto_approve_service import run_auto_approve_all

                result = await run_auto_approve_all(session)

                logger.info(
                    "[auto_approve] Completed: %d projects, %d total approved",
                    result.get("processed", 0),
                    result.get("total_approved", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_AUTO_APPROVE)

    async def _run_auto_process(self):
        """Auto-process queued tasks with concurrency limits.

        Protected by advisory lock — only one instance executes per tick.
        """
        settings = get_settings()
        if not settings.auto_process_enabled:
            return None

        async with await self._get_session() as session:
            acquired = await self._try_advisory_lock(session, LOCK_AUTO_PROCESS)
            if not acquired:
                logger.debug("[auto_process] Advisory lock not acquired — skipping tick")
                return None

            try:
                logger.info("[auto_process] LEADER — running auto-process")
                from app.services.auto_process_service import run_auto_process

                result = await run_auto_process(session)

                logger.info(
                    "[auto_process] Completed: %d started, %d skipped",
                    result.get("started_count", 0),
                    result.get("skipped_count", 0),
                )
                return result
            finally:
                await self._release_advisory_lock(session, LOCK_AUTO_PROCESS)

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
