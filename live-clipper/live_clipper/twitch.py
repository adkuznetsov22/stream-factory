import json
from dataclasses import dataclass

import httpx

GQL_URL = "https://gql.twitch.tv/gql"
# Public web client id (same one streamlink uses); no developer key needed.
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

_STREAM_FIELDS = "id viewersCount title game { name }"


@dataclass
class LiveStream:
    login: str
    display_name: str
    stream_id: str
    viewers: int
    game: str | None
    title: str
    avatar: str | None = None


async def gql(client: httpx.AsyncClient, query: str) -> dict:
    r = await client.post(GQL_URL, headers={"Client-Id": CLIENT_ID}, json={"query": query}, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"twitch gql error: {body['errors']}")
    return body["data"]


async def live_users(client: httpx.AsyncClient, logins: list[str]) -> list[LiveStream]:
    if not logins:
        return []
    parts = [
        f"u{i}: user(login: {json.dumps(login)}) {{ login displayName profileImageURL(width: 70) stream {{ {_STREAM_FIELDS} }} }}"
        for i, login in enumerate(logins)
    ]
    data = await gql(client, "{ " + " ".join(parts) + " }")
    out = []
    for user in data.values():
        if user and user.get("stream"):
            out.append(_to_stream(user, user["stream"]))
    return out


async def category_streams(client: httpx.AsyncClient, game: str, language: str, first: int = 30) -> list[LiveStream]:
    query = (
        f"{{ game(name: {json.dumps(game)}) {{ streams(first: {first}, options: {{broadcasterLanguages: [{language}]}}) "
        f"{{ edges {{ node {{ {_STREAM_FIELDS} broadcaster {{ login displayName profileImageURL(width: 70) }} }} }} }} }} }}"
    )
    data = await gql(client, query)
    if not data.get("game"):
        return []
    return [_to_stream(e["node"]["broadcaster"], e["node"]) for e in data["game"]["streams"]["edges"]]


def _to_stream(user: dict, stream: dict) -> LiveStream:
    return LiveStream(
        login=user["login"].lower(),
        display_name=user.get("displayName") or user["login"],
        stream_id=stream["id"],
        viewers=stream.get("viewersCount") or 0,
        game=(stream.get("game") or {}).get("name"),
        title=stream.get("title") or "",
        avatar=user.get("profileImageURL"),
    )
