"""
Unified publishing layer for destination platforms.

Each platform adapter implements the `PublisherAdapter` interface:
    publish(task, account, file_path, title, description, tags) -> PublishResult

Results (including errors) are always returned explicitly — no silent failures.
"""
from __future__ import annotations

import abc
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.models import PublishTask, SocialAccount
from app.settings import get_settings

logger = logging.getLogger(__name__)


# ── Result dataclass ─────────────────────────────────────────

# Ошибки, которые считаются retryable (сетевые, rate-limit, временные)
RETRYABLE_INDICATORS = (
    "timeout", "timed out", "429", "too many requests",
    "502", "503", "504", "connection", "reset by peer",
    "temporary", "service unavailable", "rate limit",
    "network", "ssl", "eof", "broken pipe",
)


def _is_retryable_error(error: str | None) -> bool:
    """Determine if an error message indicates a retryable failure."""
    if not error:
        return False
    lower = error.lower()
    return any(ind in lower for ind in RETRYABLE_INDICATORS)


# ── Credential sanitization ──────────────────────────────────

# Patterns that match tokens/secrets in error strings and URLs
_SENSITIVE_PATTERNS = [
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE), "Bearer ***"),
    # access_token in URLs/params
    (re.compile(r"access_token=[A-Za-z0-9\-_\.%]+", re.IGNORECASE), "access_token=***"),
    # refresh_token in URLs/params
    (re.compile(r"refresh_token=[A-Za-z0-9\-_\.%]+", re.IGNORECASE), "refresh_token=***"),
    # session_id / sessionid values
    (re.compile(r"session[_]?[iI]d[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_\.%]+", re.IGNORECASE), "session_id=***"),
    # client_secret
    (re.compile(r"client_secret=[A-Za-z0-9\-_\.%]+", re.IGNORECASE), "client_secret=***"),
    # Generic long hex/base64 tokens (40+ chars)
    (re.compile(r"[A-Za-z0-9\-_]{40,}"), "***TOKEN***"),
]


def _sanitize(text: str | None) -> str | None:
    """Strip credentials and tokens from error messages / response text."""
    if not text:
        return text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _sanitize_dict(d: dict | None) -> dict | None:
    """Remove sensitive keys from a response dict before persisting."""
    if not d:
        return d
    SENSITIVE_KEYS = {
        "access_token", "refresh_token", "client_secret",
        "session_id", "sessionid", "sessionId", "ds_user_id",
        "cookie", "cookies", "authorization",
    }
    cleaned = {}
    for k, v in d.items():
        if k.lower() in {s.lower() for s in SENSITIVE_KEYS}:
            cleaned[k] = "***"
        elif isinstance(v, dict):
            cleaned[k] = _sanitize_dict(v)
        elif isinstance(v, str) and len(v) > 60:
            # Possibly a token — truncate
            cleaned[k] = v[:8] + "***"
        else:
            cleaned[k] = v
    return cleaned


@dataclass
class PublishResult:
    """Unified result of a publish attempt."""
    success: bool
    external_id: str | None = None
    url: str | None = None
    platform: str | None = None
    error: str | None = None
    retryable: bool = False
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "external_id": self.external_id,
            "url": self.url,
            "platform": self.platform,
            "error": self.error,
            "retryable": self.retryable,
        }


# ── Abstract adapter ─────────────────────────────────────────

