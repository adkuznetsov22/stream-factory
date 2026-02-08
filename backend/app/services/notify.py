"""
Notification service — Telegram alerts with throttle.

Env:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Throttle: same (title) not sent more than once per 15 minutes.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_throttle: dict[str, float] = {}
THROTTLE_SEC = 15 * 60  # 15 minutes


def _should_send(key: str) -> bool:
    now = time.monotonic()
    last = _throttle.get(key, 0.0)
    if now - last < THROTTLE_SEC:
        return False
    _throttle[key] = now
    return True


def _get_config() -> tuple[str | None, str | None]:
    from app.settings import get_settings
    s = get_settings()
    return s.telegram_bot_token, s.telegram_chat_id


async def _send_telegram(text: str) -> bool:
    token, chat_id = _get_config()
    if not token or not chat_id:
        logger.debug("[notify] Telegram not configured, skipping")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={
                "chat_id": chat_id,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if r.status_code == 200:
                return True
            logger.warning(f"[notify] Telegram API {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[notify] Telegram send failed: {e}")
    return False


async def notify_error(title: str, payload: Any = None) -> bool:
    """Send error-level alert (throttled by title)."""
    if not _should_send(f"error:{title}"):
        logger.debug(f"[notify] throttled error: {title}")
        return False
    body = f"🔴 <b>{title}</b>"
    if payload:
        body += f"\n<pre>{str(payload)[:500]}</pre>"
    return await _send_telegram(body)


async def notify_warn(title: str, payload: Any = None) -> bool:
    """Send warning-level alert (throttled by title)."""
    if not _should_send(f"warn:{title}"):
        logger.debug(f"[notify] throttled warn: {title}")
        return False
    body = f"🟡 <b>{title}</b>"
    if payload:
        body += f"\n<pre>{str(payload)[:500]}</pre>"
    return await _send_telegram(body)


async def notify_info(title: str, payload: Any = None) -> bool:
    """Send info-level notification (throttled by title)."""
    if not _should_send(f"info:{title}"):
        return False
    body = f"🟢 <b>{title}</b>"
    if payload:
        body += f"\n<pre>{str(payload)[:500]}</pre>"
    return await _send_telegram(body)
