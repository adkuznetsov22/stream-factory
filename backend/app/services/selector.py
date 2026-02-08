"""
Smart candidate/task selector — reorders items to minimize skips
by penalizing repeated topics and authors.

Used by auto_approve_service and auto_publish_service to pick the
"best next" candidate/task that maximizes diversity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ── Penalty constants (fixed, predictable) ─────────────────
PENALTY_TOPIC_LAST = 0.15      # same topic as the very last published
PENALTY_AUTHOR_LAST = 0.10     # same author as the very last published
PENALTY_TOPIC_RECENT = 0.05    # topic appeared in recent N
PENALTY_AUTHOR_RECENT = 0.03   # author appeared in recent N


@dataclass
class SelectionState:
    """Per-destination state for smart ordering."""
    last_topic_signature: str = ""
    last_author_key: str = ""
    recent_topic_signatures: set[str] = field(default_factory=set)
    recent_author_keys: set[str] = field(default_factory=set)


@runtime_checkable
class Scoreable(Protocol):
    """Anything with a base score, topic_signature, and author_key."""
    @property
    def base_score(self) -> float: ...
    @property
    def topic_signature(self) -> str: ...
    @property
    def author_key(self) -> str: ...
    @property
    def created_at_ts(self) -> float: ...


@dataclass
class ScoredItem:
    """Wrapper that holds an item + its effective score and penalties."""
    item: Any
    base_score: float
    effective_score: float
    penalties: dict[str, float] = field(default_factory=dict)

    @property
    def sort_key(self) -> tuple:
        return (-self.effective_score, -self.base_score, self.item_created_at)

    @property
    def item_created_at(self) -> float:
        if hasattr(self.item, "created_at_ts"):
            return self.item.created_at_ts
        return 0.0


def compute_effective_score(
    base_score: float,
    topic_sig: str,
    author_key: str,
    state: SelectionState,
) -> tuple[float, dict[str, float]]:
    """Compute effective_score with penalties.

    Returns (effective_score, penalties_dict).
    """
    penalties: dict[str, float] = {}
    total_penalty = 0.0

    # Penalty: same topic as last published
    if topic_sig and topic_sig == state.last_topic_signature:
        penalties["topic_last"] = PENALTY_TOPIC_LAST
        total_penalty += PENALTY_TOPIC_LAST
    # Penalty: topic in recent set (but not last — already penalized)
    elif topic_sig and topic_sig in state.recent_topic_signatures:
        penalties["topic_recent"] = PENALTY_TOPIC_RECENT
        total_penalty += PENALTY_TOPIC_RECENT

    # Penalty: same author as last published
    if author_key and author_key == state.last_author_key:
        penalties["author_last"] = PENALTY_AUTHOR_LAST
        total_penalty += PENALTY_AUTHOR_LAST
    # Penalty: author in recent set (but not last)
    elif author_key and author_key in state.recent_author_keys:
        penalties["author_recent"] = PENALTY_AUTHOR_RECENT
        total_penalty += PENALTY_AUTHOR_RECENT

    effective = max(0.0, base_score - total_penalty)
    return effective, penalties


def rank_items(
    items: list[dict[str, Any]],
    state: SelectionState,
) -> list[ScoredItem]:
    """Rank a list of item dicts by effective score.

    Each item dict must have keys:
    - "base_score": float
    - "topic_signature": str
    - "author_key": str
    - "item": the original object

    Returns sorted list of ScoredItem (best first).
    """
    scored: list[ScoredItem] = []
    for entry in items:
        base = entry.get("base_score", 0.0) or 0.0
        tsig = entry.get("topic_signature", "") or ""
        akey = entry.get("author_key", "") or ""
        effective, penalties = compute_effective_score(base, tsig, akey, state)
        scored.append(ScoredItem(
            item=entry.get("item"),
            base_score=base,
            effective_score=effective,
            penalties=penalties,
        ))

    scored.sort(key=lambda s: (-s.effective_score, -s.base_score))
    return scored


def rank_candidates(candidates: list, state: SelectionState) -> list[ScoredItem]:
    """Rank ORM Candidate objects by effective score.

    Extracts topic_signature and author_key from candidate.meta and fields.
    """
    items = []
    for c in candidates:
        meta = c.meta or {}
        tsig = meta.get("topic_signature", "")
        # Author key: for REPURPOSE use author/url, for GENERATE use brief_id
        if hasattr(c, "origin") and c.origin == "GENERATE":
            akey = f"brief:{c.brief_id}" if c.brief_id else ""
        else:
            akey = c.author or c.url or ""
        items.append({
            "item": c,
            "base_score": c.virality_score or 0.0,
            "topic_signature": tsig,
            "author_key": akey,
        })
    return rank_items(items, state)


def rank_tasks(
    tasks: list,
    score_map: dict[int, float],
    candidate_map: dict[int, Any],
    state: SelectionState,
) -> list[ScoredItem]:
    """Rank ORM PublishTask objects by effective score.

    Args:
        tasks: list of PublishTask
        score_map: task_id -> virality_score
        candidate_map: task_id -> Candidate (for topic/author extraction)
        state: SelectionState for the destination
    """
    items = []
    for t in tasks:
        base = score_map.get(t.id, 0.0) or 0.0
        cand = candidate_map.get(t.id)
        tsig = ""
        akey = ""
        if cand:
            meta = cand.meta or {} if hasattr(cand, "meta") else {}
            tsig = meta.get("topic_signature", "")
            if hasattr(cand, "origin") and cand.origin == "GENERATE":
                akey = f"brief:{cand.brief_id}" if cand.brief_id else ""
            else:
                akey = cand.author or cand.url or ""
        items.append({
            "item": t,
            "base_score": base,
            "topic_signature": tsig,
            "author_key": akey,
        })
    return rank_items(items, state)


def top_debug(scored: list[ScoredItem], n: int = 5) -> list[dict]:
    """Return top-N items with penalties for debug/report."""
    result = []
    for si in scored[:n]:
        item = si.item
        item_id = getattr(item, "id", None)
        result.append({
            "id": item_id,
            "base_score": round(si.base_score, 4),
            "effective_score": round(si.effective_score, 4),
            "penalties": {k: round(v, 4) for k, v in si.penalties.items()},
        })
    return result
