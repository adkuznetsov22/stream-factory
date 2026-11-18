import asyncio
import random
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from . import policy, publish

if TYPE_CHECKING:
    from .app import App

log = logging.getLogger(__name__)


class Publisher:
    """Per-target publication queue: auto-picks the best fresh clip within each target's rules."""

    def __init__(self, app: "App"):
        self.app = app
        self.store = app.store
        self.busy: set[int] = set()

    def seed_targets(self):
        if self.store.targets():
            return
        s = self.app.s
        seeds = [
            ("telegram", "Telegram", {"bot_token": s.telegram_bot_token, "chat_id": s.telegram_chat_id},
             dict(daily_limit=100, min_score=8, min_interval_min=5)),
            ("vk", "VK", {"access_token": s.vk_access_token, "group_id": s.vk_group_id},
             dict(daily_limit=50, min_score=9, min_interval_min=10)),
            ("youtube", "YouTube Shorts", {"client_id": s.youtube_client_id, "client_secret": s.youtube_client_secret,
                                           "refresh_token": s.youtube_refresh_token, "privacy": s.youtube_privacy},
             dict(daily_limit=6, min_score=12, min_interval_min=60)),
        ]
        for kind, name, cfg, limits in seeds:
            if any(v for k, v in cfg.items() if k != "privacy"):
                self.store.add_target(kind=kind, name=name, config=cfg, enabled=0, **limits)

    # ---- rules -------------------------------------------------------------------
    def _now_local(self) -> datetime:
        return datetime.now(ZoneInfo(self.app.s.timezone))

    def quiet_until(self, t: dict) -> float | None:
        qf, qt = t.get("quiet_from"), t.get("quiet_to")
        if qf is None or qt is None or qf == qt:
            return None
        now = self._now_local()
        h = now.hour
        quiet = (qf <= h < qt) if qf < qt else (h >= qf or h < qt)
        if not quiet:
            return None
        end = now.replace(hour=qt, minute=0, second=0, microsecond=0)
        if end <= now:
            end += timedelta(days=1)
        return end.timestamp()

    def _stats(self, t: dict) -> dict:
        return self.store.row(
            "SELECT COUNT(*) AS n, MAX(done_at) AS last, MIN(done_at) AS first FROM publications "
            "WHERE target_id = ? AND status = 'done' AND done_at > ?", t["id"], time.time() - 86400)

    def candidates(self, t: dict, limit: int = 1) -> list[dict]:
        rows = self.store.rows(
            "SELECT id, login, score, judge, safety FROM clips c WHERE status IN ('ready', 'published') AND manual = 0 "
            "AND duplicate_of IS NULL AND path IS NOT NULL AND score >= ? AND created_at >= ? AND NOT EXISTS "
            "(SELECT 1 FROM publications p WHERE p.clip_id = c.id AND p.target_id = ?) ORDER BY score DESC LIMIT 200",
            t["min_score"], time.time() - self.app.s.max_publish_age_min * 60, t["id"])
        ok = []
        for r in rows:
            d = policy.decide(t.get("policy"), r)
            if d["action"] == "allow":
                ok.append({**r, "rank": d["rank"]})
        ok.sort(key=lambda r: -r["rank"])
        explore = policy.normalize(t.get("policy"))["explore"]
        if len(ok) > 1 and random.random() < explore:
            pick = random.choice(ok[1:])
            ok = [{**pick, "explore": True}] + [r for r in ok if r["id"] != pick["id"]]
        return ok[:limit]

    def plan(self, t: dict) -> dict:
        """Why the target is (not) posting right now and when the next post can go."""
        now = time.time()
        queued = self.store.row("SELECT COUNT(*) AS n FROM publications WHERE target_id = ? AND status = 'queued'",
                                t["id"])["n"]
        st = self._stats(t)
        base = {"today": st["n"], "queued": queued, "at": None}
        if not t["enabled"]:
            return {**base, "state": "off", "reason": "площадка выключена"}
        if self.app.s.publish_paused:
            return {**base, "state": "paused", "reason": "вся публикация на паузе"}
        if t["id"] in self.busy:
            return {**base, "state": "publishing", "reason": "идёт загрузка", "at": now}
        q = self.quiet_until(t)
        if q:
            return {**base, "state": "quiet", "reason": "тихие часы", "at": q}
        if queued:
            return {**base, "state": "ready", "reason": f"в очереди {queued}", "at": now}
        if t["mode"] != "auto":
            return {**base, "state": "manual", "reason": "ждёт клипов, отправленных вручную"}
        if st["n"] >= t["daily_limit"]:
            return {**base, "state": "limit", "reason": "дневной лимит исчерпан", "at": st["first"] + 86400}
        if st["last"] and now - st["last"] < t["min_interval_min"] * 60:
            return {**base, "state": "interval", "reason": "пауза между постами",
                    "at": st["last"] + t["min_interval_min"] * 60}
        if not self.candidates(t):
            return {**base, "state": "waiting",
                    "reason": f"нет клипов с баллом ≥ {t['min_score']:g} за {self.app.s.max_publish_age_min} мин"}
        return {**base, "state": "ready", "reason": "есть подходящий клип", "at": now}

    # ---- loop --------------------------------------------------------------------
    def tick(self) -> list[asyncio.Task]:
        tasks = []
        if self.app.s.publish_paused:
            return tasks
        for t in self.store.targets(enabled_only=True):
            if t["id"] in self.busy or self.quiet_until(t):
                continue
            pub = self.store.row("SELECT id, clip_id FROM publications WHERE target_id = ? AND status = 'queued' "
                                 "ORDER BY id LIMIT 1", t["id"])
            if not pub and t["mode"] == "auto" and self.plan(t)["state"] == "ready":
                c = self.candidates(t)
                pub_id = c and self.store.add_publication(c[0]["id"], t["id"])
                pub = pub_id and {"id": pub_id, "clip_id": c[0]["id"]}
            if pub:
                self.busy.add(t["id"])
                tasks.append(asyncio.create_task(self._publish(t, pub["id"], pub["clip_id"])))
        return tasks

    async def loop(self):
        for p in self.store.rows("SELECT id FROM publications WHERE status = 'publishing'"):
            self.store.update_publication(p["id"], status="error", error="прервано перезапуском")
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("publish loop failed")
            await asyncio.sleep(3)

    def post_for(self, t: dict, clip: dict) -> dict:
        prof = self.app.profile(clip["login"])
        name = prof.get("display_name") or clip["login"]
        return publish.build_post(t["kind"], t.get("caption"), clip["meta"] or {}, clip["login"], name,
                                  list(self.app.s.hashtags) + list(prof.get("hashtags") or []))

    async def _publish(self, t: dict, pub_id: int, clip_id: int):
        try:
            clip = self.store.clip(clip_id)
            self.store.update_publication(pub_id, status="publishing")
            if not clip or not clip["path"] or not Path(clip["path"]).exists():
                raise RuntimeError("файл клипа удалён")
            res = await publish.PUBLISHERS[t["kind"]](self.app.http, t["config"], Path(clip["path"]),
                                                      self.post_for(t, clip))
            self.store.update_publication(pub_id, status="done", url=res.get("url"), remote=res.get("remote"),
                                          done_at=time.time(), error=None)
            self.store.update(clip_id, status="published")
            log.info("опубликовано #%d → %s: %s", clip_id, t["name"], res.get("url") or "ok")
        except Exception as e:
            log.error("публикация #%d → %s не удалась: %s", clip_id, t["name"], e)
            self.store.update_publication(pub_id, status="error", error=str(e)[:500], done_at=time.time())
            self.app.monitor.alert(f"pub:{t['id']}", f"Публикация в «{t['name']}» не удалась: {str(e)[:300]}")
        finally:
            self.busy.discard(t["id"])

    async def delete(self, pub_id: int):
        p = self.store.row("SELECT * FROM publications WHERE id = ?", pub_id)
        t = self.store.target(p["target_id"]) if p else None
        if not p or not t or p["status"] != "done" or not p["remote"]:
            raise RuntimeError("пост не найден или не опубликован")
        await publish.DELETERS[t["kind"]](self.app.http, t["config"], p["remote"])
        self.store.update_publication(pub_id, deleted=1, status="deleted")
        log.info("пост #%d удалён с «%s»", p["clip_id"], t["name"])

    async def views_loop(self):
        while True:
            await asyncio.sleep(900)
            targets = {t["id"]: t for t in self.store.targets()}
            for p in self.store.rows("SELECT * FROM publications WHERE status = 'done' AND done_at > ?",
                                     time.time() - 3 * 86400):
                t = targets.get(p["target_id"])
                if not t or not p["remote"] or t["kind"] == "telegram":
                    continue
                try:
                    views = await publish.VIEWS[t["kind"]](self.app.http, t["config"], p["remote"])
                    if views is not None:
                        self.store.update_publication(p["id"], views=views, views_at=time.time())
                except Exception as e:
                    log.debug("views %s: %s", p["id"], e)
