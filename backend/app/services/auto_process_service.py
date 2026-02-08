"""
Auto-process service — picks queued tasks and starts pipeline processing,
respecting global and per-destination concurrency limits.

Settings (env):
  AUTO_PROCESS_MAX_PARALLEL              — global max concurrent processing tasks (default 2)
  AUTO_PROCESS_MAX_PARALLEL_PER_DESTINATION — per destination_account_id (default 1)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Candidate, PublishTask
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Statuses that mean "eligible for auto-process start"
ELIGIBLE_STATUSES = {"queued"}

# Statuses that mean "currently running"
RUNNING_STATUSES = {"processing"}


async def run_auto_process(
    session: AsyncSession, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Pick queued tasks and start pipeline processing.

    Args:
        session: DB session
        dry_run: if True, compute report but do NOT start tasks

    Returns report dict with started[], skipped[], concurrency info.
    """
    settings = get_settings()
    max_parallel = settings.auto_process_max_parallel
    max_per_dest = settings.auto_process_max_parallel_per_destination
    now = datetime.now(timezone.utc)

    # ── Count currently processing tasks ──────────────────────
    global_running_q = await session.execute(
        select(func.count(PublishTask.id)).where(
            PublishTask.status.in_(RUNNING_STATUSES)
        )
    )
    global_running = global_running_q.scalar() or 0

    # Per-destination running counts
    per_dest_q = await session.execute(
        select(
            PublishTask.destination_social_account_id,
            func.count(PublishTask.id),
        )
        .where(PublishTask.status.in_(RUNNING_STATUSES))
        .group_by(PublishTask.destination_social_account_id)
    )
    per_dest_running: dict[int | None, int] = {
        row[0]: row[1] for row in per_dest_q.all()
    }

    free_global = max(0, max_parallel - global_running)

    if free_global == 0 and not dry_run:
        logger.info(
            f"[auto_process] Global limit reached ({global_running}/{max_parallel}), nothing to start"
        )

    # ── Fetch eligible tasks sorted by score desc, then created_at asc ──
    eligible_q = await session.execute(
        select(PublishTask)
        .where(PublishTask.status.in_(ELIGIBLE_STATUSES))
        .order_by(PublishTask.created_at.asc())
        .limit(50)
    )
    eligible_tasks = list(eligible_q.scalars().all())

    # Optionally enrich with candidate virality_score for sorting
    task_ids = [t.id for t in eligible_tasks]
    score_map: dict[int, float] = {}
    if task_ids:
        cand_q = await session.execute(
            select(Candidate.linked_publish_task_id, Candidate.virality_score)
            .where(
                Candidate.linked_publish_task_id.in_(task_ids),
                Candidate.virality_score.isnot(None),
            )
        )
        score_map = {row[0]: row[1] for row in cand_q.all()}

    # Sort: highest virality_score first, then created_at asc (already ordered)
    eligible_tasks.sort(
        key=lambda t: (-(score_map.get(t.id) or 0), t.created_at or now)
    )

    started: list[dict] = []
    skipped: list[dict] = []
    slots_used = 0

    for task in eligible_tasks:
        dest_id = task.destination_social_account_id
        dest_current = per_dest_running.get(dest_id, 0)

        # Global limit
        if slots_used >= free_global:
            skipped.append({
                "task_id": task.id,
                "reason": f"global_limit: {global_running + slots_used}/{max_parallel}",
                "score": score_map.get(task.id),
            })
            continue

        # Per-destination limit
        if dest_current >= max_per_dest:
            skipped.append({
                "task_id": task.id,
                "reason": f"per_dest_limit: dest={dest_id} has {dest_current}/{max_per_dest}",
                "score": score_map.get(task.id),
            })
            continue

        if dry_run:
            started.append({
                "task_id": task.id,
                "destination_account_id": dest_id,
                "project_id": task.project_id,
                "score": score_map.get(task.id),
                "dry_run": True,
            })
        else:
            # Mark as processing so no other worker picks it up
            task.status = "processing"
            task.processing_started_at = now
            task.error_message = None
            session.add(task)

            started.append({
                "task_id": task.id,
                "destination_account_id": dest_id,
                "project_id": task.project_id,
                "score": score_map.get(task.id),
            })

        # Update counters
        slots_used += 1
        per_dest_running[dest_id] = dest_current + 1

    if not dry_run and started:
        await session.commit()

    report = {
        "started_count": len(started),
        "skipped_count": len(skipped),
        "started": started,
        "skipped": skipped,
        "concurrency": {
            "global_running_before": global_running,
            "global_running_after": global_running + len(started),
            "max_parallel": max_parallel,
            "max_per_destination": max_per_dest,
            "per_dest_running": {str(k): v for k, v in per_dest_running.items()},
        },
        "dry_run": dry_run,
        "run_at": now.isoformat(),
    }

    if not dry_run and started:
        # Fire-and-forget actual processing in background tasks
        for item in started:
            asyncio.create_task(_process_task_background(item["task_id"]))

    logger.info(
        f"[auto_process] Started {len(started)}, skipped {len(skipped)}, "
        f"running {global_running}/{max_parallel}, dry_run={dry_run}"
    )
    return report


async def _process_task_background(task_id: int):
    """Run TaskProcessor.process_task in a fresh session (fire-and-forget)."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.settings import get_settings
        from app.services.task_processor import TaskProcessor

        settings = get_settings()
        engine = create_async_engine(settings.async_database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            processor = TaskProcessor(session)
            result = await processor.process_task(task_id)
            logger.info(f"[auto_process] Task {task_id} finished: {result.get('status', result.get('error', '?'))}")
    except Exception as e:
        logger.error(f"[auto_process] Task {task_id} background error: {e}")