class PublisherAdapter(abc.ABC):
    """Base class for platform-specific publishers."""

    platform: str = "unknown"

    @abc.abstractmethod
    async def publish(
        self,
        task: PublishTask,
        account: SocialAccount,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> PublishResult:
        """Upload video and return result with external_id + url."""
        ...

    def _log(self, task_id: int, msg: str):
        logger.info(f"[{self.platform}][task={task_id}] {msg}")

    def _error(self, task_id: int, msg: str):
        logger.error(f"[{self.platform}][task={task_id}] {msg}")


# ── YouTube Shorts ────────────────────────────────────────────

class YouTubePublisher(PublisherAdapter):
    """Upload via YouTube Data API v3 resumable upload.

    Requires:
    - account.credentials_json with OAuth2 tokens (access_token, refresh_token, client_id, client_secret)
    - Scope: https://www.googleapis.com/auth/youtube.upload
    """

    platform = "YouTube"

    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    async def publish(
        self,
        task: PublishTask,
        account: SocialAccount,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> PublishResult:
        creds = (account.credentials_json or {}) if hasattr(account, "credentials_json") else {}
        access_token = creds.get("access_token")
        refresh_token = creds.get("refresh_token")
        client_id = creds.get("client_id") or os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = creds.get("client_secret") or os.getenv("YOUTUBE_CLIENT_SECRET")

        if not access_token and not refresh_token:
            msg = "YouTube OAuth2 credentials missing (access_token / refresh_token)"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        # Refresh token if needed
        if refresh_token and client_id and client_secret:
            try:
                access_token = await self._refresh_access_token(
                    refresh_token, client_id, client_secret
                )
            except Exception as exc:
                msg = _sanitize(f"Token refresh failed: {exc}")
                self._error(task.id, msg)
                return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(str(exc)))

        if not access_token:
            msg = "No valid access_token after refresh attempt"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        try:
            self._log(task.id, f"Uploading {file_path.name} ({file_path.stat().st_size} bytes)")

            metadata = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": (tags or [])[:30],
                    "categoryId": "22",  # People & Blogs
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    "madeForKids": False,
                },
            }

            import json
            async with httpx.AsyncClient(timeout=300) as client:
                # Step 1: initiate resumable upload
                init_resp = await client.post(
                    self.UPLOAD_URL,
                    params={
                        "uploadType": "resumable",
                        "part": "snippet,status",
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": "video/mp4",
                        "X-Upload-Content-Length": str(file_path.stat().st_size),
                    },
                    content=json.dumps(metadata),
                )
                if init_resp.status_code not in (200, 308):
                    msg = _sanitize(f"YouTube init upload failed: {init_resp.status_code} — {init_resp.text[:500]}")
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))

                upload_url = init_resp.headers.get("location")
                if not upload_url:
                    msg = "YouTube did not return upload URL"
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

                # Step 2: upload file
                with open(file_path, "rb") as f:
                    upload_resp = await client.put(
                        upload_url,
                        headers={"Content-Type": "video/mp4"},
                        content=f.read(),
                    )

                if upload_resp.status_code not in (200, 201):
                    msg = _sanitize(f"YouTube upload failed: {upload_resp.status_code} — {upload_resp.text[:500]}")
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))

                data = upload_resp.json()
                video_id = data.get("id")
                url = f"https://youtube.com/shorts/{video_id}" if video_id else None

                self._log(task.id, f"Published: {url}")
                return PublishResult(
                    success=True,
                    external_id=video_id,
                    url=url,
                    platform=self.platform,
                    raw_response=_sanitize_dict(data),
                )

        except Exception as exc:
            msg = _sanitize(f"YouTube publish error: {exc}")
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))

    async def _refresh_access_token(
        self, refresh_token: str, client_id: str, client_secret: str
    ) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(_sanitize(f"Token refresh HTTP {resp.status_code}: {resp.text[:300]}"))
            return resp.json()["access_token"]


# ── TikTok (via Apify) ───────────────────────────────────────

