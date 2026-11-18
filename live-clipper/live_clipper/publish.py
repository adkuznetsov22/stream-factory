"""Platform publishers. Each takes a target config dict (credentials) and a post dict, returns url + remote ids."""
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

TG = "https://api.telegram.org/bot{token}/{method}"
VK = "https://api.vk.com/method/{method}"

# Fields each platform needs; used by the admin panel to render the form.
FIELDS = {
    "telegram": ["bot_token", "chat_id"],
    "vk": ["access_token", "group_id"],
    "youtube": ["client_id", "client_secret", "refresh_token", "privacy"],
}
CAPTIONS = {
    "telegram": "{title}\n\n{description}\n\n▶️ {link}\n{hashtags}",
    "vk": "{description}\n\nСтрим: {link}\n{hashtags}",
    "youtube": "{description}\n\nСтрим: {link}\n{hashtags} #shorts",
}
LIMITS = {"telegram": 1024, "vk": 5000, "youtube": 4900}


class _Fmt(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def build_post(kind: str, template: str | None, meta: dict, login: str, name: str, hashtags: list[str]) -> dict:
    tags = list(dict.fromkeys(hashtags))
    caption = (template or CAPTIONS[kind]).format_map(_Fmt(
        title=meta.get("title", ""), description=meta.get("description", ""), streamer=name, login=login,
        link=f"https://twitch.tv/{login}", hashtags=" ".join(tags),
    ))
    caption = "\n".join(line.rstrip() for line in caption.strip().splitlines())
    while "\n\n\n" in caption:
        caption = caption.replace("\n\n\n", "\n\n")
    return {"title": meta.get("title", "")[:100], "caption": caption[: LIMITS[kind]],
            "tags": [t.lstrip("#") for t in tags] + [login, "gta 6"]}


async def _tg(client: httpx.AsyncClient, cfg: dict, method: str, **kw) -> dict:
    r = await client.post(TG.format(token=cfg["bot_token"], method=method), **kw)
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"telegram {method}: {body.get('description', r.status_code)}")
    return body["result"]


async def _vk(client: httpx.AsyncClient, cfg: dict, method: str, **params) -> dict | list:
    r = await client.post(VK.format(method=method), data={**params, "access_token": cfg["access_token"], "v": "5.199"},
                          timeout=30)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"vk {method}: {body['error'].get('error_msg')}")
    return body["response"]


