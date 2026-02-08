"""
Auto-generate service — creates GENERATE candidates from Briefs
based on content plan settings.

Content plan stored in Project.meta["content_plan"]:
{
  "auto_generate_enabled": true,
  "generate_per_day": 3,
  "cooldown_hours_per_brief": 24,
  "brief_weights": {"12": 1.0, "15": 0.5},
  "min_gap_minutes": 30,
  "default_weight": 1.0
}
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Brief, Candidate, CandidateOrigin, CandidateStatus,
    DecisionLog, Project,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_PLAN: dict[str, Any] = {
    "auto_generate_enabled": False,
    "generate_per_day": 3,
    "cooldown_hours_per_brief": 24,
    "brief_weights": {},
    "min_gap_minutes": 30,
    "default_weight": 1.0,
}


def _get_content_plan(project: Project) -> dict[str, Any]:
    meta = project.meta or {}
    cp = meta.get("content_plan") or {}
    return {**DEFAULT_CONTENT_PLAN, **cp}


def _pick_brief_weighted(
    briefs: list[Brief],
    weights_map: dict[str, float],
    default_weight: float,
) -> Brief:
    """Pick a brief using weighted random selection."""
    weights = []
    for b in briefs:
        w = weights_map.get(str(b.id), default_weight)
        weights.append(max(0.01, w))
    return random.choices(briefs, weights=weights, k=1)[0]


async def _generate_candidate_from_brief(
    session: AsyncSession,
    brief: Brief,
    weight: float,
) -> Candidate:
    """Create a GENERATE candidate from a brief via LLM (same logic as POST /briefs/{id}/generate)."""
    from app.services.llm_provider import get_llm_provider

    llm = get_llm_provider()
    result = await llm.generate(
        title=brief.title,
        topic=brief.topic,
        description=brief.description,
        style=brief.style,
        tone=brief.tone,
        language=brief.language,
        target_platform=brief.target_platform,
        target_duration_sec=brief.target_duration_sec,
        reference_urls=brief.reference_urls if isinstance(brief.reference_urls, list) else None,
        llm_prompt_template=brief.llm_prompt_template,
    )

    meta = result.to_meta()
    meta["brief_weight"] = weight

    # Virtual score based on weight
    virtual_score = min(0.99, 0.50 + 0.10 * weight)

    candidate = Candidate(
        project_id=brief.project_id,
        platform=brief.target_platform or "generated",
        platform_video_id=f"gen_{brief.id}_{uuid.uuid4().hex[:8]}",
        title=result.title_suggestion or brief.title,
        caption=result.captions_draft,
        origin=CandidateOrigin.generate.value,
        brief_id=brief.id,
        meta=meta,
        status=CandidateStatus.new.value,
        virality_score=virtual_score,
        virality_factors={"weight": weight, "base": 0.50, "virtual": True},
    )
    session.add(candidate)
    await session.flush()
    return candidate


async def run_auto_generate(
    session: AsyncSession, project_id: int, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Auto-generate candidates from briefs for a project.

    Args:
        session: DB session
        project_id: project to process
        dry_run: if True, compute report but do NOT write to DB

    Returns report dict with created[], skipped[], etc.
    """
    now = datetime.now(timezone.utc)

    project = await session.get(Project, project_id)
    if not project:
        return {"error": "Project not found", "created": [], "skipped": [], "dry_run": dry_run}

    plan = _get_content_plan(project)
    if not plan.get("auto_generate_enabled", False) and not dry_run:
        return {
            "error": "auto_generate not enabled",
            "created": [], "skipped": [],
            "dry_run": dry_run,
        }

    generate_per_day = plan.get("generate_per_day", 3)
    cooldown_hours = plan.get("cooldown_hours_per_brief", 24)
    weights_map = plan.get("brief_weights", {})
    default_weight = plan.get("default_weight", 1.0)

    # ── Determine timezone for "today" ────────────────────────
    publish_settings = (project.meta or {}).get("publish_settings", {})
    tz_name = publish_settings.get("timezone") or plan.get("timezone") or "UTC"
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    local_now = now.astimezone(tz)
    day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_local.astimezone(timezone.utc)

    # ── Count already generated today ─────────────────────────
    today_count_q = await session.execute(
        select(func.count(Candidate.id)).where(and_(
            Candidate.project_id == project_id,
            Candidate.origin == CandidateOrigin.generate.value,
            Candidate.created_at >= day_start_utc,
        ))
    )
    today_count = today_count_q.scalar() or 0
    remaining = max(0, generate_per_day - today_count)

    if remaining == 0:
        return {
            "project_id": project_id,
            "created": [],
            "skipped": [{"reason": "limit_reached", "today_count": today_count, "limit": generate_per_day}],
            "dry_run": dry_run,
            "run_at": now.isoformat(),
        }

    # ── Get active briefs ─────────────────────────────────────
    briefs_q = await session.execute(
        select(Brief).where(and_(
            Brief.project_id == project_id,
            Brief.status == "active",
        ))
    )
    active_briefs = list(briefs_q.scalars().all())

    if not active_briefs:
        return {
            "project_id": project_id,
            "created": [],
            "skipped": [{"reason": "no_active_briefs"}],
            "dry_run": dry_run,
            "run_at": now.isoformat(),
        }

    # ── Cooldown: briefs used recently ────────────────────────
    cooldown_cutoff = now - timedelta(hours=cooldown_hours)
    recent_brief_ids_q = await session.execute(
        select(Candidate.brief_id).where(and_(
            Candidate.project_id == project_id,
            Candidate.origin == CandidateOrigin.generate.value,
            Candidate.brief_id.isnot(None),
            Candidate.created_at >= cooldown_cutoff,
        )).distinct()
    )
    cooldown_brief_ids = {r[0] for r in recent_brief_ids_q.all()}

    created: list[dict] = []
    skipped: list[dict] = []

    for _ in range(remaining):
        # Filter out cooled-down briefs
        available = [b for b in active_briefs if b.id not in cooldown_brief_ids]

        if not available:
            skipped.append({"reason": "cooldown", "all_briefs_on_cooldown": True})
            break

        # Pick brief by weighted random
        brief = _pick_brief_weighted(available, weights_map, default_weight)
        weight = weights_map.get(str(brief.id), default_weight)

        if dry_run:
            created.append({
                "brief_id": brief.id,
                "brief_title": brief.title,
                "weight": weight,
                "virtual_score": min(0.99, 0.50 + 0.10 * weight),
                "candidate_id": None,
                "dry_run": True,
            })
        else:
            try:
                candidate = await _generate_candidate_from_brief(session, brief, weight)
                created.append({
                    "brief_id": brief.id,
                    "brief_title": brief.title,
                    "weight": weight,
                    "virtual_score": candidate.virality_score,
                    "candidate_id": candidate.id,
                })
            except Exception as e:
                skipped.append({
                    "brief_id": brief.id,
                    "reason": f"generation_error: {e}",
                })

        # Mark brief as on cooldown for this run
        cooldown_brief_ids.add(brief.id)

    report = {
        "project_id": project_id,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
        "today_total": today_count + len([c for c in created if not c.get("dry_run")]),
        "limit": generate_per_day,
        "active_briefs": len(active_briefs),
        "dry_run": dry_run,
        "run_at": now.isoformat(),
    }

    if not dry_run and created:
        session.add(DecisionLog(
            project_id=project_id,
            payload_json={
                "action": "auto_generate",
                "created_count": len(created),
                "created_ids": [c.get("candidate_id") for c in created],
                "skipped": skipped[:20],
                "today_total": report["today_total"],
                "limit": generate_per_day,
            },
        ))
        await session.commit()
    elif dry_run:
        await session.rollback()

    logger.info(
        f"[auto_generate] Project {project_id}: "
        f"{len(created)} created, {len(skipped)} skipped, "
        f"dry_run={dry_run}"
    )
    return report


async def run_auto_generate_all(session: AsyncSession) -> dict:
    """Run auto-generate for all projects with content_plan.auto_generate_enabled=true."""
    projects_q = await session.execute(
        select(Project.id, Project.meta).where(Project.status == "active")
    )

    project_ids = []
    for pid, meta in projects_q.all():
        cp = (meta or {}).get("content_plan", {})
        if cp.get("auto_generate_enabled"):
            project_ids.append(pid)

    if not project_ids:
        logger.info("[auto_generate] No projects with auto_generate_enabled")
        return {"processed": 0, "total_created": 0}

    total_created = 0
    for pid in project_ids:
        try:
            report = await run_auto_generate(session, pid)
            total_created += report.get("created_count", 0)
        except Exception as e:
            logger.error(f"[auto_generate] Project {pid} failed: {e}")

    logger.info(
        f"[auto_generate] Done: {len(project_ids)} projects, "
        f"{total_created} total created"
    )
    return {"processed": len(project_ids), "total_created": total_created}
