"""
SimHash-based near-duplicate detection for candidates.

Uses 64-bit SimHash over word-level shingles and Hamming distance
to find "almost identical" texts (paraphrases, minor edits).

Stored in candidate.meta["content_simhash64"] as 16-char hex string.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dedupe import normalize_text

if TYPE_CHECKING:
    from app.models import Candidate

# Simple Russian/English stop-words (kept minimal for speed)
_STOP_WORDS = frozenset(
    "и в на с по к из за от у о а но что это как не для"
    " the a an and or but in on at to of for with is it".split()
)

DEFAULT_MAX_DISTANCE = 6


def tokenize(text: str) -> list[str]:
    """Normalize and tokenize text into word tokens, removing stop-words."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    tokens = normalized.split()
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _hash64(token: str) -> int:
    """Stable 64-bit hash of a token via MD5 truncation."""
    h = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "little")


def simhash64(tokens: list[str]) -> int:
    """Compute 64-bit SimHash from a list of tokens.

    Uses word bigrams as features for better accuracy.
    """
    if not tokens:
        return 0

    # Build features: unigrams + bigrams
    features: list[str] = list(tokens)
    for i in range(len(tokens) - 1):
        features.append(f"{tokens[i]}_{tokens[i + 1]}")

    v = [0] * 64
    for feat in features:
        h = _hash64(feat)
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    result = 0
    for i in range(64):
        if v[i] > 0:
            result |= (1 << i)
    return result


def hamming(a: int, b: int) -> int:
    """Hamming distance between two 64-bit integers."""
    return bin(a ^ b).count("1")


def compute_text_simhash(text: str) -> int:
    """Compute 64-bit SimHash from raw text."""
    tokens = tokenize(text)
    return simhash64(tokens)


def simhash_to_hex(value: int) -> str:
    """Convert simhash int to 16-char hex string."""
    return f"{value & 0xFFFFFFFFFFFFFFFF:016x}"


def hex_to_simhash(hex_str: str) -> int:
    """Convert 16-char hex string back to int."""
    return int(hex_str, 16)


async def find_near_duplicate(
    session: AsyncSession,
    project_id: int,
    simhash_hex: str,
    *,
    max_distance: int = DEFAULT_MAX_DISTANCE,
    exclude_id: int | None = None,
) -> tuple["Candidate | None", int]:
    """Find a near-duplicate candidate in the project by SimHash Hamming distance.

    MVP: loads all APPROVED/USED candidates with simhash and compares in Python.

    Returns (candidate, distance) or (None, -1).
    """
    from app.models import Candidate

    if not simhash_hex:
        return None, -1

    target_hash = hex_to_simhash(simhash_hex)
    if target_hash == 0:
        return None, -1

    NEAR_DUP_STATUSES = {"APPROVED", "USED"}

    query = (
        select(Candidate.id, Candidate.meta, Candidate.status)
        .where(and_(
            Candidate.project_id == project_id,
            Candidate.status.in_(NEAR_DUP_STATUSES),
            Candidate.meta["content_simhash64"].as_string().isnot(None),
        ))
    )

    if exclude_id is not None:
        query = query.where(Candidate.id != exclude_id)

    result = await session.execute(query)
    rows = result.all()

    best_id: int | None = None
    best_dist = max_distance + 1

    for row_id, row_meta, row_status in rows:
        if not row_meta or "content_simhash64" not in row_meta:
            continue
        row_hex = row_meta["content_simhash64"]
        try:
            row_hash = hex_to_simhash(row_hex)
        except (ValueError, TypeError):
            continue
        dist = hamming(target_hash, row_hash)
        if dist <= max_distance and dist < best_dist:
            best_dist = dist
            best_id = row_id

    if best_id is not None:
        candidate = await session.get(Candidate, best_id)
        return candidate, best_dist

    return None, -1
