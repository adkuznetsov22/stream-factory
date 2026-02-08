"""
Operations endpoints — watchdog, health, system status, bulk task control.

Security: in prod (APP_ENV=prod/staging), all /api/ops/* require X-Ops-Key header.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Candidate, PublishTask, StepResult
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _ops_auth(x_ops_key: str | None = Header(default=None)):
    """Security gate: require OPS_API_KEY in prod/staging."""
    settings = get_settings()
    if settings.app_env in ("prod", "staging") and settings.ops_api_key:
        if x_ops_key != settings.ops_api_key:
            raise HTTPException(status_code=403, detail="Invalid or missing X-Ops-Key")


router = APIRouter(prefix="/api/ops", tags=["ops"], dependencies=[Depends(_ops_auth)])

SessionDep = Depends(get_session)


# ── Pydantic models for bulk requests ────────────────────────
class BulkIdsBody(BaseModel):
    ids: List[int]
    reason: Optional[str] = None

class BulkPriorityBody(BaseModel):
    ids: List[int]
    priority: int


@router.post("/watchdog")
async def run_watchdog_endpoint(
    dry_run: bool = Query(default=True),
    session: AsyncSession = SessionDep,
):
    """Run watchdog to find and mark stuck tasks."""
    from app.services.watchdog_service import run_watchdog
    return await run_watchdog(session, dry_run=dry_run)


@router.get("/health")
async def health_endpoint(
    session: AsyncSession = SessionDep,
):
    """System health overview: task counts, stuck tasks, scheduler, preflight, limits."""
    from app.services.watchdog_service import get_health
    from app.services.preflight import run_preflight

    base = await get_health(session)
    settings = get_settings()

    # Preflight checks (cached 60s)
    preflight = await run_preflight()
    base["preflight"] = preflight

    # Queue depth (best-effort via Redis llen)
    queue_depth = None
    if settings.celery_enabled:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            queue_depth = await r.llen("pipeline")
            await r.aclose()
        except Exception:
            queue_depth = -1
    base["queue_depth"] = queue_depth

    # Scheduler jobs status
    base["scheduler_jobs"] = {
        "auto_process": settings.auto_process_enabled,
        "watchdog": settings.watchdog_enabled,
        "scheduler": settings.scheduler_enabled,
    }

    # Limits / config
    base["limits"] = {
        "app_env": settings.app_env,
        "auto_process_max_parallel": settings.auto_process_max_parallel,
        "auto_process_max_parallel_per_destination": settings.auto_process_max_parallel_per_destination,
        "auto_process_interval_minutes": settings.auto_process_interval_minutes,
        "pipeline_default_step_timeout_sec": settings.pipeline_default_step_timeout_sec,
        "pipeline_ffmpeg_timeout_sec": settings.pipeline_ffmpeg_timeout_sec,
        "pipeline_whisper_timeout_sec": settings.pipeline_whisper_timeout_sec,
        "max_ffmpeg_concurrency": settings.max_ffmpeg_concurrency,
        "max_whisper_concurrency": settings.max_whisper_concurrency,
        "redis_semaphore_ttl_sec": settings.redis_semaphore_ttl_sec,
        "semaphore_wait_timeout_sec": settings.semaphore_wait_timeout_sec,
        "stuck_processing_minutes": settings.stuck_processing_minutes,
        "stuck_publishing_minutes": settings.stuck_publishing_minutes,
    }

    return base


# ── Backups ──────────────────────────────────────────────────
@router.get("/backups/latest")
async def list_backups():
    """List recent backup files."""
    settings = get_settings()
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.exists():
        return {"backups": [], "backup_dir": str(backup_dir), "exists": False}

    files = sorted(backup_dir.glob("*.sql*"), key=lambda f: f.stat().st_mtime, reverse=True)
    items = []
    for f in files[:settings.backup_keep_last + 5]:
        st = f.stat()
        items.append({
            "name": f.name,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })
    return {"backups": items, "backup_dir": str(backup_dir), "exists": True}


@router.post("/backups/create")
async def create_backup():
    """Trigger a pg_dump backup manually."""
    from app.services.backup import run_backup
    result = await run_backup()
    return result


# ── Task list ────────────────────────────────────────────────
@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = SessionDep,
):
    """List tasks with lightweight fields for ops dashboard."""
    q = select(PublishTask)
    filters = []
    if status:
        filters.append(PublishTask.status == status)
    if project_id:
        filters.append(PublishTask.project_id == project_id)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(PublishTask.priority.desc(), PublishTask.updated_at.desc()).limit(limit)

    result = await session.execute(q)
    tasks = result.scalars().all()

    # Batch-load candidate info for virality_score
    task_ids = [t.id for t in tasks]
    cand_map: dict[int, dict] = {}
    if task_ids:
        cq = await session.execute(
            select(Candidate.linked_publish_task_id, Candidate.id, Candidate.virality_score)
            .where(Candidate.linked_publish_task_id.in_(task_ids))
        )
        for tid, cid, vs in cq.all():
            cand_map[tid] = {"candidate_id": cid, "virality_score": vs}

    items = []
    for t in tasks:
        ci = cand_map.get(t.id, {})
        items.append({
            "id": t.id,
            "status": t.status,
            "project_id": t.project_id,
            "platform": t.platform,
            "destination_social_account_id": t.destination_social_account_id,
            "candidate_id": ci.get("candidate_id"),
            "virality_score": ci.get("virality_score"),
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "pause_requested_at": t.pause_requested_at.isoformat() if t.pause_requested_at else None,
            "paused_at": t.paused_at.isoformat() if t.paused_at else None,
            "cancel_requested_at": t.cancel_requested_at.isoformat() if t.cancel_requested_at else None,
            "canceled_at": t.canceled_at.isoformat() if t.canceled_at else None,
            "celery_task_id": t.celery_task_id,
        })
    return {"tasks": items, "total": len(items)}


# ── Bulk helpers ─────────────────────────────────────────────
def _revoke_if_queued(task: PublishTask, now: datetime, session, action_label: str) -> bool:
    """Revoke Celery task if queued with celery_task_id. Returns True if revoked."""
    if task.status == "queued" and task.celery_task_id:
        try:
            from app.worker.celery_app import celery_app as _celery
            _celery.control.revoke(task.celery_task_id, terminate=False)
            session.add(StepResult(
                task_id=task.id, step_index=9996, tool_id="CONTROL",
                step_name=f"Revoke queued task ({action_label})",
                status="done",
                output_data={"action": "revoke", "celery_task_id": task.celery_task_id},
                started_at=now, completed_at=now,
            ))
            return True
        except Exception as e:
            logger.warning(f"[bulk-{action_label}] Failed to revoke {task.celery_task_id}: {e}")
    return False


# ── Bulk enqueue ─────────────────────────────────────────────
@router.post("/tasks/bulk-enqueue")
async def bulk_enqueue(body: BulkIdsBody, session: AsyncSession = SessionDep):
    from app.settings import get_settings
    settings = get_settings()
    if not settings.celery_enabled:
        return {"ok": [], "failed": [{"id": i, "reason": "celery_disabled"} for i in body.ids]}

    from app.worker.tasks import process_task as celery_process_task

    ok, failed = [], []
    for tid in body.ids:
        task = await session.get(PublishTask, tid)
        if not task:
            failed.append({"id": tid, "reason": "not_found"})
            continue
        if task.status not in ("queued", "error", "ready_for_review", "done", "ready_for_publish"):
            failed.append({"id": tid, "reason": f"invalid_status:{task.status}"})
            continue

        task.status = "queued"
        task.publish_error = None
        task.pause_requested_at = None
        task.paused_at = None
        task.pause_reason = None
        task.cancel_requested_at = None
        task.canceled_at = None
        task.cancel_reason = None
        session.add(task)
        await session.flush()

        result = celery_process_task.apply_async(args=[tid], queue="pipeline")
        task.celery_task_id = result.id
        session.add(task)
        ok.append(tid)

    await session.commit()
    return {"ok": ok, "failed": failed}


# ── Bulk pause ───────────────────────────────────────────────
@router.post("/tasks/bulk-pause")
async def bulk_pause(body: BulkIdsBody, session: AsyncSession = SessionDep):
    allowed = {"queued", "processing", "ready_for_review", "done", "ready_for_publish"}
    now = datetime.now(timezone.utc)
    ok, failed = [], []

    for tid in body.ids:
        task = await session.get(PublishTask, tid)
        if not task:
            failed.append({"id": tid, "reason": "not_found"})
            continue
        if task.status not in allowed:
            failed.append({"id": tid, "reason": f"invalid_status:{task.status}"})
            continue

        _revoke_if_queued(task, now, session, "pause")

        if task.status in ("queued", "ready_for_review", "done", "ready_for_publish"):
            task.status = "paused"
            task.paused_at = now
        task.pause_requested_at = now
        task.pause_reason = body.reason
        session.add(task)
        ok.append(tid)

    await session.commit()
    return {"ok": ok, "failed": failed}


# ── Bulk resume ──────────────────────────────────────────────
@router.post("/tasks/bulk-resume")
async def bulk_resume(body: BulkIdsBody, session: AsyncSession = SessionDep):
    from app.settings import get_settings
    settings = get_settings()

    ok, failed = [], []
    for tid in body.ids:
        task = await session.get(PublishTask, tid)
        if not task:
            failed.append({"id": tid, "reason": "not_found"})
            continue
        if task.status != "paused":
            failed.append({"id": tid, "reason": f"invalid_status:{task.status}"})
            continue

        task.status = "queued"
        task.pause_requested_at = None
        task.paused_at = None
        task.pause_reason = None
        session.add(task)
        await session.flush()

        if settings.celery_enabled:
            from app.worker.tasks import process_task as celery_process_task
            result = celery_process_task.apply_async(args=[tid], queue="pipeline")
            task.celery_task_id = result.id
            session.add(task)
        ok.append(tid)

    await session.commit()
    return {"ok": ok, "failed": failed}


# ── Bulk cancel ──────────────────────────────────────────────
@router.post("/tasks/bulk-cancel")
async def bulk_cancel(body: BulkIdsBody, session: AsyncSession = SessionDep):
    now = datetime.now(timezone.utc)
    ok, failed = [], []

    for tid in body.ids:
        task = await session.get(PublishTask, tid)
        if not task:
            failed.append({"id": tid, "reason": "not_found"})
            continue
        if task.status in ("published", "canceled"):
            failed.append({"id": tid, "reason": f"already_{task.status}"})
            continue

        _revoke_if_queued(task, now, session, "cancel")

        task.cancel_requested_at = now
        task.cancel_reason = body.reason
        if task.status in ("queued", "paused", "ready_for_review", "done", "ready_for_publish", "error"):
            task.status = "canceled"
            task.canceled_at = now
        session.add(task)
        ok.append(tid)

    await session.commit()
    return {"ok": ok, "failed": failed}


# ── Bulk set priority ────────────────────────────────────────
@router.post("/tasks/bulk-set-priority")
async def bulk_set_priority(body: BulkPriorityBody, session: AsyncSession = SessionDep):
    priority = max(-10, min(10, body.priority))
    ok, failed = [], []

    for tid in body.ids:
        task = await session.get(PublishTask, tid)
        if not task:
            failed.append({"id": tid, "reason": "not_found"})
            continue
        task.priority = priority
        session.add(task)
        ok.append(tid)

    await session.commit()
    return {"ok": ok, "failed": failed, "priority": priority}
