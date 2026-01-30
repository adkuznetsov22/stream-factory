from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import HTTPException, status

from app.settings import get_settings

settings = get_settings()

BASE_URL = "https://api.vk.com/method"


def parse_vk_ref(input_str: str) -> dict:
    raw = (input_str or "").strip()
    if not raw:
        raise ValueError("VK reference is empty")
    raw = raw.replace("https://", "").replace("http://", "")
    raw = raw.replace("vk.com/", "")
    raw = raw.replace("m.vk.com/", "")
    raw = raw.strip("/")
    if raw.startswith("@"):
        raw = raw[1:]
    if raw.startswith("id") and raw[2:].isdigit():
        return {"screen_name": None, "owner_hint": int(raw[2:]), "is_group": False}
    if (raw.startswith("club") or raw.startswith("public")) and raw[len(raw.split(' ')[0]):].replace("club", "").replace("public", "").isdigit():
        num = raw.replace("club", "").replace("public", "")
        return {"screen_name": None, "owner_hint": -int(num), "is_group": True}
    return {"screen_name": raw, "owner_hint": None, "is_group": False}


async def _vk_call(method: str, params: dict) -> dict:
    if not settings.vk_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VK_ACCESS_TOKEN missing")
    query = {"access_token": settings.vk_access_token, "v": settings.vk_api_version, **params}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE_URL}/{method}", params=query)
    data = resp.json()
    if "error" in data:
        message = data["error"].get("error_msg", "VK API error")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message)
    return data.get("response", {})


async def resolve_owner(ref: dict) -> dict:
    if ref.get("owner_hint") is not None:
        owner_id = ref["owner_hint"]
        is_group = owner_id < 0
        if is_group:
            info = await _vk_call("groups.getById", {"group_ids": abs(owner_id)})
            group = info[0]
            return {
                "owner_id": owner_id,
                "is_group": True,
                "name": group.get("name", ""),
                "screen_name": group.get("screen_name"),
                "photo_200": group.get("photo_200"),
                "description": group.get("description"),
                "members_count": group.get("members_count"),
                "country": group.get("country", {}).get("title") if isinstance(group.get("country"), dict) else None,
            }
        info = await _vk_call("users.get", {"user_ids": owner_id, "fields": "photo_200,followers_count,country"})
        user = info[0]
        return {
            "owner_id": owner_id,
            "is_group": False,
            "name": f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
            "screen_name": user.get("screen_name"),
            "photo_200": user.get("photo_200"),
            "followers_count": user.get("followers_count"),
            "country": user.get("country", {}).get("title") if isinstance(user.get("country"), dict) else None,
        }
    screen_name = ref.get("screen_name")
    if not screen_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VK screen name required")
    res = await _vk_call("utils.resolveScreenName", {"screen_name": screen_name})
    if not res or "object_id" not in res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VK profile not found")
    type_ = res.get("type")
    object_id = res.get("object_id")
    if type_ in ("group", "page"):
        group_info = await _vk_call("groups.getById", {"group_ids": object_id, "fields": "members_count,description,country,photo_200"})
        group = group_info[0]
        return {
            "owner_id": -int(object_id),
            "is_group": True,
            "name": group.get("name", ""),
            "screen_name": group.get("screen_name") or screen_name,
            "photo_200": group.get("photo_200"),
            "description": group.get("description"),
            "members_count": group.get("members_count"),
            "country": group.get("country", {}).get("title") if isinstance(group.get("country"), dict) else None,
        }
    user_info = await _vk_call("users.get", {"user_ids": object_id, "fields": "photo_200,followers_count,country"})
    user = user_info[0]
    return {
        "owner_id": int(object_id),
        "is_group": False,
        "name": f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
        "screen_name": user.get("screen_name") or screen_name,
        "photo_200": user.get("photo_200"),
        "followers_count": user.get("followers_count"),
        "country": user.get("country", {}).get("title") if isinstance(user.get("country"), dict) else None,
    }


async def fetch_wall(owner_id: int, limit: int) -> List[Dict[str, Any]]:
    posts: list[dict] = []
    offset = 0
    while offset < limit:
        count = min(100, limit - offset)
        resp = await _vk_call(
            "wall.get",
            {
                "owner_id": owner_id,
                "count": count,
                "offset": offset,
                "extended": 0,
            },
        )
        items = resp.get("items", [])
        posts.extend(items)
        if len(items) < count:
            break
        offset += count
    return posts


async def fetch_videos(owner_id: int, limit: int) -> List[Dict[str, Any]]:
    videos: list[dict] = []
    offset = 0
    while offset < limit:
        count = min(200, limit - offset)
        resp = await _vk_call(
            "video.get",
            {
                "owner_id": owner_id,
                "count": count,
                "offset": offset,
                "extended": 1,
            },
        )
        items = resp.get("items", [])
        videos.extend(items)
        if len(items) < count:
            break
        offset += count
    return videos


async def fetch_clips(owner_id: int, limit: int) -> List[Dict[str, Any]]:
    clips: list[dict] = []
    offset = 0
    while offset < limit:
        count = min(100, limit - offset)
        # VK API: clips.get returns clips for user/group depending on owner_id sign
        resp = await _vk_call(
            "clips.get",
            {
                "owner_id": owner_id,
                "count": count,
                "offset": offset,
                "extended": 1,
            },
        )
        items = resp.get("items", [])
        # items can be list of dict with key \"clip\" inside depending on version
        for it in items:
            clips.append(it.get("clip") or it)
        if len(items) < count:
            break
        offset += count
    return clips
