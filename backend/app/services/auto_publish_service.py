"""
Auto-publish service — publishes ready tasks within time windows,
respecting daily limits, min-gap spacing, and jitter.

publish_settings stored in Project.meta["publish_settings"]:
{
  "publish_enabled": true,
  "timezone": "Europe/Berlin",
  "windows": {
    "mon": [["10:00","22:00"]],
    "tue": [["10:00","22:00"]],
    ...
  },
  "min_gap_minutes_per_destination": 90,
  "daily_limit_per_destination": 3,
  "jitter_minutes": 10
}
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Candidate, DecisionLog, Project, PublishTask, StepResult,
)

logger = logging.getLogger(__name__)

# Task statuses eligible for auto-publish (must be explicitly marked ready)
PUBLISH_ELIGIBLE_STATUSES = {"ready_for_publish"}

DAY_ABBREV = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_PUBLISH_SETTINGS: dict[str, Any] = {
    "publish_enabled": False,
    "timezone": "UTC",
    "windows": {d: [["00:00", "23:59"]] for d in DAY_ABBREV},
    "min_gap_minutes_per_destination": 90,
    "daily_limit_per_destination": 3,
    "jitter_minutes": 0,
}


def _get_publish_settings(project: Project) -> dict[str, Any]:
    meta = project.meta or {}
    ps = meta.get("publish_settings") or {}
    merged = {**DEFAULT_PUBLISH_SETTINGS, **ps}
    return merged


def _is_in_window(settings: dict, now_utc: datetime) -> bool:
    """Check if current time falls within any publish window for today."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(settings.get("timezone") or "UTC")
    except Exception:
        tz = timezone.utc

    local_now = now_utc.astimezone(tz)
    day_key = DAY_ABBREV[local_now.weekday()]
    windows = settings.get("windows", {})
    day_windows = windows.get(day_key, [])

    if not day_windows:
        return False

    current_time_str = local_now.strftime("%H:%M")

    for window in day_windows:
        if len(window) != 2:
            continue
        start_str, end_str = window[0], window[1]
        if start_str <= current_time_str <= end_str:
            return True

    return False


def _daily_count_key(dest_id: int, day_str: str) -> str:
    return f"{dest_id}:{day_str}"


