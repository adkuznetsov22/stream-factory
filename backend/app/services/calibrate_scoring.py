"""
Scoring calibration service.

Runs daily: computes correlation between virality_score and actual
views_per_hour, determines auto-approve threshold, and identifies
which virality factors actually correlate with real performance.

Stores calibration result in Project.meta["scoring_calibration"].
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, Project, PublishTask, PublishedVideoMetrics

logger = logging.getLogger(__name__)

# Minimum data points needed for a meaningful calibration
MIN_DATA_POINTS = 5

# Default threshold when not enough data
DEFAULT_THRESHOLD = 0.70


async def calibrate_project_scoring(
    session: AsyncSession, project_id: int
) -> dict[str, Any]:
    """Compute scoring calibration for a single project.

    Returns dict with:
    - correlation: Pearson r between virality_score and views_per_hour
    - auto_approve_threshold: recommended score cutoff
    - factor_correlations: which factors correlate with performance
    - data_points: number of samples used
    - buckets: breakdown by age_bucket
    """
    now = datetime.now(timezone.utc)

    # ── Gather data: candidates with both score and published metrics ──
    latest_snap = (
        select(
            PublishedVideoMetrics.task_id,
            PublishedVideoMetrics.views,
            PublishedVideoMetrics.likes,
            PublishedVideoMetrics.comments,
            PublishedVideoMetrics.shares,
            PublishedVideoMetrics.hours_since_publish,
        )
        .distinct(PublishedVideoMetrics.task_id)
        .order_by(
            PublishedVideoMetrics.task_id,
            PublishedVideoMetrics.snapshot_at.desc(),
        )
        .subquery()
    )

    query = (
        select(
            Candidate.id,
            Candidate.virality_score,
            Candidate.virality_factors,
            Candidate.views.label("candidate_views"),
            Candidate.likes.label("candidate_likes"),
            Candidate.comments.label("candidate_comments"),
            Candidate.shares.label("candidate_shares"),
            Candidate.subscribers.label("candidate_subscribers"),
            Candidate.published_at.label("candidate_published_at"),
            Candidate.platform,
            latest_snap.c.views.label("actual_views"),
            latest_snap.c.likes.label("actual_likes"),
            latest_snap.c.comments.label("actual_comments"),
            latest_snap.c.shares.label("actual_shares"),
            latest_snap.c.hours_since_publish,
        )
        .join(PublishTask, Candidate.linked_publish_task_id == PublishTask.id)
        .join(latest_snap, latest_snap.c.task_id == PublishTask.id)
        .where(
            Candidate.project_id == project_id,
            Candidate.virality_score.isnot(None),
            PublishTask.status == "published",
            latest_snap.c.hours_since_publish > 0,
        )
    )

    result = await session.execute(query)
    rows = result.all()

    if len(rows) < MIN_DATA_POINTS:
        logger.info(
            f"[calibrate] Project {project_id}: only {len(rows)} data points "
            f"(need {MIN_DATA_POINTS}), using defaults"
        )
        return {
            "project_id": project_id,
            "correlation": None,
            "auto_approve_threshold": DEFAULT_THRESHOLD,
            "factor_correlations": {},
            "data_points": len(rows),
            "sufficient_data": False,
            "calibrated_at": now.isoformat(),
        }

    # ── Build data arrays ────────────────────────────────────
    scores = []
    vph_values = []       # views per hour (actual performance)
    platforms = []
    hours_list = []
    factor_arrays: dict[str, list[float]] = {}

    for row in rows:
        score = row.virality_score
        hours = row.hours_since_publish or 1
        actual_views = row.actual_views or 0
        vph = actual_views / max(hours, 1)

        scores.append(score)
        vph_values.append(vph)
        platforms.append(row.platform)
        hours_list.append(hours)

        # Extract individual factors from virality_factors JSON
        factors = row.virality_factors or {}
        for key, val in factors.items():
            if isinstance(val, (int, float)):
                factor_arrays.setdefault(key, []).append(float(val))
            else:
                # Ensure array stays aligned — pad with 0 for non-numeric
                factor_arrays.setdefault(key, []).append(0.0)

    # ── 1. Overall correlation ───────────────────────────────
    corr = _pearson(scores, vph_values)

    # ── 2. Auto-approve threshold ────────────────────────────
    threshold = _compute_threshold(scores, vph_values)

    # ── 3. Factor correlations ───────────────────────────────
    factor_corr = {}
    for factor_name, factor_vals in factor_arrays.items():
        if len(factor_vals) == len(vph_values) and len(factor_vals) >= MIN_DATA_POINTS:
            r = _pearson(factor_vals, vph_values)
            if r is not None:
                factor_corr[factor_name] = round(r, 4)

    # Sort factors by absolute correlation (strongest first)
    factor_corr = dict(
        sorted(factor_corr.items(), key=lambda x: abs(x[1]), reverse=True)
    )

    # ── 4. Per-platform breakdown ────────────────────────────
    platform_stats = {}
    unique_platforms = set(platforms)
    for plat in unique_platforms:
        idx = [i for i, p in enumerate(platforms) if p == plat]
        if len(idx) >= 3:
            p_scores = [scores[i] for i in idx]
            p_vph = [vph_values[i] for i in idx]
            platform_stats[plat] = {
                "correlation": _safe_round(_pearson(p_scores, p_vph)),
                "threshold": _safe_round(_compute_threshold(p_scores, p_vph)),
                "count": len(idx),
                "avg_score": _safe_round(_mean(p_scores)),
                "avg_vph": _safe_round(_mean(p_vph)),
            }

    # ── 5. Per-age-bucket breakdown ──────────────────────────
    bucket_stats = {}
    for bname, bmin, bmax in [("0-6h", 0, 6), ("6-24h", 6, 24), ("1-3d", 24, 72), ("3-7d", 72, 168), ("7d+", 168, 999999)]:
        idx = [i for i, h in enumerate(hours_list) if bmin < h <= bmax]
        if len(idx) >= 3:
            b_scores = [scores[i] for i in idx]
            b_vph = [vph_values[i] for i in idx]
            bucket_stats[bname] = {
                "correlation": _safe_round(_pearson(b_scores, b_vph)),
                "count": len(idx),
                "avg_score": _safe_round(_mean(b_scores)),
                "avg_vph": _safe_round(_mean(b_vph)),
            }

    calibration = {
        "project_id": project_id,
        "correlation": _safe_round(corr),
        "auto_approve_threshold": _safe_round(threshold),
        "factor_correlations": factor_corr,
        "top_factors": [k for k, v in list(factor_corr.items())[:5] if v > 0.1],
        "weak_factors": [k for k, v in factor_corr.items() if abs(v) < 0.05],
        "platforms": platform_stats,
        "buckets": bucket_stats,
        "data_points": len(rows),
        "sufficient_data": True,
        "calibrated_at": now.isoformat(),
    }

    # ── Persist to project.meta ──────────────────────────────
    project = await session.get(Project, project_id)
    if project:
        meta = project.meta or {}
        meta["scoring_calibration"] = calibration
        project.meta = meta
        session.add(project)
        await session.commit()
        logger.info(
            f"[calibrate] Project {project_id}: r={corr:.3f}, "
            f"threshold={threshold:.2f}, {len(rows)} points, "
            f"top_factors={calibration['top_factors']}"
        )

    return calibration


async def calibrate_all_projects(session: AsyncSession) -> dict:
    """Run calibration for all projects that have published candidates."""
    result = await session.execute(
        select(Candidate.project_id)
        .where(Candidate.linked_publish_task_id.isnot(None))
        .distinct()
    )
    project_ids = [r[0] for r in result.all()]

    calibrated = 0
    skipped = 0
    for pid in project_ids:
        try:
            cal = await calibrate_project_scoring(session, pid)
            if cal.get("sufficient_data"):
                calibrated += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"[calibrate] Project {pid} failed: {e}")
            skipped += 1

    logger.info(f"[calibrate] Done: {calibrated} calibrated, {skipped} skipped")
    return {"calibrated": calibrated, "skipped": skipped, "total": len(project_ids)}


# ── Math helpers (no numpy dependency) ───────────────────────

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient. Returns None if undefined."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    mx = _mean(xs)
    my = _mean(ys)

    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))

    if sx == 0 or sy == 0:
        return None

    return cov / (sx * sy)


def _compute_threshold(scores: list[float], vph_values: list[float]) -> float:
    """Find optimal score threshold that separates good/bad performers.

    Strategy: find the score where median views_per_hour above the threshold
    is at least 2x the median below. If not possible, use top-30% percentile.
    """
    if not scores:
        return DEFAULT_THRESHOLD

    # Sort by score
    pairs = sorted(zip(scores, vph_values), key=lambda x: x[0])

    best_threshold = DEFAULT_THRESHOLD
    best_ratio = 0.0

    # Try each score as a threshold
    unique_scores = sorted(set(scores))
    for candidate_threshold in unique_scores:
        above = [v for s, v in pairs if s >= candidate_threshold]
        below = [v for s, v in pairs if s < candidate_threshold]

        if len(above) < 2 or len(below) < 1:
            continue

        med_above = _median(above)
        med_below = _median(below) or 0.001

        ratio = med_above / med_below
        # Prefer thresholds that keep at least 20% of candidates above
        above_pct = len(above) / len(pairs)
        if above_pct < 0.15:
            continue

        if ratio > best_ratio:
            best_ratio = ratio
            best_threshold = candidate_threshold

    # Fallback: 70th percentile of scores
    if best_ratio < 1.5:
        best_threshold = _percentile(scores, 70)

    return round(best_threshold, 2)


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _percentile(xs: list[float], pct: int) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]


def _safe_round(val: float | None, digits: int = 4) -> float | None:
    if val is None:
        return None
    return round(val, digits)