class TikTokPublisher(PublisherAdapter):
    """Upload via Apify TikTok upload actor.

    Uses apify_client to run an actor that posts to TikTok.
    account.credentials_json should contain session cookies or tokens.
    """

    platform = "TikTok"
    APIFY_ACTOR = os.getenv("TIKTOK_UPLOAD_ACTOR", "adenium/tiktok-upload")

    async def publish(
        self,
        task: PublishTask,
        account: SocialAccount,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> PublishResult:
        settings = get_settings()
        if not settings.apify_token:
            msg = "APIFY_TOKEN not configured — cannot publish to TikTok"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        creds = (account.credentials_json or {}) if hasattr(account, "credentials_json") else {}
        session_id = creds.get("session_id") or creds.get("sessionid")
        if not session_id:
            msg = "TikTok session_id missing in account credentials"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        try:
            from app.integrations.apify_client import run_actor_and_get_dataset_items

            hashtags = " ".join(f"#{t}" for t in (tags or []))
            caption = f"{description} {hashtags}".strip()[:2200]

            self._log(task.id, f"Uploading via Apify actor {self.APIFY_ACTOR}")

            items, meta = await run_actor_and_get_dataset_items(
                self.APIFY_ACTOR,
                {
                    "sessionId": session_id,
                    "videoPath": str(file_path),
                    "caption": caption,
                    "title": title[:150],
                },
                timeout_s=180,
            )

            if items and isinstance(items, list) and items[0].get("videoId"):
                item = items[0]
                video_id = item["videoId"]
                handle = creds.get("handle") or account.handle or ""
                url = f"https://www.tiktok.com/@{handle}/video/{video_id}" if handle else None

                self._log(task.id, f"Published: {url}")
                return PublishResult(
                    success=True,
                    external_id=video_id,
                    url=url,
                    platform=self.platform,
                    raw_response=_sanitize_dict({"items": items, "meta": meta}),
                )

            msg = _sanitize(f"Apify run completed but no videoId in response: {items[:1] if items else 'empty'}")
            self._error(task.id, msg)
            return PublishResult(
                success=False,
                platform=self.platform,
                error=msg,
                retryable=True,
                raw_response=_sanitize_dict({"items": items, "meta": meta}),
            )

        except Exception as exc:
            msg = _sanitize(f"TikTok publish error: {exc}")
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))


# ── Instagram Reels (via Apify) ──────────────────────────────

class InstagramPublisher(PublisherAdapter):
    """Upload via Apify Instagram Reels upload actor.

    account.credentials_json should contain session cookies.
    """

    platform = "Instagram"
    APIFY_ACTOR = os.getenv("INSTAGRAM_UPLOAD_ACTOR", "adenium/instagram-reel-upload")

    async def publish(
        self,
        task: PublishTask,
        account: SocialAccount,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> PublishResult:
        settings = get_settings()
        if not settings.apify_token:
            msg = "APIFY_TOKEN not configured — cannot publish to Instagram"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        creds = (account.credentials_json or {}) if hasattr(account, "credentials_json") else {}
        session_id = creds.get("session_id") or creds.get("sessionid") or creds.get("ds_user_id")
        if not session_id:
            msg = "Instagram session credentials missing in account"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        try:
            from app.integrations.apify_client import run_actor_and_get_dataset_items

            hashtags = " ".join(f"#{t}" for t in (tags or []))
            caption = f"{description} {hashtags}".strip()[:2200]

            self._log(task.id, f"Uploading via Apify actor {self.APIFY_ACTOR}")

            items, meta = await run_actor_and_get_dataset_items(
                self.APIFY_ACTOR,
                {
                    "sessionId": session_id,
                    "videoPath": str(file_path),
                    "caption": caption,
                },
                timeout_s=180,
            )

            if items and isinstance(items, list) and items[0].get("mediaId"):
                item = items[0]
                media_id = item["mediaId"]
                shortcode = item.get("shortcode") or item.get("code")
                url = f"https://www.instagram.com/reel/{shortcode}/" if shortcode else None

                self._log(task.id, f"Published: {url}")
                return PublishResult(
                    success=True,
                    external_id=media_id,
                    url=url,
                    platform=self.platform,
                    raw_response=_sanitize_dict({"items": items, "meta": meta}),
                )

            msg = _sanitize(f"Apify run completed but no mediaId in response: {items[:1] if items else 'empty'}")
            self._error(task.id, msg)
            return PublishResult(
                success=False,
                platform=self.platform,
                error=msg,
                retryable=True,
                raw_response=_sanitize_dict({"items": items, "meta": meta}),
            )

        except Exception as exc:
            msg = _sanitize(f"Instagram publish error: {exc}")
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))