async def run_auto_publish(
    session: AsyncSession, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Publish ready tasks within time windows.

    Args:
        session: DB session
        dry_run: if True, compute report but do NOT publish

    Returns report dict with started[], skipped[], window info.
    """
    now = datetime.now(timezone.utc)

    # ── Load projects with publish_enabled ────────────────────
    projects_q = await session.execute(
        select(Project)
        .where(Project.status == "active")
        .options(selectinload(Project.destinations))
    )
    projects = projects_q.scalars().all()

    started: list[dict] = []
    skipped: list[dict] = []

    for project in projects:
        ps = _get_publish_settings(project)
        if not ps.get("publish_enabled", False):
            continue

        # ── Window check ──────────────────────────────────────
        if not _is_in_window(ps, now):
            # All tasks for this project skipped
            # (we'll count them below if there are eligible tasks)
            eligible_q = await session.execute(
                select(func.count(PublishTask.id)).where(and_(
                    PublishTask.project_id == project.id,
                    PublishTask.status.in_(PUBLISH_ELIGIBLE_STATUSES),
                ))
            )
            eligible_count = eligible_q.scalar() or 0
            if eligible_count > 0:
                skipped.append({
                    "project_id": project.id,
                    "task_id": None,
                    "reason": "not_in_window",
                    "count": eligible_count,
                })
            continue

        # ── Per-destination limits ────────────────────────────
        daily_limit = ps.get("daily_limit_per_destination", 3)
        min_gap_minutes = ps.get("min_gap_minutes_per_destination", 90)
        jitter_minutes = ps.get("jitter_minutes", 0)

        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(ps.get("timezone") or "UTC")
        except Exception:
            tz = timezone.utc

        local_now = now.astimezone(tz)
        day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_local.astimezone(timezone.utc)

        active_dests = [d for d in project.destinations if d.is_active]

        # ── Topic guard settings ──────────────────────────────
        tg_enabled = ps.get("topic_guard_enabled", True)
        tg_last_n = ps.get("topic_guard_last_n", 5)
        tg_cooldown_hours = ps.get("topic_guard_cooldown_hours", 12)

        # Build banned topic_signature sets + SelectionState per destination
        from app.services.selector import SelectionState, rank_tasks, top_debug

        banned_topic_sigs: dict[int, set[str]] = {}
        dest_states: dict[int, SelectionState] = {}
        tg_cutoff = now - timedelta(hours=tg_cooldown_hours) if tg_enabled else now

        for dest in active_dests:
            dest_id = dest.social_account_id
            state = SelectionState()

            # Recent published tasks for this destination (ordered newest first)
            recent_q = await session.execute(
                select(PublishTask.id).where(and_(
                    PublishTask.project_id == project.id,
                    PublishTask.destination_social_account_id == dest_id,
                    PublishTask.status == "published",
                    PublishTask.published_at >= tg_cutoff,
                )).order_by(PublishTask.published_at.desc()).limit(tg_last_n)
            )
            recent_task_ids = [r[0] for r in recent_q.all()]
            sigs: set[str] = set()
            recent_authors: set[str] = set()
            if recent_task_ids:
                cand_hist_q = await session.execute(
                    select(Candidate.meta, Candidate.author, Candidate.url, Candidate.origin, Candidate.brief_id,
                           Candidate.linked_publish_task_id).where(
                        Candidate.linked_publish_task_id.in_(recent_task_ids),
                    )
                )
                first = True
                for cmeta, cauthor, curl, corigin, cbrief, ctask_id in cand_hist_q.all():
                    cmeta = cmeta or {}
                    ts = cmeta.get("topic_signature", "")
                    if ts:
                        sigs.add(ts)
                    # Author key
                    if corigin == "GENERATE":
                        ak = f"brief:{cbrief}" if cbrief else ""
                    else:
                        ak = cauthor or curl or ""
                    if ak:
                        recent_authors.add(ak)
                    # First row = most recent (last published)
                    if first and ctask_id == recent_task_ids[0]:
                        state.last_topic_signature = ts
                        state.last_author_key = ak
                        first = False

            banned_topic_sigs[dest_id] = sigs
            state.recent_topic_signatures = sigs
            state.recent_author_keys = recent_authors
            dest_states[dest_id] = state

        # Count published today per destination
        daily_counts: dict[int, int] = {}
        last_published: dict[int, datetime | None] = {}
        for dest in active_dests:
            count_q = await session.execute(
                select(func.count(PublishTask.id)).where(and_(
                    PublishTask.project_id == project.id,
                    PublishTask.destination_social_account_id == dest.social_account_id,
                    PublishTask.status == "published",
                    PublishTask.published_at >= day_start_utc,
                ))
            )
            daily_counts[dest.social_account_id] = count_q.scalar() or 0

            last_q = await session.execute(
                select(PublishTask.published_at).where(and_(
                    PublishTask.project_id == project.id,
                    PublishTask.destination_social_account_id == dest.social_account_id,
                    PublishTask.status == "published",
                    PublishTask.published_at.isnot(None),
                )).order_by(PublishTask.published_at.desc()).limit(1)
            )
            last_row = last_q.scalar_one_or_none()
            last_published[dest.social_account_id] = last_row

        # ── Fetch eligible tasks ──────────────────────────────
        eligible_q = await session.execute(
            select(PublishTask).where(and_(
                PublishTask.project_id == project.id,
                PublishTask.status.in_(PUBLISH_ELIGIBLE_STATUSES),
            )).order_by(PublishTask.created_at.asc()).limit(20)
        )
        eligible_tasks = list(eligible_q.scalars().all())

        # Enrich with virality score + candidate data for selector
        task_ids = [t.id for t in eligible_tasks]
        score_map: dict[int, float] = {}
        candidate_map: dict[int, Candidate] = {}
        if task_ids:
            cand_q = await session.execute(
                select(Candidate)
                .where(
                    Candidate.linked_publish_task_id.in_(task_ids),
                )
            )
            for cand in cand_q.scalars().all():
                if cand.linked_publish_task_id:
                    candidate_map[cand.linked_publish_task_id] = cand
                    if cand.virality_score is not None:
                        score_map[cand.linked_publish_task_id] = cand.virality_score

        # Smart ordering via selector — group by destination
        # Use first active dest's state as default (tasks are per-dest anyway)
        default_dest_id = active_dests[0].social_account_id if active_dests else 0
        # Pre-filter tasks that have video and are not already published
        valid_tasks = []
        for t in eligible_tasks:
            artifacts = t.artifacts or {}
            video_path = artifacts.get("final_video_path") or artifacts.get("ready_video_path")
            if not video_path:
                skipped.append({"project_id": project.id, "task_id": t.id, "reason": "no_video"})
                continue
            if t.published_url or t.published_external_id:
                skipped.append({"project_id": project.id, "task_id": t.id, "reason": "already_published"})
                continue
            valid_tasks.append(t)

        # Rank valid tasks using selector per destination
        dest_id_for_ranking = valid_tasks[0].destination_social_account_id if valid_tasks else default_dest_id
        sel_state = dest_states.get(dest_id_for_ranking, SelectionState())
        ranked = rank_tasks(valid_tasks, score_map, candidate_map, sel_state)
        eligible_tasks = [si.item for si in ranked]

        # Debug: top-5 effective scores
        ranking_debug = top_debug(ranked, 5)

        for task in eligible_tasks:
            dest_id = task.destination_social_account_id

            # Daily limit
            if daily_counts.get(dest_id, 0) >= daily_limit:
                skipped.append({
                    "project_id": project.id,
                    "task_id": task.id,
                    "reason": f"daily_limit: {daily_counts.get(dest_id, 0)}/{daily_limit}",
                })
                continue

            # Min gap
            last_at = last_published.get(dest_id)
            if last_at and min_gap_minutes > 0:
                gap = (now - last_at).total_seconds() / 60
                if gap < min_gap_minutes:
                    skipped.append({
                        "project_id": project.id,
                        "task_id": task.id,
                        "reason": f"min_gap: {gap:.0f}m < {min_gap_minutes}m",
                    })
                    continue

            # Topic anti-repeat guard
            if tg_enabled and dest_id in banned_topic_sigs:
                # Get candidate's topic_signature
                cand_for_task = task.candidate if hasattr(task, "candidate") and task.candidate else None
                if not cand_for_task:
                    cand_q2 = await session.execute(
                        select(Candidate).where(Candidate.linked_publish_task_id == task.id).limit(1)
                    )
                    cand_for_task = cand_q2.scalar_one_or_none()
                if cand_for_task:
                    from app.services.topic_guard import ensure_candidate_topic_meta
                    _, task_topic_sig = ensure_candidate_topic_meta(cand_for_task)
                    if task_topic_sig and task_topic_sig in banned_topic_sigs[dest_id]:
                        skipped.append({
                            "project_id": project.id,
                            "task_id": task.id,
                            "reason": f"topic_repeat: sig={task_topic_sig[:12]}…",
                        })
                        continue

            if dry_run:
                started.append({
                    "project_id": project.id,
                    "task_id": task.id,
                    "destination_account_id": dest_id,
                    "score": score_map.get(task.id),
                    "dry_run": True,
                })
                daily_counts[dest_id] = daily_counts.get(dest_id, 0) + 1
                last_published[dest_id] = now
                continue

            # ── Jitter ────────────────────────────────────────
            if jitter_minutes > 0:
                jitter_sec = random.randint(0, jitter_minutes * 60)
                logger.info(f"[auto_publish] Jitter: waiting {jitter_sec}s before publishing task {task.id}")
                await asyncio.sleep(jitter_sec)

            # ── Run P01_PUBLISH via PipelineExecutor ──────────
            publish_result = await _run_publish_step(session, task)

            started.append({
                "project_id": project.id,
                "task_id": task.id,
                "destination_account_id": dest_id,
                "score": score_map.get(task.id),
                "success": publish_result.get("success", False),
                "published_url": publish_result.get("published_url"),
                "error": publish_result.get("error"),
            })

            # Update counters
            daily_counts[dest_id] = daily_counts.get(dest_id, 0) + 1
            last_published[dest_id] = now

    report = {
        "started_count": len(started),
        "skipped_count": len(skipped),
        "started": started,
        "skipped": skipped,
        "ordered_by": "effective_score",
        "dry_run": dry_run,
        "run_at": now.isoformat(),
    }

    if not dry_run and started:
        # Log decision
        project_ids = list({s["project_id"] for s in started})
        for pid in project_ids:
            session.add(DecisionLog(
                project_id=pid,
                payload_json={
                    "action": "auto_publish",
                    "started": [s for s in started if s["project_id"] == pid],
                    "skipped": [s for s in skipped if s.get("project_id") == pid],
                },
            ))
        await session.commit()

    logger.info(
        f"[auto_publish] Started {len(started)}, skipped {len(skipped)}, "
        f"dry_run={dry_run}"
    )
    return report


async def _run_publish_step(session: AsyncSession, task: PublishTask) -> dict:
    """Run P01_PUBLISH for a single task via PipelineExecutor.

    Same approach as retry-publish endpoint.
    """
    from app.services.pipeline_executor import StepContext, PipelineExecutor
    from app.models import ExportProfile

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    task_dir = data_dir / "tasks" / str(task.id)
    task_dir.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []

    def log_cb(msg: str):
        log_lines.append(msg)
        logger.info(f"[auto_publish][task={task.id}] {msg}")

    ctx = StepContext(task_id=task.id, task_dir=task_dir, log_cb=log_cb)
    ctx.session = session
    ctx.publish_task = task
    ctx.platform = task.platform
    ctx.destination_account_id = task.destination_social_account_id
    ctx.caption_text = task.caption_text or task.instructions

    # Set current_video
    for name in ("final.mp4", "ready.mp4", "output.mp4"):
        p = task_dir / name
        if p.exists():
            ctx.set_output_video(p)
            break

    # Populate GENERATE context
    if task.artifacts and isinstance(task.artifacts, dict) and task.artifacts.get("origin") == "GENERATE":
        ctx.candidate_meta = task.artifacts.get("candidate_meta", {})
        ctx.brief_data = task.artifacts.get("brief", {})

    # Load project for policy/export_profile
    project = await session.scalar(select(Project).where(Project.id == task.project_id))
    if project and project.policy and isinstance(project.policy, dict):
        ctx.policy = project.policy
    if project and project.export_profile_id:
        ep = await session.get(ExportProfile, project.export_profile_id)
        if ep:
            ctx.export_profile = {
                "name": ep.name, "target_platform": ep.target_platform,
                "max_duration_sec": ep.max_duration_sec,
                "width": ep.width, "height": ep.height, "fps": ep.fps,
                "codec": ep.codec, "video_bitrate": ep.video_bitrate,
                "audio_bitrate": ep.audio_bitrate,
            }

    # Execute
    executor = PipelineExecutor(ctx)
    step_def = {
        "id": "auto_publish",
        "tool_id": "P01_PUBLISH",
        "name": "Publish (auto)",
        "enabled": True,
        "params": {},
    }

    pipeline_result = await executor.execute_steps([step_def])

    # Persist StepResult
    now = datetime.now(timezone.utc)
    max_idx_q = await session.execute(
        select(func.max(StepResult.step_index)).where(StepResult.task_id == task.id)
    )
    max_idx = max_idx_q.scalar() or 0

    step_output = {}
    step_error = None
    step_status = "completed"
    duration_ms = None

    if pipeline_result.get("steps"):
        s = pipeline_result["steps"][0]
        step_output = s.get("outputs", {})
        step_error = s.get("error")
        step_status = "completed" if s.get("status") == "ok" else "error"
        duration_ms = s.get("duration_ms")
    elif pipeline_result.get("error"):
        step_error = pipeline_result["error"]
        step_status = "error"

    sr = StepResult(
        task_id=task.id,
        step_index=max_idx + 1,
        tool_id="P01_PUBLISH",
        step_name="Publish (auto)",
        status=step_status,
        started_at=now,
        completed_at=datetime.now(timezone.utc),
        duration_ms=duration_ms,
        output_data=step_output,
        error_message=step_error,
        logs="\n".join(log_lines) if log_lines else None,
        moderation_status="auto",
        can_retry=True,
        retry_count=0,
        version=1,
    )
    session.add(sr)

    # Update dag_debug
    existing_debug = task.dag_debug or {}
    existing_steps = existing_debug.get("steps", [])
    existing_steps.extend(executor.get_debug_info().get("steps", []))
    task.dag_debug = {"steps": existing_steps}
    session.add(task)
    await session.commit()
    await session.refresh(task)

    return {
        "success": pipeline_result.get("success", False),
        "published_url": task.published_url,
        "published_external_id": task.published_external_id,
        "error": step_error,
        "step_result_id": sr.id,
    }
