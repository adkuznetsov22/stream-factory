"""
Auto-publishing service — thin wrapper around P01_PUBLISH pipeline step.

P01_PUBLISH is the single source of truth for publishing logic
(idempotency, advisory locks, retry with backoff, adapter dispatch).

AutoPublisher exists as a convenience layer for:
- Manual "publish now" endpoint (POST /publish-tasks/{id}/publish)
- Scheduler batch job (process_pending_publications)

It constructs a StepContext and delegates to the P01_PUBLISH handler.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PublishTask, Project

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
TASKS_DIR = DATA_DIR / "tasks"


class AutoPublisher:
    """Thin wrapper that delegates to P01_PUBLISH pipeline handler."""

    async def publish_task(
        self,
        session: AsyncSession,
        task_id: int,
    ) -> dict:
        """Publish a completed task via P01_PUBLISH handler.

        Can be called from endpoints or scheduler — all real logic
        (idempotency, locks, retry, adapter) lives in P01_PUBLISH.
        """
        task = await session.get(PublishTask, task_id)
        if not task:
            return {"status": "error", "error": "Task not found"}

        if task.status not in ("done", "error"):
            # Allow re-publish of errored tasks, but not queued/processing
            if task.status == "published":
                return {
                    "status": "already_published",
                    "published_url": task.published_url,
                    "published_external_id": task.published_external_id,
                }
            if task.status in ("queued", "processing", "publishing"):
                return {"status": "error", "error": f"Task not ready: {task.status}"}

        from app.services.pipeline_executor import StepContext, PipelineExecutor

        # Build minimal StepContext for P01_PUBLISH
        task_dir = TASKS_DIR / str(task.id)
        task_dir.mkdir(parents=True, exist_ok=True)

        def log_cb(msg: str):
            logger.info(f"[auto_publish][task={task_id}] {msg}")

        ctx = StepContext(task_id=task_id, task_dir=task_dir, log_cb=log_cb)
        ctx.session = session
        ctx.publish_task = task
        ctx.platform = task.platform
        ctx.destination_account_id = task.destination_social_account_id

        # Resolve current_video so P01_PUBLISH finds the file
        for name in ("final.mp4", "ready.mp4", "output.mp4"):
            p = task_dir / name
            if p.exists():
                ctx.set_output_video(p)
                break

        handler = PipelineExecutor.get_handler("P01_PUBLISH")
        if not handler:
            return {"status": "error", "error": "P01_PUBLISH handler not registered"}

        try:
            result = await handler(ctx, {})
        except RuntimeError as exc:
            logger.error(f"[auto_publish] task={task_id} failed: {exc}")
            return {"status": "error", "error": str(exc)}

        if result.get("published"):
            return {
                "status": "published",
                "published_url": result.get("published_url"),
                "external_id": result.get("published_external_id"),
                "platform": result.get("platform"),
                "attempts_count": result.get("attempts_count"),
            }
        elif result.get("skipped"):
            return {
                "status": "skipped",
                "reason": result.get("reason"),
            }
        else:
            return {"status": "error", "error": "Unexpected result from P01_PUBLISH"}

    async def process_pending_publications(self, session: AsyncSession) -> int:
        """Process all tasks that are ready for auto-publishing. Called by scheduler."""
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
