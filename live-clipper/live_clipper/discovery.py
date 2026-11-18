import logging

import httpx

from .config import Settings
from .twitch import LiveStream, category_streams, live_users

log = logging.getLogger(__name__)


async def discover(client: httpx.AsyncClient, s: Settings) -> list[LiveStream]:
    found: dict[str, LiveStream] = {}
    whitelist = [w.lower() for w in s.whitelist]
    try:
        for st in await live_users(client, whitelist):
            if s.whitelist_any_game or st.game == s.game_name:
                found[st.login] = st
    except Exception:
        log.exception("whitelist lookup failed")
    if s.auto_discover:
        try:
            for st in await category_streams(client, s.game_name, s.language):
                if st.viewers >= s.min_viewers:
                    found.setdefault(st.login, st)
        except Exception:
            log.exception("category lookup failed")
    blocked = {b.lower() for b in s.blacklist}
    ranked = sorted((st for st in found.values() if st.login not in blocked), key=lambda st: (st.login not in whitelist, -st.viewers))
    return ranked[: s.max_streams]
