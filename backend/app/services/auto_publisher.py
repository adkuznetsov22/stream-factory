"""
Auto-publishing service for completed tasks.

Uses PublisherAdapter layer for platform-specific uploads.
All results (success and error) are saved explicitly into
PublishTask fields and StepResult — no silent failures.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PublishTask, Project, SocialAccount, StepResult
from .publisher_adapter import get_publisher, PublishResult
from .telegram_notifier import notify_task_completed, notify_task_error

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
TASKS_DIR = DATA_DIR / "tasks"


class AutoPublisher:
    """
    Publishes completed videos via platform-specific adapters.
    Saves published_url, published_external_id, publish_error into PublishTask.
    Logs errors into StepResult for traceability.
    """

    async def publish_task(
        self,
        session: AsyncSession,
        task_id: int,
    ) -> dict:
        """Publish a completed task to its destination platform."""
        task = await session.get(PublishTask, task_id)
        if not task:
            return {"status": "error", "error": "Task not found"}

        if task.status != "done":
            return {"status": "error", "error": f"Task not ready for publishing: {task.status}"}

        account = await session.get(SocialAccount, task.destination_social_account_id)
        if not account:
            return {"status": "error", "error": "Destination account not found"}

        project = await session.get(Project, task.project_id)
        project_name = project.name if project else f"Project #{task.project_id}"

        platform = task.platform.lower()
        adapter = get_publisher(platform)
        if not adapter:
            err = f"Unsupported platform: {platform}"
            await self._save_error(session, task, project_name, err)
            return {"status": "error", "error": err}

        # Resolve output file
        file_path = self._resolve_output_file(task)
        if not file_path or not file_path.exists():
            err = f"Output video not found at {file_path}"
            await self._save_error(session, task, project_name, err)
            return {"status": "error", "error": err}

        # Prepare metadata
        title = task.caption_text or task.instructions or f"Video #{task.id}"
        description = task.caption_text or ""
        tags = self._extract_tags(task)

        logger.info(f"[publish] task={task.id} platform={platform} file={file_path}")

        try:
            result: PublishResult = await adapter.publish(
                task=task,
                account=account,
                file_path=file_path,
                title=title,
                description=description,
                tags=tags,
            )
        except Exception as exc:
            logger.exception(f"[publish] Unhandled error for task {task_id}")
            result = PublishResult(
                success=False,
                platform=platform,
                error=f"Unhandled exception: {exc}",
            )

        # Persist result
        now = datetime.now(timezone.utc)

        if result.success:
            task.status = "published"
            task.published_url = result.url
            task.published_external_id = result.external_id
            task.published_at = now
            task.publish_error = None
            session.add(task)
            await session.commit()

            # Save StepResult for publish step
            await self._save_step_result(
                session, task,
                status="done",
                output_data=result.to_dict(),
            )

            await notify_task_completed(
                task_id=task.id,
                project_name=project_name,
                platform=platform,
            )

            return {
                "status": "published",
                "published_url": result.url,
                "external_id": result.external_id,
                "platform": result.platform,
            }
        else:
            await self._save_error(
                session, task, project_name,
                result.error or "Publishing failed",
                result=result,
            )
            return {"status": "error", "error": result.error}

    async def _save_error(
        self,
        session: AsyncSession,
        task: PublishTask,
        project_name: str,
        error_msg: str,
        result: PublishResult | None = None,
    ):
        """Persist error into task + StepResult + notify."""
        task.status = "error"
        task.publish_error = error_msg
        task.error_message = error_msg
        session.add(task)
        await session.commit()

        await self._save_step_result(
            session, task,
            status="error",
            error_message=error_msg,
            output_data=result.to_dict() if result else {"error": error_msg},
        )

        await notify_task_error(
            task_id=task.id,
            project_name=project_name,
            platform=task.platform,
            error_message=error_msg,
        )

    async def _save_step_result(
        self,
        session: AsyncSession,
        task: PublishTask,
        *,
        status: str,
        output_data: dict | None = None,
        error_message: str | None = None,
    ):
        """Create a StepResult record for the publish step."""
        now = datetime.now(timezone.utc)
        step = StepResult(
            task_id=task.id,
            step_index=9999,  # publish — виртуальный шаг после всех pipeline steps
            tool_id="PUBLISH",
            step_name="Platform publish",
            status=status,
            started_at=now,
            completed_at=now,
            output_data=output_data,
            error_message=error_message,
            moderation_status="auto_approved",
            can_retry=True,
        )
        session.add(step)
        await session.commit()

    def _resolve_output_file(self, task: PublishTask) -> Path | None:
        """Find the final output video for a task."""
        task_dir = TASKS_DIR / str(task.id)
        # Prefer final.mp4, then ready.mp4
        for name in ("final.mp4", "ready.mp4", "output.mp4"):
            p = task_dir / name
            if p.exists():
                return p
        # Check artifacts for explicit path
        if task.artifacts and isinstance(task.artifacts, dict):
            path_str = task.artifacts.get("output_path") or task.artifacts.get("final_path")
            if path_str:
                p = Path(path_str)
                if p.exists():
                    return p
        return None

    def _extract_tags(self, task: PublishTask) -> list[str]:
        """Extract hashtags / tags from task metadata."""
        tags: list[str] = []
        if task.artifacts and isinstance(task.artifacts, dict):
            t = task.artifacts.get("tags") or task.artifacts.get("hashtags") or []
            if isinstance(t, list):
                tags = [str(x) for x in t]
        return tags

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
