"""
Task control: cooperative pause/resume/cancel for pipeline processing.

Exceptions:
- TaskPaused: raised when pause_requested_at is set
- TaskCanceled: raised when cancel_requested_at is set

check_control_flags() is called between steps in PipelineExecutor
to implement cooperative cancellation/pause.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PublishTask, StepResult

logger = logging.getLogger(__name__)


class TaskPaused(Exception):
    """Raised when a task has been paused by the user."""
    pass


class TaskCanceled(Exception):
    """Raised when a task has been canceled by the user."""
    pass


async def check_control_flags(session: AsyncSession, task_id: int) -> None:
    """Check pause/cancel flags and act accordingly.

    Must be called between pipeline steps for cooperative control.

    Raises:
        TaskCanceled: if cancel_requested_at is set
        TaskPaused: if pause_requested_at is set
    """
    now = datetime.now(timezone.utc)

    task = await session.get(PublishTask, task_id)
    if not task:
        raise RuntimeError(f"Task {task_id} not found during control check")

    # Cancel takes priority over pause
    if task.cancel_requested_at is not None:
        task.status = "canceled"
        task.canceled_at = now
        session.add(task)

        session.add(StepResult(
            task_id=task_id,
            step_index=9996,
            tool_id="CONTROL",
            step_name="Canceled by user",
            status="canceled",
            error_message=f"Canceled by user: {task.cancel_reason or 'no reason'}",
            started_at=now,
            completed_at=now,
        ))
        await session.commit()

        logger.info(f"[task_control] Task {task_id} canceled (reason: {task.cancel_reason})")
        raise TaskCanceled(f"Task {task_id} canceled by user")

    if task.pause_requested_at is not None:
        task.status = "paused"
        task.paused_at = now
        session.add(task)

        session.add(StepResult(
            task_id=task_id,
            step_index=9996,
            tool_id="CONTROL",
            step_name="Paused by user",
            status="paused",
            error_message=f"Paused by user: {task.pause_reason or 'no reason'}",
            started_at=now,
            completed_at=now,
        ))
        await session.commit()

        logger.info(f"[task_control] Task {task_id} paused (reason: {task.pause_reason})")
        raise TaskPaused(f"Task {task_id} paused by user")
