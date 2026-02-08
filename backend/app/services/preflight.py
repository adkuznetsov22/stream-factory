"""
Preflight checks — validate external dependencies on startup / health.

Results are cached for 60 seconds to avoid hammering dependencies.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
CACHE_TTL = 60  # seconds


async def _check_db() -> dict:
    """SELECT 1 on the database."""
    try:
        from app.db import get_session
        async for session in get_session():
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            return {"check": "db", "ok": True, "detail": "connected"}
    except Exception as e:
        return {"check": "db", "ok": False, "detail": str(e)[:200]}
    return {"check": "db", "ok": False, "detail": "no session"}


async def _check_redis() -> dict:
    """Ping Redis (if celery/redis enabled)."""
    from app.settings import get_settings
    settings = get_settings()
    if not settings.celery_enabled:
        return {"check": "redis", "ok": True, "detail": "skipped (celery disabled)"}
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pong = await r.ping()
        await r.aclose()
        return {"check": "redis", "ok": bool(pong), "detail": "pong" if pong else "no pong"}
    except Exception as e:
        return {"check": "redis", "ok": False, "detail": str(e)[:200]}


async def _check_binary(name: str, args: list[str] | None = None) -> dict:
    """Check if a binary is available via --version or -version."""
    path = shutil.which(name)
    if not path:
        return {"check": name, "ok": False, "detail": "not found in PATH"}
    try:
        cmd = args or [name, "-version"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        first_line = stdout.decode("utf-8", errors="replace").split("\n")[0][:120]
        return {"check": name, "ok": proc.returncode == 0, "detail": first_line or "ok"}
    except asyncio.TimeoutError:
        return {"check": name, "ok": False, "detail": "timeout"}
    except Exception as e:
        return {"check": name, "ok": False, "detail": str(e)[:200]}


async def _check_tokens() -> list[dict]:
    """Check that required API tokens are present."""
    from app.settings import get_settings
    settings = get_settings()
    results = []

    if settings.apify_token:
        results.append({"check": "apify_token", "ok": True, "detail": f"set ({settings.apify_token[:6]}...)"})
    else:
        results.append({"check": "apify_token", "ok": True, "detail": "not set (optional)"})

    if settings.youtube_api_key:
        results.append({"check": "youtube_api_key", "ok": True, "detail": f"set ({settings.youtube_api_key[:6]}...)"})
    else:
        results.append({"check": "youtube_api_key", "ok": True, "detail": "not set (optional)"})

    if settings.vk_access_token:
        results.append({"check": "vk_access_token", "ok": True, "detail": "set"})
    else:
        results.append({"check": "vk_access_token", "ok": True, "detail": "not set (optional)"})

    return results


async def run_preflight() -> dict[str, Any]:
    """Run all preflight checks, return cached result if fresh."""
    global _cache, _cache_ts

    now = time.monotonic()
    if _cache and (now - _cache_ts) < CACHE_TTL:
        return _cache

    checks = []

    # DB
    checks.append(await _check_db())
    # Redis
    checks.append(await _check_redis())
    # FFmpeg
    checks.append(await _check_binary("ffmpeg", ["ffmpeg", "-version"]))
    # ffprobe
    checks.append(await _check_binary("ffprobe", ["ffprobe", "-version"]))
    # Whisper (optional — just check binary presence)
    whisper_path = shutil.which("whisper") or shutil.which("whisper-ctranslate2")
    if whisper_path:
        checks.append({"check": "whisper", "ok": True, "detail": whisper_path})
    else:
        checks.append({"check": "whisper", "ok": True, "detail": "not found (optional)"})

    # Tokens
    checks.extend(await _check_tokens())

    all_ok = all(c["ok"] for c in checks)
    result = {"ok": all_ok, "checks": checks, "cached_at": time.time()}

    _cache = result
    _cache_ts = now

    if not all_ok:
        failed = [c for c in checks if not c["ok"]]
        logger.warning(f"[preflight] FAILED checks: {failed}")
    else:
        logger.info("[preflight] All checks passed")

    return result
