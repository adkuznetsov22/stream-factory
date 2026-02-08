"""
Watchdog service — finds stuck PublishTasks and marks them as errors.

Stuck criteria:
- status == "processing" and updated_at < now - STUCK_PROCESSING_MINUTES
- status == "publishing" and updated_at < now - STUCK_PUBLISHING_MINUTES
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionLog, PublishTask, StepResult
from app.settings import get_settings

logger = logging.getLogger(__name__)


async def run_watchdog(
    session: AsyncSession, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Find stuck tasks and mark them as errors.

    Returns a report dict.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    stuck_processing_cutoff = now - timedelta(minutes=settings.stuck_processing_minutes)
    stuck_publishing_cutoff = now - timedelta(minutes=settings.stuck_publishing_minutes)

    # Find stuck processing tasks
    processing_q = await session.execute(
        select(PublishTask).where(and_(
            PublishTask.status == "processing",
            PublishTask.updated_at < stuck_processing_cutoff,
        ))
    )
    stuck_processing = list(processing_q.scalars().all())

    # Find stuck publishing tasks
    publishing_q = await session.execute(
        select(PublishTask).where(and_(
            PublishTask.status == "publishing",
            PublishTask.updated_at < stuck_publishing_cutoff,
        ))
    )
    stuck_publishing = list(publishing_q.scalars().all())

    report_items: list[dict] = []

    for task in stuck_processing:
        age_minutes = (now - task.updated_at).total_seconds() / 60
        error_msg = f"watchdog: stuck processing > {settings.stuck_processing_minutes}m (age={age_minutes:.0f}m)"
        item = {
            "task_id": task.id,
            "project_id": task.project_id,
            "old_status": "processing",
            "age_minutes": round(age_minutes),
            "action": "mark_error",
            "error_message": error_msg,
        }

        if not dry_run:
            task.status = "error"
            task.publish_error = error_msg

            # Create StepResult as audit trail
            session.add(StepResult(
                task_id=task.id,
                step_index=9998,
                tool_id="WATCHDOG",
                step_name="Watchdog: stuck processing",
                status="error",
                error_message=error_msg,
                started_at=now,
                completed_at=now,
            ))

            # DecisionLog
            session.add(DecisionLog(
                project_id=task.project_id,
                payload_json={
                    "action": "watchdog_stuck",
                    "task_id": task.id,
                    "old_status": "processing",
                    "age_minutes": round(age_minutes),
                    "new_status": "error",
                },
            ))
            item["action"] = "marked_error"
        else:
            item["action"] = "would_mark_error"

        report_items.append(item)

    for task in stuck_publishing:
        age_minutes = (now - task.updated_at).total_seconds() / 60
        error_msg = f"watchdog: stuck publishing > {settings.stuck_publishing_minutes}m (age={age_minutes:.0f}m)"
        item = {
            "task_id": task.id,
            "project_id": task.project_id,
            "old_status": "publishing",
            "age_minutes": round(age_minutes),
            "action": "mark_error",
            "error_message": error_msg,
        }

        if not dry_run:
            task.status = "error"
            task.publish_error = error_msg

            session.add(StepResult(
                task_id=task.id,
                step_index=9998,
                tool_id="WATCHDOG",
                step_name="Watchdog: stuck publishing",
                status="error",
                error_message=error_msg,
                started_at=now,
                completed_at=now,
            ))

            session.add(DecisionLog(
                project_id=task.project_id,
                payload_json={
                    "action": "watchdog_stuck",
                    "task_id": task.id,
                    "old_status": "publishing",
                    "age_minutes": round(age_minutes),
                    "new_status": "error",
                },
            ))
            item["action"] = "marked_error"
        else:
            item["action"] = "would_mark_error"

        report_items.append(item)

    if not dry_run and report_items:
        await session.commit()
        # Notify about stuck tasks
        try:
            from app.services.notify import notify_warn
            summary = ", ".join(f"#{it['task_id']}({it['old_status']} {it['age_minutes']}m)" for it in report_items[:10])
            await notify_warn(f"Watchdog: {len(report_items)} stuck tasks", summary)
        except Exception:
            pass

    total = len(report_items)
    logger.info(f"[watchdog] Found {total} stuck tasks (dry_run={dry_run})")

    return {
        "stuck_count": total,
        "stuck_processing": len(stuck_processing),
        "stuck_publishing": len(stuck_publishing),
        "items": report_items,
        "dry_run": dry_run,
        "run_at": now.isoformat(),
        "settings": {
            "stuck_processing_minutes": settings.stuck_processing_minutes,
            "stuck_publishing_minutes": settings.stuck_publishing_minutes,
            "auto_requeue": settings.watchdog_auto_requeue,
        },
    }


async def get_health(session: AsyncSession) -> dict[str, Any]:
    """Return system health overview."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Task counts by status
    counts_q = await session.execute(
        select(PublishTask.status, func.count(PublishTask.id))
        .group_by(PublishTask.status)
    )
    counts = {row[0]: row[1] for row in counts_q.all()}

    # Stuck counts
    stuck_processing_cutoff = now - timedelta(minutes=settings.stuck_processing_minutes)
    stuck_publishing_cutoff = now - timedelta(minutes=settings.stuck_publishing_minutes)

    stuck_proc_q = await session.execute(
        select(func.count(PublishTask.id)).where(and_(
            PublishTask.status == "processing",
            PublishTask.updated_at < stuck_processing_cutoff,
        ))
    )
    stuck_pub_q = await session.execute(
        select(func.count(PublishTask.id)).where(and_(
            PublishTask.status == "publishing",
            PublishTask.updated_at < stuck_publishing_cutoff,
        ))
    )

    # Last decisions
    last_decisions_q = await session.execute(
        select(DecisionLog.payload_json, DecisionLog.created_at)
        .order_by(DecisionLog.created_at.desc())
        .limit(10)
    )
    last_decisions = []
    for payload, created_at in last_decisions_q.all():
        action = payload.get("action", "unknown") if isinstance(payload, dict) else "unknown"
        last_decisions.append({
            "action": action,
            "at": created_at.isoformat() if created_at else None,
        })

    return {
        "counts": counts,
        "stuck": {
            "processing": stuck_proc_q.scalar() or 0,
            "publishing": stuck_pub_q.scalar() or 0,
        },
        "scheduler_enabled": settings.scheduler_enabled,
        "watchdog_enabled": settings.watchdog_enabled,
        "celery_enabled": settings.celery_enabled,
        "celery": {
            "task_time_limit_sec": 6 * 3600,
            "visibility_timeout_sec": 7 * 3600,
        },
        "last_decisions": last_decisions,
    }
