"""
Daily Publish Plan — compute optimal slot→task assignments per destination.

Uses publish_settings (windows, min_gap, daily_limit), selector ranking,
and topic_guard to produce a greedy plan.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Candidate, DecisionLog, Project, PublishTask

logger = logging.getLogger(__name__)

DAY_ABBREV = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_PUBLISH_SETTINGS: dict[str, Any] = {
    "timezone": "UTC",
    "windows": {d: [["00:00", "23:59"]] for d in DAY_ABBREV},
    "min_gap_minutes_per_destination": 90,
    "daily_limit_per_destination": 3,
}

ELIGIBLE_STATUSES = {"ready_for_publish"}


def _get_publish_settings(project: Project) -> dict[str, Any]:
    meta = project.meta or {}
    ps = meta.get("publish_settings") or {}
    return {**DEFAULT_PUBLISH_SETTINGS, **ps}


def _compute_slots(
    day_windows: list[list[str]],
    min_gap_minutes: int,
    daily_limit: int,
    already_published_today: int,
    tz_info: Any,
    target_date: Any,
) -> list[datetime]:
    """Generate available time slots for a day within windows respecting min_gap."""
    remaining = daily_limit - already_published_today
    if remaining <= 0:
        return []

    slots: list[datetime] = []
    for window in day_windows:
        if len(window) != 2:
            continue
        try:
            start_h, start_m = map(int, window[0].split(":"))
            end_h, end_m = map(int, window[1].split(":"))
        except (ValueError, AttributeError):
            continue

        start_dt = datetime(
            target_date.year, target_date.month, target_date.day,
            start_h, start_m, tzinfo=tz_info,
        )
        end_dt = datetime(
            target_date.year, target_date.month, target_date.day,
            end_h, end_m, tzinfo=tz_info,
        )
        gap = timedelta(minutes=max(min_gap_minutes, 1))

        current = start_dt
        while current <= end_dt and len(slots) < remaining:
            slots.append(current)
            current += gap

    return slots[:remaining]


async def compute_plan(
    session: AsyncSession,
    project_id: int,
    *,
    date_str: str | None = None,
    destination_id: int | None = None,
    max_items: int = 20,
) -> dict[str, Any]:
    """Compute daily publish plan (pure read, no mutations)."""
    import zoneinfo

    project_q = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.destinations))
    )
    project = project_q.scalar_one_or_none()
    if not project:
        return {"error": "project_not_found"}

    ps = _get_publish_settings(project)
    tz_name = ps.get("timezone") or "UTC"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
        tz_name = "UTC"

    now_utc = datetime.now(timezone.utc)
    local_now = now_utc.astimezone(tz)

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = local_now.date()
    else:
        target_date = local_now.date()

    day_key = DAY_ABBREV[target_date.weekday()]
    windows = ps.get("windows", {})
    day_windows = windows.get(day_key, [])
    min_gap = ps.get("min_gap_minutes_per_destination", 90)
    daily_limit = ps.get("daily_limit_per_destination", 3)

    # Topic guard settings
    tg_enabled = ps.get("topic_guard_enabled", True)
    tg_last_n = ps.get("topic_guard_last_n", 5)
    tg_cooldown_hours = ps.get("topic_guard_cooldown_hours", 12)

    active_dests = [d for d in project.destinations if d.is_active]
    if destination_id:
        active_dests = [d for d in active_dests if d.id == destination_id]

    # Day boundaries in UTC
    day_start_local = datetime(target_date.year, target_date.month, target_date.day, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)

    # Fetch eligible tasks
    eligible_q = await session.execute(
        select(PublishTask).where(and_(
            PublishTask.project_id == project_id,
            PublishTask.status.in_(ELIGIBLE_STATUSES),
        )).order_by(PublishTask.priority.desc(), PublishTask.created_at.asc()).limit(max_items * 3)
    )
    all_eligible = list(eligible_q.scalars().all())

    # Load candidate data for scoring / topic guard
    task_ids = [t.id for t in all_eligible]
    score_map: dict[int, float] = {}
    candidate_map: dict[int, Candidate] = {}
    if task_ids:
        cand_q = await session.execute(
            select(Candidate).where(Candidate.linked_publish_task_id.in_(task_ids))
        )
        for cand in cand_q.scalars().all():
            if cand.linked_publish_task_id:
                candidate_map[cand.linked_publish_task_id] = cand
                if cand.virality_score is not None:
                    score_map[cand.linked_publish_task_id] = cand.virality_score

    from app.services.selector import SelectionState, rank_tasks
    from app.services.topic_guard import ensure_candidate_topic_meta

    dest_results = []

    for dest in active_dests:
        dest_acct_id = dest.social_account_id

        # Count already published today for this dest
        pub_count_q = await session.execute(
            select(func.count(PublishTask.id)).where(and_(
                PublishTask.project_id == project_id,
                PublishTask.destination_social_account_id == dest_acct_id,
                PublishTask.status == "published",
                PublishTask.published_at >= day_start_utc,
                PublishTask.published_at < day_end_utc,
            ))
        )
        already_published = pub_count_q.scalar() or 0

        # Compute slots
        slots = _compute_slots(day_windows, min_gap, daily_limit, already_published, tz, target_date)

        # Build SelectionState from recent history
        state = SelectionState()
        tg_cutoff = now_utc - timedelta(hours=tg_cooldown_hours) if tg_enabled else now_utc
        banned_sigs: set[str] = set()

        recent_q = await session.execute(
            select(PublishTask.id).where(and_(
                PublishTask.project_id == project_id,
                PublishTask.destination_social_account_id == dest_acct_id,
                PublishTask.status == "published",
                PublishTask.published_at >= tg_cutoff,
            )).order_by(PublishTask.published_at.desc()).limit(tg_last_n)
        )
        recent_ids = [r[0] for r in recent_q.all()]
        if recent_ids:
            hist_q = await session.execute(
                select(Candidate.meta, Candidate.author, Candidate.url,
                       Candidate.origin, Candidate.brief_id,
                       Candidate.linked_publish_task_id)
                .where(Candidate.linked_publish_task_id.in_(recent_ids))
            )
            first = True
            for cmeta, cauthor, curl, corigin, cbrief, ctask_id in hist_q.all():
                cmeta = cmeta or {}
                ts = cmeta.get("topic_signature", "")
                if ts:
                    banned_sigs.add(ts)
                    state.recent_topic_signatures.add(ts)
                ak = f"brief:{cbrief}" if corigin == "GENERATE" and cbrief else (cauthor or curl or "")
                if ak:
                    state.recent_author_keys.add(ak)
                if first and ctask_id == recent_ids[0]:
                    state.last_topic_signature = ts
                    state.last_author_key = ak
                    first = False

        # Filter tasks for this destination
        dest_tasks = [t for t in all_eligible if t.destination_social_account_id == dest_acct_id]

        # Pre-filter: has video
        valid_tasks = []
        skipped_items = []
        for t in dest_tasks:
            artifacts = t.artifacts or {}
            video_path = artifacts.get("final_video_path") or artifacts.get("ready_video_path")
            if not video_path:
                skipped_items.append({"task_id": t.id, "reason": "no_video"})
                continue
            if t.published_url or t.published_external_id:
                skipped_items.append({"task_id": t.id, "reason": "already_published"})
                continue
            valid_tasks.append(t)

        # Rank
        ranked = rank_tasks(valid_tasks, score_map, candidate_map, state)

        # Greedy slot assignment
        assigned_slots = []
        used_task_ids: set[int] = set()
        local_banned = set(banned_sigs)

        for slot_time in slots:
            best = None
            for si in ranked:
                task = si.item
                if task.id in used_task_ids:
                    continue

                # Topic guard hard-block
                cand = candidate_map.get(task.id)
                if cand and tg_enabled:
                    _, tsig = ensure_candidate_topic_meta(cand)
                    if tsig and tsig in local_banned:
                        if task.id not in {s["task_id"] for s in skipped_items}:
                            skipped_items.append({"task_id": task.id, "reason": "topic_repeat"})
                        continue

                best = si
                break

            if best:
                task = best.item
                cand = candidate_map.get(task.id)
                cand_id = cand.id if cand else None

                # Update local state for next slot
                if cand:
                    _, tsig = ensure_candidate_topic_meta(cand)
                    if tsig:
                        local_banned.add(tsig)

                assigned_slots.append({
                    "at": slot_time.isoformat(),
                    "task_id": task.id,
                    "candidate_id": cand_id,
                    "score": round(best.base_score, 4),
                    "effective_score": round(best.effective_score, 4),
                    "priority": task.priority,
                    "reason": "ranked",
                })
                used_task_ids.add(task.id)

        dest_results.append({
            "destination_id": dest.id,
            "social_account_id": dest_acct_id,
            "platform": dest.platform,
            "already_published_today": already_published,
            "daily_limit": daily_limit,
            "total_slots": len(slots),
            "slots": assigned_slots,
            "skipped": skipped_items,
        })

    return {
        "project_id": project_id,
        "timezone": tz_name,
        "date": str(target_date),
        "day": day_key,
        "windows": day_windows,
        "min_gap_minutes": min_gap,
        "destinations": dest_results,
    }


async def apply_plan(
    session: AsyncSession,
    project_id: int,
    *,
    date_str: str | None = None,
    base_priority: int = 10,
    enqueue: bool = False,
) -> dict[str, Any]:
    """Compute plan and apply priorities (+ optional enqueue)."""
    plan = await compute_plan(session, project_id, date_str=date_str)
    if "error" in plan:
        return plan

    ok_list = []
    failed_list = []

    for dest_info in plan.get("destinations", []):
        for idx, slot in enumerate(dest_info.get("slots", [])):
            task_id = slot["task_id"]
            priority = max(-10, min(10, base_priority - idx))

            task = await session.get(PublishTask, task_id)
            if not task:
                failed_list.append({"task_id": task_id, "reason": "not_found"})
                continue

            task.priority = priority
            session.add(task)

            entry = {"task_id": task_id, "priority": priority}

            if enqueue and task.status in ("queued", "ready_for_review", "done"):
                try:
                    from app.settings import get_settings
                    settings = get_settings()
                    if settings.celery_enabled:
                        from app.worker.tasks import process_task as celery_process_task
                        # Set queued + clear control flags
                        task.status = "queued"
                        task.pause_requested_at = None
                        task.paused_at = None
                        task.pause_reason = None
                        task.cancel_requested_at = None
                        task.canceled_at = None
                        task.cancel_reason = None
                        session.add(task)
                        await session.flush()
                        result = celery_process_task.apply_async(args=[task_id], queue="pipeline")
                        task.celery_task_id = result.id
                        session.add(task)
                        entry["enqueued"] = True
                        entry["celery_task_id"] = result.id
                except Exception as e:
                    logger.warning(f"[apply_plan] Failed to enqueue task {task_id}: {e}")
                    entry["enqueue_error"] = str(e)

            ok_list.append(entry)

        for skip in dest_info.get("skipped", []):
            failed_list.append(skip)

    # DecisionLog
    session.add(DecisionLog(
        action="daily_publish_plan_apply",
        payload_json={
            "project_id": project_id,
            "date": plan.get("date"),
            "base_priority": base_priority,
            "enqueue": enqueue,
            "ok_count": len(ok_list),
            "failed_count": len(failed_list),
            "task_ids": [e["task_id"] for e in ok_list],
        },
    ))

    await session.commit()

    return {
        "ok": ok_list,
        "failed": failed_list,
        "plan_summary": {
            "date": plan.get("date"),
            "timezone": plan.get("timezone"),
            "destinations": len(plan.get("destinations", [])),
        },
    }
