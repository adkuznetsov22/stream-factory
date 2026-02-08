"""
Topic Anti-Repeat Guard — prevents publishing similar topics
back-to-back on the same destination.

Uses topic_tags (top keywords) hashed into a topic_signature (SHA-1).
Stored in candidate.meta["topic_tags"] and candidate.meta["topic_signature"].
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from app.services.dedupe import normalize_text

if TYPE_CHECKING:
    from app.models import Candidate


def extract_topic_tags(candidate: "Candidate") -> list[str]:
    """Extract topic tags from a candidate.

    Priority:
    1. REPURPOSE: meta.script_analysis.theses → first 2-3 words of each
    2. GENERATE: meta.keywords or meta.script_data.keywords
    3. Fallback: title/caption → tokenize → top words
    """
    meta = candidate.meta or {}
    tags: list[str] = []

    # 1. script_analysis theses (from A01 pipeline step)
    script_analysis = meta.get("script_analysis")
    if isinstance(script_analysis, dict):
        theses = script_analysis.get("theses") or script_analysis.get("topics") or []
        if isinstance(theses, list):
            for thesis in theses[:5]:
                if isinstance(thesis, str):
                    words = normalize_text(thesis).split()[:3]
                    if words:
                        tags.append(" ".join(words))
                elif isinstance(thesis, dict):
                    text = thesis.get("text") or thesis.get("title") or ""
                    words = normalize_text(text).split()[:3]
                    if words:
                        tags.append(" ".join(words))

    # 2. keywords (from GENERATE / LLM)
    if not tags:
        keywords = meta.get("keywords")
        if isinstance(keywords, list):
            for kw in keywords[:7]:
                if isinstance(kw, str) and kw.strip():
                    tags.append(normalize_text(kw))

    # 3. script_data keywords
    if not tags:
        script_data = meta.get("script_data")
        if isinstance(script_data, dict):
            kw = script_data.get("keywords")
            if isinstance(kw, list):
                for k in kw[:7]:
                    if isinstance(k, str) and k.strip():
                        tags.append(normalize_text(k))

    # 4. Fallback: title + caption → top words
    if not tags:
        parts = []
        if candidate.title:
            parts.append(candidate.title)
        if candidate.caption and candidate.caption != candidate.title:
            parts.append(candidate.caption)
        text = normalize_text(" ".join(parts))
        if text:
            # Remove short words, take top 5 unique
            words = [w for w in text.split() if len(w) > 2]
            seen: set[str] = set()
            for w in words:
                if w not in seen:
                    seen.add(w)
                    tags.append(w)
                if len(tags) >= 5:
                    break

    # Deduplicate and clean
    clean: list[str] = []
    seen_tags: set[str] = set()
    for t in tags:
        t = t.strip()
        if t and t not in seen_tags:
            seen_tags.add(t)
            clean.append(t)

    return clean[:7]


def topic_signature(tags: list[str]) -> str:
    """Compute SHA-1 signature from sorted topic tags."""
    if not tags:
        return ""
    normalized = sorted(set(t.lower().strip() for t in tags if t.strip()))
    if not normalized:
        return ""
    text = "|".join(normalized)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def ensure_candidate_topic_meta(candidate: "Candidate") -> tuple[list[str], str]:
    """Extract topic tags + signature and store in candidate.meta.

    Returns (tags, signature).
    """
    tags = extract_topic_tags(candidate)
    sig = topic_signature(tags)

    meta = candidate.meta or {}
    meta["topic_tags"] = tags
    meta["topic_signature"] = sig
    candidate.meta = meta

    return tags, sig
