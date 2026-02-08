"""
Redis-based distributed semaphore for limiting concurrency of heavy pipeline steps.

Uses a Redis sorted set (ZSET) where:
- key: sem:{name}
- members: unique tokens (UUIDs)
- scores: expiry timestamps (unix epoch)

Expired tokens are cleaned up on every acquire attempt.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

import redis.asyncio as aioredis

from app.settings import get_settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """Get or create a shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


def _sem_key(name: str) -> str:
    return f"sem:{name}"


async def acquire(
    name: str,
    limit: int,
    *,
    ttl_sec: int | None = None,
    wait_timeout_sec: int | None = None,
) -> str:
    """Acquire a semaphore slot.

    Args:
        name: semaphore name (e.g. "whisper", "ffmpeg")
        limit: max concurrent holders
        ttl_sec: token TTL in seconds (auto-expire for crash safety)
        wait_timeout_sec: max seconds to wait for a free slot

    Returns:
        token string (must be passed to release())

    Raises:
        TimeoutError: if wait_timeout_sec exceeded
    """
    settings = get_settings()
    if ttl_sec is None:
        ttl_sec = settings.redis_semaphore_ttl_sec
    if wait_timeout_sec is None:
        wait_timeout_sec = settings.semaphore_wait_timeout_sec

    r = _get_redis()
    key = _sem_key(name)
    token = str(uuid.uuid4())
    deadline = time.monotonic() + wait_timeout_sec
    backoff = 1.0

    while True:
        now_ts = time.time()

        # Cleanup expired tokens
        await r.zremrangebyscore(key, "-inf", now_ts)

        # Check current count
        current = await r.zcard(key)

        if current < limit:
            # Try to add our token with expiry score
            expiry = now_ts + ttl_sec
            added = await r.zadd(key, {token: expiry}, nx=True)
            if added:
                # Double-check we didn't exceed limit (race condition guard)
                new_count = await r.zcard(key)
                if new_count > limit:
                    # We exceeded — remove ourselves and retry
                    await r.zrem(key, token)
                else:
                    logger.info(
                        f"[semaphore] Acquired '{name}' slot (token={token[:8]}…, "
                        f"count={new_count}/{limit})"
                    )
                    return token

        # Check timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Semaphore '{name}': timed out waiting {wait_timeout_sec}s "
                f"for slot (limit={limit}, current={current})"
            )

        # Wait with jittered backoff
        wait = min(backoff, remaining)
        logger.debug(
            f"[semaphore] '{name}' full ({current}/{limit}), "
            f"waiting {wait:.1f}s (remaining={remaining:.0f}s)"
        )
        await asyncio.sleep(wait)
        backoff = min(backoff * 1.5, 5.0)


async def release(name: str, token: str) -> None:
    """Release a semaphore slot.

    Args:
        name: semaphore name
        token: token returned by acquire()
    """
    r = _get_redis()
    key = _sem_key(name)
    removed = await r.zrem(key, token)
    current = await r.zcard(key)
    if removed:
        logger.info(
            f"[semaphore] Released '{name}' slot (token={token[:8]}…, "
            f"remaining={current})"
        )
    else:
        logger.warning(
            f"[semaphore] Release '{name}': token {token[:8]}… not found "
            f"(already expired or released)"
        )
