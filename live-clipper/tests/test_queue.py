"""Publication queue and retention checks with a fake publisher: python tests/test_queue.py"""
import asyncio
import os
import tempfile
import time
from pathlib import Path

from live_clipper import app as app_mod
from live_clipper import publish as publish_mod
from live_clipper.config import Settings

calls = []


async def fake(client, cfg, video, post):
    calls.append((cfg["chat_id"], video.parent.name, post["title"]))
    if cfg["chat_id"] == "broken":
        raise RuntimeError("boom")
    return {"url": f"https://t.me/test/{len(calls)}", "remote": {"message_id": len(calls)}}


def make_clip(a, login, score, age=0.0, manual=False):
    cid = a.store.add(login, 0, 1, score, manual=manual)
    d = a.s.clips_dir / f"{login}_{cid}"
    d.mkdir(parents=True)
    (d / "clip.mp4").write_bytes(b"x")
    a.store.update(cid, status="ready", path=str(d / "clip.mp4"), created_at=time.time() - age,
                   meta={"title": f"t{cid}", "description": "", "tags": []})
    return cid


async def tick(a):
    await asyncio.gather(*a.publisher.tick())


async def main():
    publish_mod.PUBLISHERS["telegram"] = fake
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=Path(tmp), admin_password="x", telegram_bot_token=None, vk_access_token=None,
                     youtube_client_id=None, youtube_refresh_token=None, youtube_client_secret=None)
        a = app_mod.App(s)
        auto = a.store.add_target(kind="telegram", name="auto", config={"chat_id": "a"}, enabled=1, mode="auto",
                                  daily_limit=2, min_score=8, min_interval_min=0)
        manual = a.store.add_target(kind="telegram", name="manual", config={"chat_id": "m"}, enabled=1,
                                    mode="manual", daily_limit=10, min_score=0, min_interval_min=0)
        low = make_clip(a, "buster", 5)
        best = make_clip(a, "buster", 20)
        mid = make_clip(a, "recrent", 9)
        make_clip(a, "recrent", 30, age=3600)        # too old for auto
        make_clip(a, "recrent", 40, manual=True)     # manual clips are never auto-published
        dup = make_clip(a, "evelone2004", 50)
        a.store.update(dup, duplicate_of=best)       # duplicates of co-streams are never auto-published

        await tick(a)
        assert calls == [("a", f"buster_{best}", f"t{best}")], calls
        await tick(a)
        assert calls[-1][1] == f"recrent_{mid}", calls
        await tick(a)
        assert len(calls) == 2, "daily limit 2 must stop the third post"

        a.store.update_target(auto, daily_limit=10, min_interval_min=5)
        await tick(a)
        assert len(calls) == 2, "interval must hold the next post"

        a.store.add_publication(low, manual)
        await tick(a)
        assert calls[-1] == ("m", f"buster_{low}", f"t{low}"), calls
        assert a.store.clip(low)["status"] == "published"

        a.store.update_target(manual, config={"chat_id": "broken"})
        a.store.add_publication(mid, manual)
        await tick(a)
        err = a.store.row("SELECT * FROM publications WHERE clip_id = ? AND target_id = ?", mid, manual)
        assert err["status"] == "error" and "boom" in err["error"], err

        s.publish_paused = True
        a.store.add_publication(best, manual)
        assert a.publisher.tick() == []
        s.publish_paused = False

        a.store.update_target(auto)  # empty update is a no-op
        a.store.update_target(auto, quiet_from=0, quiet_to=0)
        assert a.publisher.quiet_until(a.store.target(auto)) is None
        h = a.publisher._now_local().hour
        a.store.update_target(auto, quiet_from=h, quiet_to=(h + 2) % 24)
        assert a.publisher.quiet_until(a.store.target(auto)) and a.publisher.plan(a.store.target(auto))["state"] == "quiet"

        from live_clipper.publish import build_post
        post = build_post("telegram", None, {"title": "T", "description": ""}, "buster", "Бустер", ["#gta6", "#gta6"])
        assert post["caption"] == "T\n\n▶️ https://twitch.tv/buster\n#gta6", post

        old = make_clip(a, "t2x2", 1, age=13 * 3600)
        kept = a.store.clip(best)["path"]
        a.store.update(best, created_at=time.time() - 13 * 3600)  # published: kept for 72 h
        a.cleanup()
        assert a.store.clip(old)["path"] is None and not (s.clips_dir / f"t2x2_{old}").exists()
        assert a.store.clip(best)["path"] == kept and os.path.exists(kept)
        await a.http.aclose()
    print("ok:", len(calls), "publications")


asyncio.run(main())