# ── VK Clips ──────────────────────────────────────────────────

class VKPublisher(PublisherAdapter):
    """Upload via VK API: video.save → upload → video.save confirm.

    Uses VK_ACCESS_TOKEN from settings.
    account may have additional owner_id info.
    """

    platform = "VK"

    async def publish(
        self,
        task: PublishTask,
        account: SocialAccount,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> PublishResult:
        settings = get_settings()
        if not settings.vk_access_token:
            msg = "VK_ACCESS_TOKEN not configured — cannot publish to VK"
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

        try:
            # Determine owner_id for group or user
            creds = (account.credentials_json or {}) if hasattr(account, "credentials_json") else {}
            owner_id = creds.get("owner_id")
            group_id = None
            if owner_id and int(owner_id) < 0:
                group_id = abs(int(owner_id))

            self._log(task.id, f"VK video.save (group_id={group_id})")

            vk_params: dict[str, Any] = {
                "access_token": settings.vk_access_token,
                "v": settings.vk_api_version,
                "name": title[:128],
                "description": description[:2000],
                "is_private": 0,
                "wallpost": 0,
                "repeat": 0,
            }
            if group_id:
                vk_params["group_id"] = group_id

            async with httpx.AsyncClient(timeout=120) as client:
                # Step 1: video.save — get upload URL
                save_resp = await client.get(
                    "https://api.vk.com/method/video.save",
                    params=vk_params,
                )
                save_data = save_resp.json()
                if "error" in save_data:
                    msg = _sanitize(f"VK video.save error: {save_data['error'].get('error_msg', save_data['error'])}")
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))

                response = save_data.get("response", {})
                upload_url = response.get("upload_url")
                video_id = response.get("video_id")
                owner_result_id = response.get("owner_id")

                if not upload_url:
                    msg = "VK video.save did not return upload_url"
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=False)

                # Step 2: upload video file
                self._log(task.id, f"Uploading {file_path.name} to VK ({file_path.stat().st_size} bytes)")
                with open(file_path, "rb") as f:
                    upload_resp = await client.post(
                        upload_url,
                        files={"video_file": (file_path.name, f, "video/mp4")},
                    )

                upload_data = upload_resp.json()
                if upload_data.get("error"):
                    msg = _sanitize(f"VK upload error: {upload_data}")
                    self._error(task.id, msg)
                    return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))

                # Build URL
                vid = video_id or upload_data.get("video_id")
                oid = owner_result_id or upload_data.get("owner_id")
                url = f"https://vk.com/video{oid}_{vid}" if oid and vid else None

                self._log(task.id, f"Published: {url}")
                return PublishResult(
                    success=True,
                    external_id=f"{oid}_{vid}" if oid and vid else str(vid),
                    url=url,
                    platform=self.platform,
                    raw_response=_sanitize_dict({"save": response, "upload": upload_data}),
                )

        except Exception as exc:
            msg = _sanitize(f"VK publish error: {exc}")
            self._error(task.id, msg)
            return PublishResult(success=False, platform=self.platform, error=msg, retryable=_is_retryable_error(msg))


# ── Registry ──────────────────────────────────────────────────

_ADAPTERS: dict[str, PublisherAdapter] = {
    "youtube": YouTubePublisher(),
    "tiktok": TikTokPublisher(),
    "instagram": InstagramPublisher(),
    "vk": VKPublisher(),
}


def get_publisher(platform: str) -> PublisherAdapter | None:
    """Get publisher adapter for a given platform (case-insensitive)."""
    return _ADAPTERS.get(platform.lower())


def list_publishers() -> list[str]:
    """List all registered platform adapters."""
    return list(_ADAPTERS.keys())