async def _yt_token(client: httpx.AsyncClient, cfg: dict) -> dict:
    r = await client.post("https://oauth2.googleapis.com/token", data={
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"], "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"youtube token: {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---- publish -----------------------------------------------------------------
async def telegram(client: httpx.AsyncClient, cfg: dict, video: Path, post: dict) -> dict:
    with video.open("rb") as f:
        msg = await _tg(client, cfg, "sendVideo", timeout=300,
                        data={"chat_id": cfg["chat_id"], "caption": post["caption"], "supports_streaming": "true",
                              "width": "1080", "height": "1920"},
                        files={"video": (video.name, f, "video/mp4")})
    chat = msg["chat"]
    url = f"https://t.me/{chat['username']}/{msg['message_id']}" if chat.get("username") else None
    return {"url": url, "remote": {"chat_id": chat["id"], "message_id": msg["message_id"]}}


async def vk(client: httpx.AsyncClient, cfg: dict, video: Path, post: dict) -> dict:
    resp = await _vk(client, cfg, "video.save", name=post["title"], description=post["caption"],
                     group_id=cfg["group_id"], wallpost=1)
    with video.open("rb") as f:
        up = await client.post(resp["upload_url"], files={"video_file": (video.name, f, "video/mp4")}, timeout=600)
    up.raise_for_status()
    return {"url": f"https://vk.com/video{resp['owner_id']}_{resp['video_id']}",
            "remote": {"owner_id": resp["owner_id"], "video_id": resp["video_id"]}}


async def youtube(client: httpx.AsyncClient, cfg: dict, video: Path, post: dict) -> dict:
    auth = await _yt_token(client, cfg)
    init = await client.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={**auth, "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(video.stat().st_size)},
        json={
            "snippet": {"title": post["title"], "description": post["caption"], "tags": post["tags"],
                        "categoryId": "20", "defaultLanguage": "ru"},
            "status": {"privacyStatus": cfg.get("privacy") or "public", "selfDeclaredMadeForKids": False},
        },
        timeout=30,
    )
    if init.status_code != 200:
        raise RuntimeError(f"youtube upload init: {init.text[:300]}")
    up = await client.put(init.headers["Location"], headers={**auth, "Content-Type": "video/mp4"},
                          content=video.read_bytes(), timeout=600)
    up.raise_for_status()
    vid = up.json()["id"]
    return {"url": f"https://youtube.com/shorts/{vid}", "remote": {"video_id": vid}}


# ---- delete --------------------------------------------------------------------
async def delete_telegram(client, cfg, remote):
    await _tg(client, cfg, "deleteMessage", data=remote, timeout=15)


async def delete_vk(client, cfg, remote):
    await _vk(client, cfg, "video.delete", owner_id=remote["owner_id"], video_id=remote["video_id"])


async def delete_youtube(client, cfg, remote):
    auth = await _yt_token(client, cfg)
    r = await client.delete(f"https://www.googleapis.com/youtube/v3/videos?id={remote['video_id']}", headers=auth,
                            timeout=30)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"youtube delete: {r.text[:200]} (нужен scope youtube, а не только youtube.upload)")


# ---- views (None when the platform API does not expose them) --------------------
async def views_telegram(client, cfg, remote):
    return None  # Bot API does not return channel post views


async def views_vk(client, cfg, remote):
    resp = await _vk(client, cfg, "video.get", videos=f"{remote['owner_id']}_{remote['video_id']}")
    items = resp.get("items") or []
    return items[0].get("views") if items else None


async def views_youtube(client, cfg, remote):
    auth = await _yt_token(client, cfg)
    r = await client.get(f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={remote['video_id']}",
                         headers=auth, timeout=15)
    items = r.json().get("items") or [] if r.status_code == 200 else []
    return int(items[0]["statistics"].get("viewCount", 0)) if items else None


# ---- checks ----------------------------------------------------------------------
async def check_telegram(client: httpx.AsyncClient, cfg: dict) -> str:
    me = await _tg(client, cfg, "getMe", timeout=15)
    try:
        chat = await _tg(client, cfg, "getChat", data={"chat_id": cfg["chat_id"]}, timeout=15)
    except RuntimeError as e:
        if "not found" in str(e):
            raise RuntimeError(f"канал {cfg['chat_id']} не найден: проверьте адрес и что @{me['username']} добавлен "
                               "в канал администратором") from e
        raise
    member = await _tg(client, cfg, "getChatMember", data={"chat_id": cfg["chat_id"], "user_id": me["id"]}, timeout=15)
    can_post = member["status"] == "creator" or member.get("can_post_messages") or (
        chat["type"] != "channel" and member["status"] in ("administrator", "member"))
    if not can_post:
        raise RuntimeError(f"бот @{me['username']} не может публиковать в «{chat.get('title')}»: сделайте его "
                           "админом с правом «Публикация сообщений»")
    return f"бот @{me['username']} → «{chat.get('title')}»: права на публикацию есть"


async def check_vk(client: httpx.AsyncClient, cfg: dict) -> str:
    groups = await _vk(client, cfg, "groups.getById", group_id=cfg["group_id"], fields="is_admin")
    g = (groups.get("groups") if isinstance(groups, dict) else groups)[0]
    if not g.get("is_admin"):
        raise RuntimeError(f"аккаунт токена не админ сообщества «{g['name']}»")
    return f"сообщество «{g['name']}»: права администратора есть"


async def check_youtube(client: httpx.AsyncClient, cfg: dict) -> str:
    auth = await _yt_token(client, cfg)
    r = await client.get("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", headers=auth, timeout=15)
    if r.status_code != 200:
        return "токен действителен; канал определится при первой загрузке (scope youtube.upload)"
    items = r.json().get("items") or []
    return f"канал «{items[0]['snippet']['title']}»" if items else "токен действителен, канал не найден"


# ---- test post: proves posting rights without leaving a post behind ---------------
async def test_telegram(client, cfg) -> str:
    msg = await _tg(client, cfg, "sendMessage", data={"chat_id": cfg["chat_id"], "text": "Проверка публикации",
                                                       "disable_notification": "true"}, timeout=15)
    await _tg(client, cfg, "deleteMessage", data={"chat_id": msg["chat"]["id"], "message_id": msg["message_id"]},
              timeout=15)
    return "сообщение опубликовано и сразу удалено"


async def test_vk(client, cfg) -> str:
    gid = -abs(int(cfg["group_id"]))
    resp = await _vk(client, cfg, "wall.post", owner_id=gid, from_group=1, message="Проверка публикации")
    await _vk(client, cfg, "wall.delete", owner_id=gid, post_id=resp["post_id"])
    return "пост на стене опубликован и сразу удалён"


async def test_youtube(client, cfg) -> str:
    return await check_youtube(client, cfg) + ". Пробную загрузку не делаем: она тратит 1600 единиц квоты"


PUBLISHERS = {"telegram": telegram, "vk": vk, "youtube": youtube}
DELETERS = {"telegram": delete_telegram, "vk": delete_vk, "youtube": delete_youtube}
VIEWS = {"telegram": views_telegram, "vk": views_vk, "youtube": views_youtube}
CHECKS = {"telegram": check_telegram, "vk": check_vk, "youtube": check_youtube}
TESTS = {"telegram": test_telegram, "vk": test_vk, "youtube": test_youtube}
