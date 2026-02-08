"""
DuplicateGuard — content-based deduplication for candidates.

Uses SHA-1 of normalized text (title + caption or transcript) as a
content_signature stored in candidate.meta["content_signature"].
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models import Candidate


def normalize_text(text: str) -> str:
    """Normalize text for deduplication.

    - NFKC unicode normalization
    - lowercase
    - collapse whitespace
    - strip punctuation (keep letters, digits, spaces)
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    # Remove punctuation, keep letters/digits/spaces
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_signature(text: str) -> str:
    """Compute SHA-1 hex signature of normalized text."""
    normalized = normalize_text(text)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def extract_candidate_text(
    candidate: "Candidate",
    *,
    transcript: str | None = None,
) -> tuple[str, str]:
    """Extract text and source label for signature computation.

    Priority:
    1. transcript (from Whisper / T08_SPEECH_TO_TEXT)
    2. title + caption
    3. title alone

    Returns (text, source) where source is "transcript", "title+caption", or "title".
    """
    if transcript and transcript.strip():
        return transcript.strip(), "transcript"

    parts = []
    if candidate.title:
        parts.append(candidate.title)
    if candidate.caption and candidate.caption != candidate.title:
        parts.append(candidate.caption)

    text = " ".join(parts).strip()
    source = "title+caption" if len(parts) > 1 else "title"
    return text, source


def compute_candidate_signature(
    candidate: "Candidate",
    *,
    transcript: str | None = None,
) -> tuple[str, str]:
    """Compute content signature for a candidate.

    Returns (signature, source).
    """
    text, source = extract_candidate_text(candidate, transcript=transcript)
    sig = compute_signature(text)
    return sig, source


async def find_duplicate(
    session: AsyncSession,
    project_id: int,
    content_signature: str,
    *,
    exclude_candidate_id: int | None = None,
) -> "Candidate | None":
    """Find a candidate in the project with the same content_signature
    that has already been approved/used/published.

    Returns the duplicate Candidate or None.
    """
    from app.models import Candidate

    if not content_signature:
        return None

    # We search in meta->>'content_signature' for the matching value
    # among candidates with relevant statuses
    DUPLICATE_STATUSES = {"APPROVED", "USED"}

    query = (
        select(Candidate)
        .where(and_(
            Candidate.project_id == project_id,
            Candidate.status.in_(DUPLICATE_STATUSES),
            Candidate.meta["content_signature"].as_string() == content_signature,
        ))
        .limit(1)
    )

    if exclude_candidate_id is not None:
        query = query.where(Candidate.id != exclude_candidate_id)

    result = await session.execute(query)
    return result.scalar_one_or_none()
