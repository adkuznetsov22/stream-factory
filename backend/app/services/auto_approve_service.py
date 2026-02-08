"""
Auto-approve engine for candidates.

Uses scoring calibration threshold (or manual override) to automatically
approve high-scoring candidates and create PublishTasks, respecting
daily limits per destination, origin filter, and cooldown per source.

Cooldown keys:
- REPURPOSE candidates → candidate.author (fallback: source url)
- GENERATE candidates  → candidate.brief_id
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Candidate, CandidateOrigin, CandidateStatus,
    DecisionLog, Project, ProjectDestination, PublishTask, Brief,
)

logger = logging.getLogger(__name__)

# Defaults when feed_settings keys are missing
DEFAULT_DAILY_LIMIT = 3
DEFAULT_COOLDOWN_HOURS = 12
MAX_CANDIDATES_PER_RUN = 100

VALID_ORIGIN_FILTERS = {"ALL", "REPURPOSE", "GENERATE"}


# Diversity defaults
DEFAULT_MAX_PER_AUTHOR_PER_DAY = 2
DEFAULT_MAX_PER_TOPIC_PER_DAY = 2
DEFAULT_MAX_SAME_TOPIC_IN_SINGLE_RUN = 1


def _get_feed_settings(project: Project) -> dict:
    """Extract feed_settings with defaults."""
    fs = project.feed_settings or {}
    return {
        "auto_approve_enabled": fs.get("auto_approve_enabled", False),
        "daily_limit_per_destination": fs.get("daily_limit_per_destination", DEFAULT_DAILY_LIMIT),
        "cooldown_hours_per_source": fs.get("cooldown_hours_per_source", DEFAULT_COOLDOWN_HOURS),
        "min_score_override": fs.get("min_score_override"),
        "origin_filter": fs.get("origin_filter", "ALL"),
        # Diversity guard
        "diversity_enabled": fs.get("diversity_enabled", True),
        "max_per_author_per_day": fs.get("max_per_author_per_day", DEFAULT_MAX_PER_AUTHOR_PER_DAY),
        "max_per_topic_per_day": fs.get("max_per_topic_per_day", DEFAULT_MAX_PER_TOPIC_PER_DAY),
        "max_same_topic_in_single_run": fs.get("max_same_topic_in_single_run", DEFAULT_MAX_SAME_TOPIC_IN_SINGLE_RUN),
    }


def _get_threshold(project: Project, settings: dict) -> float:
    """Determine the score threshold for auto-approve.

    Priority:
    1. min_score_override from feed_settings (operator override)
    2. auto_approve_threshold from scoring calibration
    3. Fallback 0.70
    """
    override = settings.get("min_score_override")
    if override is not None and isinstance(override, (int, float)):
        return float(override)

    meta = project.meta or {}
    calibration = meta.get("scoring_calibration", {})
    cal_threshold = calibration.get("auto_approve_threshold")
    if cal_threshold is not None:
        return float(cal_threshold)

    return 0.70


def _cooldown_key(candidate: Candidate) -> str | None:
    """Get the cooldown grouping key for a candidate.

    REPURPOSE → author (fallback: url)
    GENERATE  → brief_id
    """
    if candidate.origin == CandidateOrigin.generate.value:
        return f"brief:{candidate.brief_id}" if candidate.brief_id else None
    # REPURPOSE or other
    if candidate.author:
        return f"author:{candidate.author}"
    if candidate.url:
        return f"url:{candidate.url}"
    return None


async def run_auto_approve(
    session: AsyncSession, project_id: int, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Auto-approve candidates for a project based on scoring threshold.

    Args:
        session: DB session
        project_id: project to process
        dry_run: if True, compute report but do NOT write to DB

    Returns report dict with approved[], skipped[], threshold, etc.
    """
    now = datetime.now(timezone.utc)

    # ── Load project with destinations ───────────────────────
    res = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.destinations))
    )
    project = res.scalar_one_or_none()
    if not project:
        return {"error": "Project not found", "approved": [], "skipped": [], "dry_run": dry_run}

    settings = _get_feed_settings(project)
    threshold = _get_threshold(project, settings)
    daily_limit = settings["daily_limit_per_destination"]
    cooldown_hours = settings["cooldown_hours_per_source"]
    origin_filter = settings.get("origin_filter", "ALL")
    if origin_filter not in VALID_ORIGIN_FILTERS:
        origin_filter = "ALL"

    # Diversity settings
    diversity_enabled = settings.get("diversity_enabled", True)
    max_per_author = settings.get("max_per_author_per_day", DEFAULT_MAX_PER_AUTHOR_PER_DAY)
    max_per_topic = settings.get("max_per_topic_per_day", DEFAULT_MAX_PER_TOPIC_PER_DAY)
    max_topic_run = settings.get("max_same_topic_in_single_run", DEFAULT_MAX_SAME_TOPIC_IN_SINGLE_RUN)

    active_dests = [d for d in project.destinations if d.is_active]
    if not active_dests:
        return {
            "error": "No active destinations",
            "approved": [], "skipped": [],
            "threshold": threshold, "dry_run": dry_run,
        }

    # ── Timezone for "today" ───────────────────────────────────
    ps = (project.meta or {}).get("publish_settings", {})
    tz_name = ps.get("timezone") or "UTC"
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    local_now = now.astimezone(tz)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    daily_counts: dict[int, int] = {}
    for dest in active_dests:
        count_q = await session.execute(
            select(func.count(PublishTask.id)).where(and_(
                PublishTask.project_id == project_id,
                PublishTask.destination_social_account_id == dest.social_account_id,
                PublishTask.created_at >= day_start,
            ))
        )
        daily_counts[dest.id] = count_q.scalar() or 0

    # ── Cooldown: recently approved sources ───────────────────
    cooldown_cutoff = now - timedelta(hours=cooldown_hours)

    # Collect recently approved candidates for cooldown key extraction
    recent_approved_q = await session.execute(
        select(Candidate.author, Candidate.url, Candidate.brief_id, Candidate.origin).where(and_(
            Candidate.project_id == project_id,
            Candidate.status.in_([CandidateStatus.approved.value, "used"]),
            Candidate.reviewed_at >= cooldown_cutoff,
        ))
    )
    cooldown_keys: set[str] = set()
    for row in recent_approved_q.all():
        author, url, brief_id, origin = row
        # Build a temporary candidate-like object for key extraction
        if origin == CandidateOrigin.generate.value:
            if brief_id:
                cooldown_keys.add(f"brief:{brief_id}")
        else:
            if author:
                cooldown_keys.add(f"author:{author}")
            elif url:
                cooldown_keys.add(f"url:{url}")

    # ── Diversity: today counts per author and topic ──────────
    author_today: dict[str, int] = {}
    topic_today: dict[str, int] = {}
    topic_run: dict[str, int] = {}  # per-run counter

    if diversity_enabled:
        today_cands_q = await session.execute(
            select(Candidate.author, Candidate.url, Candidate.origin, Candidate.meta).where(and_(
                Candidate.project_id == project_id,
                Candidate.status.in_([CandidateStatus.approved.value, "used"]),
                Candidate.reviewed_at >= day_start,
            ))
        )
        for row in today_cands_q.all():
            c_author, c_url, c_origin, c_meta = row
            # Author key
            if c_origin != CandidateOrigin.generate.value:
                akey = c_author or c_url or ""
                if akey:
                    author_today[akey] = author_today.get(akey, 0) + 1
            # Topic key
            c_meta = c_meta or {}
            tsig = c_meta.get("topic_signature", "")
            if tsig:
                topic_today[tsig] = topic_today.get(tsig, 0) + 1

    # ── Fetch eligible candidates ────────────────────────────
    filters = [
        Candidate.project_id == project_id,
        Candidate.status == CandidateStatus.new.value,
        Candidate.virality_score.isnot(None),
        Candidate.virality_score >= threshold,
        Candidate.linked_publish_task_id.is_(None),
    ]

    # Origin filter
    if origin_filter == "REPURPOSE":
        filters.append(Candidate.origin == CandidateOrigin.repurpose.value)
    elif origin_filter == "GENERATE":
        filters.append(Candidate.origin == CandidateOrigin.generate.value)

    candidates_q = await session.execute(
        select(Candidate)
        .where(and_(*filters))
        .order_by(Candidate.virality_score.desc())
        .limit(MAX_CANDIDATES_PER_RUN)
    )
    candidates_raw = list(candidates_q.scalars().all())

    # ── Smart ordering via selector ───────────────────────────
    from app.services.selector import SelectionState, rank_candidates, top_debug

    # Build state from today's approved candidates
    sel_state = SelectionState()
    if diversity_enabled and (topic_today or author_today):
        # Last approved = the most recent by reviewed_at among today's
        last_approved_q = await session.execute(
            select(Candidate.meta, Candidate.author, Candidate.url, Candidate.origin, Candidate.brief_id)
            .where(and_(
                Candidate.project_id == project_id,
                Candidate.status.in_([CandidateStatus.approved.value, "used"]),
                Candidate.reviewed_at >= day_start,
            ))
            .order_by(Candidate.reviewed_at.desc())
            .limit(1)
        )
        last_row = last_approved_q.first()
        if last_row:
            lmeta, lauthor, lurl, lorigin, lbrief = last_row
            lmeta = lmeta or {}
            sel_state.last_topic_signature = lmeta.get("topic_signature", "")
            if lorigin == CandidateOrigin.generate.value:
                sel_state.last_author_key = f"brief:{lbrief}" if lbrief else ""
            else:
                sel_state.last_author_key = lauthor or lurl or ""
        sel_state.recent_topic_signatures = set(topic_today.keys())
        sel_state.recent_author_keys = set(author_today.keys())

    ranked = rank_candidates(candidates_raw, sel_state)
    candidates = [si.item for si in ranked]
    ranking_debug = top_debug(ranked, 5)

    approved: list[dict] = []
    skipped: list[dict] = []

    for candidate in candidates:
        # ── Exact duplicate check via content_signature ────
        sig = (candidate.meta or {}).get("content_signature")
        if sig:
            from app.services.dedupe import find_duplicate
            dup = await find_duplicate(session, project_id, sig, exclude_candidate_id=candidate.id)
            if dup:
                skipped.append({
                    "candidate_id": candidate.id,
                    "score": candidate.virality_score,
                    "reason": f"duplicate: same content as #{dup.id} (status={dup.status})",
                })
                continue

        # ── Near-duplicate check via SimHash ──────────────
        sh_hex = (candidate.meta or {}).get("content_simhash64")
        if sh_hex:
            from app.services.simhash import find_near_duplicate
            _dedupe = ((project.meta or {}).get("dedupe_settings") or {})
            _max_dist = _dedupe.get("simhash_max_distance", 6)
            near_dup, dist = await find_near_duplicate(
                session, project_id, sh_hex,
                max_distance=_max_dist, exclude_id=candidate.id,
            )
            if near_dup:
                skipped.append({
                    "candidate_id": candidate.id,
                    "score": candidate.virality_score,
                    "reason": f"near_duplicate: #{near_dup.id} d={dist}",
                })
                continue

        # ── Check cooldown ───────────────────────────────
        ck = _cooldown_key(candidate)
        if ck and ck in cooldown_keys:
            skipped.append({
                "candidate_id": candidate.id,
                "score": candidate.virality_score,
                "reason": f"cooldown: '{ck}' approved within {cooldown_hours}h",
            })
            continue

        # ── Diversity guard ──────────────────────────────
        if diversity_enabled:
            # Author cap
            if candidate.origin != CandidateOrigin.generate.value:
                akey = candidate.author or candidate.url or ""
                if akey and author_today.get(akey, 0) >= max_per_author:
                    skipped.append({
                        "candidate_id": candidate.id,
                        "score": candidate.virality_score,
                        "reason": f"author_cap: '{akey}' {author_today[akey]}/{max_per_author}",
                        "author_key": akey,
                    })
                    continue

            # Topic cap (daily)
            from app.services.topic_guard import ensure_candidate_topic_meta
            _, tsig = ensure_candidate_topic_meta(candidate)
            if tsig and topic_today.get(tsig, 0) >= max_per_topic:
                skipped.append({
                    "candidate_id": candidate.id,
                    "score": candidate.virality_score,
                    "reason": f"topic_cap: sig={tsig[:12]}… {topic_today[tsig]}/{max_per_topic}",
                    "topic_signature": tsig,
                })
                continue

            # Topic cap (per-run)
            if tsig and topic_run.get(tsig, 0) >= max_topic_run:
                skipped.append({
                    "candidate_id": candidate.id,
                    "score": candidate.virality_score,
                    "reason": f"topic_run_cap: sig={tsig[:12]}… {topic_run[tsig]}/{max_topic_run}",
                    "topic_signature": tsig,
                })
                continue

        # ── Find best destination with remaining budget ──
        best_dest = None
        for dest in active_dests:
            if daily_counts.get(dest.id, 0) < daily_limit:
                best_dest = dest
                break

        if not best_dest:
            skipped.append({
                "candidate_id": candidate.id,
                "score": candidate.virality_score,
                "reason": "daily_limit: all destinations exhausted",
            })
            continue

        if dry_run:
            # Dry run: just record what WOULD happen
            approved.append({
                "candidate_id": candidate.id,
                "task_id": None,
                "destination_id": best_dest.id,
                "destination_platform": best_dest.platform,
                "score": candidate.virality_score,
                "title": candidate.title,
                "dry_run": True,
            })
            daily_counts[best_dest.id] = daily_counts.get(best_dest.id, 0) + 1
            if ck:
                cooldown_keys.add(ck)
            # Update diversity counters for dry_run too
            if diversity_enabled:
                if candidate.origin != CandidateOrigin.generate.value:
                    akey = candidate.author or candidate.url or ""
                    if akey:
                        author_today[akey] = author_today.get(akey, 0) + 1
                _tsig = (candidate.meta or {}).get("topic_signature", "")
                if _tsig:
                    topic_today[_tsig] = topic_today.get(_tsig, 0) + 1
                    topic_run[_tsig] = topic_run.get(_tsig, 0) + 1
            continue

        # ── Create PublishTask (same flow as manual approve) ─
        is_generate = candidate.origin == CandidateOrigin.generate.value
        task_meta = None
        if is_generate and candidate.brief_id:
            brief = await session.get(Brief, candidate.brief_id)
            if brief:
                task_meta = {
                    "origin": "GENERATE",
                    "candidate_meta": candidate.meta or {},
                    "brief": {
                        "id": brief.id,
                        "title": brief.title,
                        "topic": brief.topic,
                        "style": brief.style,
                        "tone": brief.tone,
                        "language": brief.language,
                        "target_duration_sec": brief.target_duration_sec,
                        "target_platform": brief.target_platform,
                        "llm_prompt_template": brief.llm_prompt_template,
                    },
                }

        task = PublishTask(
            project_id=project_id,
            platform=best_dest.platform,
            destination_social_account_id=best_dest.social_account_id,
            external_id=candidate.platform_video_id,
            permalink=candidate.url if not is_generate else None,
            preview_url=candidate.thumbnail_url,
            download_url=candidate.url if not is_generate else None,
            caption_text=candidate.caption or candidate.title,
            status="queued",
            preset_id=project.preset_id,
            total_steps=0,
            artifacts=task_meta,
        )
        session.add(task)
        await session.flush()

        # Link candidate
        candidate.status = CandidateStatus.approved.value
        candidate.linked_publish_task_id = task.id
        candidate.reviewed_at = now
        session.add(candidate)

        # Update counters
        daily_counts[best_dest.id] = daily_counts.get(best_dest.id, 0) + 1
        if ck:
            cooldown_keys.add(ck)
        # Update diversity counters
        if diversity_enabled:
            if candidate.origin != CandidateOrigin.generate.value:
                akey = candidate.author or candidate.url or ""
                if akey:
                    author_today[akey] = author_today.get(akey, 0) + 1
            _tsig = (candidate.meta or {}).get("topic_signature", "")
            if _tsig:
                topic_today[_tsig] = topic_today.get(_tsig, 0) + 1
                topic_run[_tsig] = topic_run.get(_tsig, 0) + 1

        approved.append({
            "candidate_id": candidate.id,
            "task_id": task.id,
            "destination_id": best_dest.id,
            "destination_platform": best_dest.platform,
            "score": candidate.virality_score,
            "title": candidate.title,
        })

    # ── Build skipped_reasons_breakdown ────────────────────────
    reasons_breakdown: dict[str, int] = {}
    for s in skipped:
        reason_key = s["reason"].split(":")[0]  # e.g. "author_cap", "topic_cap", etc.
        reasons_breakdown[reason_key] = reasons_breakdown.get(reason_key, 0) + 1

    report = {
        "project_id": project_id,
        "threshold": round(threshold, 4),
        "approved_count": len(approved),
        "skipped_count": len(skipped),
        "approved": approved,
        "skipped": skipped,
        "skipped_reasons_breakdown": reasons_breakdown,
        "ordered_by": "effective_score",
        "ranking_debug": ranking_debug,
        "daily_limits": {
            dest.id: {"platform": dest.platform, "used": daily_counts.get(dest.id, 0), "limit": daily_limit}
            for dest in active_dests
        },
        "settings": settings,
        "run_at": now.isoformat(),
        "dry_run": dry_run,
    }

    if not dry_run:
        # Log decision
        session.add(DecisionLog(
            project_id=project_id,
            payload_json={
                "action": "auto_approve",
                "threshold": round(threshold, 4),
                "approved_count": len(approved),
                "skipped_count": len(skipped),
                "approved_ids": [a["candidate_id"] for a in approved],
                "skipped_reasons": {s["candidate_id"]: s["reason"] for s in skipped[:20]},
                "daily_limits": report["daily_limits"],
            },
        ))
        await session.commit()
    else:
        # Dry run — rollback any accidental flushes (shouldn't be any)
        await session.rollback()

    logger.info(
        f"[auto_approve] Project {project_id}: "
        f"{len(approved)} approved, {len(skipped)} skipped, "
        f"threshold={threshold:.2f}, dry_run={dry_run}"
    )
    return report


async def run_auto_approve_all(session: AsyncSession) -> dict:
    """Run auto-approve for all projects with auto_approve_enabled=true."""
    projects_q = await session.execute(
        select(Project.id).where(
            Project.feed_settings["auto_approve_enabled"].as_boolean() == True  # noqa: E712
        )
    )
    project_ids = [r[0] for r in projects_q.all()]

    if not project_ids:
        logger.info("[auto_approve] No projects with auto_approve_enabled")
        return {"processed": 0, "total_approved": 0}

    total_approved = 0
    for pid in project_ids:
        try:
            report = await run_auto_approve(session, pid)
            total_approved += report.get("approved_count", 0)
        except Exception as e:
            logger.error(f"[auto_approve] Project {pid} failed: {e}")

    logger.info(
        f"[auto_approve] Done: {len(project_ids)} projects, "
        f"{total_approved} total approved"
    )
    return {"processed": len(project_ids), "total_approved": total_approved}
