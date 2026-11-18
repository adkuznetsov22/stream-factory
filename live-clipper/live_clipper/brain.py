"""Learning signals: viewer-made Twitch clips (ground truth), per-second features, quality metrics."""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING

from .twitch import gql

if TYPE_CHECKING:
    from .app import App

log = logging.getLogger(__name__)

LAUGH = re.compile(r"(?i)(ах{1,}а|ха{2,}|хах|аха|lul|kekw|omegalul|ору|рофл|лол\b|😂|🤣)")
SHOCK = re.compile(r"(?i)(wtf|что\?+|чтоо|жесть|капец|ебать|ахуе|охуе|pog|monkas|ужас|😱|😳)")
HYPE_W = re.compile(r"(?i)(pogchamp|poggers|letsgo|гооо|ееее|база|красав|gg\b|изи|ez\b|🔥)")
CLIPWORD = re.compile(r"(?i)(\bклип|\bclip|\+клип|в нарезк|в шортс|в тикток)")
CLIPS_Q = """{ user(login:"%s"){ clips(first:%d, criteria:{period:LAST_DAY, sort:%s}){ edges{ node{
  slug title viewCount createdAt durationSeconds curator{login} } } } } }"""
POPULAR = 300


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class Brain:
    def __init__(self, app: "App"):
        self.app = app
        self.store = app.store
        self.pending: list[tuple] = []
        self.crowd: dict[str, list[float]] = {}
        from collections import deque
        from .ranker import Ranker
        self.ranker = Ranker(app.s.data_dir)
        self.recent: dict[str, deque] = {}
        self.model_trigger: dict[str, float] = {}
        self.last_train: dict = {}
        self._deque = deque

    # ---- per-second features -------------------------------------------------
    def log_second(self, ch, sec: int):
        msgs = ch.chat.messages_between(sec - 1, sec, limit=10_000)
        z_chat, z_audio = ch.detector.last_parts
        texts = " ".join(msgs)
        self.pending.append((ch.stream.login, sec, round(ch.chat.activity(sec - 1), 2), len(msgs), round(z_chat, 2),
                             round(z_audio, 2), ch.detector.audio.get(sec - 1), len(LAUGH.findall(texts)),
                             len(SHOCK.findall(texts)), len(HYPE_W.findall(texts)), len(CLIPWORD.findall(texts)),
                             ch.stream.viewers))
        row = self.pending[-1]
        buf = self.recent.setdefault(row[0], self._deque(maxlen=300))
        buf.append((row[1], *row[2:]))
        self._model_tick(ch, sec, buf)
        if len(self.pending) >= 200:
            self.flush()

    def _model_tick(self, ch, sec: int, buf):
        from .detector import Moment
        if not self.ranker.model or not self.app.s.model_trigger:
            return
        score = self.ranker.score(list(buf))
        login = ch.stream.login
        ch.model_score = score
        if score is None or score < self.ranker.meta["threshold"] or sec - self.model_trigger.get(login, 0) < self.app.s.cooldown:
            return
        self.model_trigger[login] = sec
        if self.store.row("SELECT 1 FROM clips WHERE login = ? AND moment_end > ?", login, sec - 30):
            return
        start = sec - self.app.s.reaction_delay - self.app.s.clip_before
        m = Moment(login, sec - 8, sec, round(score, 2), start, sec + self.app.s.clip_after - self.app.s.reaction_delay,
                   ch.chat.messages_between(sec - 20, sec + 3), {"model": round(score, 2),
                                                                  "threshold": round(self.ranker.meta["threshold"], 2)})
        self.app.submit(m, source="model")

    async def train_loop(self):
        from .ranker import train
        await asyncio.sleep(600)
        while True:
            try:
                self.flush()
                res = await asyncio.to_thread(train, self.store, self.app.s.data_dir)
                self.last_train = res
                self.store.set_settings({"_last_train": res})
                if res.get("promoted"):
                    self.ranker.load()
                    log.info("модель обновлена: ловит %.0f%% популярных моментов против %.0f%% у детектора",
                             res["recall_model"] * 100, res["recall_detector"] * 100)
                else:
                    log.info("обучение: %s", res.get("reason") or f"модель не лучше детектора ({res})")
            except Exception:
                log.exception("обучение не удалось")
            await asyncio.sleep(self.app.s.train_hours * 3600)

    def flush(self):
        if self.pending:
            self.store.db.executemany("INSERT OR REPLACE INTO features VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", self.pending)
            self.store.db.commit()
            self.pending = []

    # ---- viewer clips --------------------------------------------------------
    async def fetch_clips(self, login: str, first: int = 100, sort: str = "VIEWS_DESC") -> list[dict]:
        d = await gql(self.app.http, CLIPS_Q % (login, first, sort))
        return [e["node"] for e in ((d.get("user") or {}).get("clips") or {}).get("edges", [])]

    def _save(self, login: str, n: dict) -> bool:
        new = not self.store.row("SELECT 1 FROM viewer_clips WHERE slug = ?", n["slug"])
        if new:
            self.store.execute(
                "INSERT INTO viewer_clips (slug, login, title, created, duration, views, curator, seen_at, views_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)", n["slug"], login, n["title"], _ts(n["createdAt"]), n["durationSeconds"],
                n["viewCount"], (n.get("curator") or {}).get("login"), time.time(), time.time())
            end = _ts(n["createdAt"])
            ours = self.store.row("SELECT id FROM clips WHERE login = ? AND moment_start < ? AND moment_end > ? "
                                  "ORDER BY id LIMIT 1", login, end + 5, end - n["durationSeconds"] - 20)
            if ours:
                self.store.execute("UPDATE viewer_clips SET clip_id = ? WHERE slug = ?", ours["id"], n["slug"])
        else:
            self.store.execute("UPDATE viewer_clips SET views = ?, views_at = ? WHERE slug = ?",
                               n["viewCount"], time.time(), n["slug"])
        return new

    async def crowd_loop(self):
        """New viewer clips on a live channel are the strongest live signal: the moment already landed."""
        last_views = 0.0
        while True:
            for login, ch in list(self.app.channels.items()):
                try:
                    for n in await self.fetch_clips(login):
                        if self._save(login, n) and _ts(n["createdAt"]) > ch.started:
                            self.on_viewer_clip(ch, n)
                except Exception as e:
                    log.debug("[%s] clips poll: %s", login, e)
            if time.time() - last_views > 900:
                last_views = time.time()
                for login in {r["login"] for r in self.store.rows(
                        "SELECT DISTINCT login FROM viewer_clips WHERE created > ?", time.time() - 86400)}:
                    try:
                        for n in await self.fetch_clips(login, 100, "VIEWS_DESC"):
                            self._save(login, n)
                    except Exception as e:
                        log.debug("[%s] clips views: %s", login, e)
            self.flush()
            await asyncio.sleep(30)

    def on_viewer_clip(self, ch, n: dict):
        from .detector import Moment
        end = _ts(n["createdAt"])
        start = end - n["durationSeconds"]
        login = ch.stream.login
        times = [t for t in self.crowd.get(login, []) if t > end - 120] + [end]
        self.crowd[login] = times
        ours = self.store.row("SELECT id FROM clips WHERE login = ? AND moment_start < ? AND moment_end > ? "
                              "ORDER BY id DESC LIMIT 1", login, end + 5, start - 20)
        if ours:
            self.store.execute("UPDATE viewer_clips SET clip_id = ? WHERE slug = ?", ours["id"], n["slug"])
            log.info("[%s] зрители клипнули наш момент #%d: «%s»", login, ours["id"], n["title"])
            return
        if not ch.recorder.segments or start < ch.recorder.segments[0].wall_start:
            return
        m = Moment(login, start, end - 3, round(max(ch.detector.threshold, 4.0) + 2 * len(times), 2),
                   max(start - 5, ch.recorder.segments[0].wall_start), end + 2,
                   ch.chat.messages_between(start, end + 5),
                   {"crowd": len(times), "viewer_clip": n["slug"], "viewer_title": n["title"]})
        clip_id = self.app.submit(m, source="crowd")
        self.store.execute("UPDATE viewer_clips SET clip_id = ? WHERE slug = ?", clip_id, n["slug"])
        log.info("[%s] зрители клипнули момент, который детектор пропустил → клип #%d («%s»)", login, clip_id, n["title"])

    # ---- quality ------------------------------------------------------------
    def metrics(self, hours: float = 24) -> dict:
        since = time.time() - hours * 3600
        st = self.store
        cov = {r["login"]: (r["a"], r["b"]) for r in st.rows(
            "SELECT login, MIN(sec) AS a, MAX(sec) AS b FROM features WHERE sec > ? GROUP BY login", since)}
        out, total = {}, {"popular": 0, "caught": 0, "ours": 0, "matched": 0}
        for login, (a, b) in cov.items():
            vc = st.rows("SELECT slug, title, created, duration, views, clip_id FROM viewer_clips "
                         "WHERE login = ? AND created BETWEEN ? AND ?", login, a + 120, b)
            ours = st.rows("SELECT id, moment_start, moment_end, score, source FROM clips WHERE login = ? AND manual = 0 "
                           "AND created_at BETWEEN ? AND ?", login, a, b + 120)
            def hit(v):
                return any(o["moment_start"] < v["created"] + 5 and o["moment_end"] > v["created"] - v["duration"] - 20
                           and (o["source"] or "detector") == "detector" for o in ours)
            pop = [v for v in vc if v["views"] >= POPULAR]
            caught = sum(hit(v) for v in pop)
            matched = sum(any(o["moment_start"] < v["created"] + 5 and o["moment_end"] > v["created"] - v["duration"] - 20
                              for v in vc) for o in ours if (o["source"] or "detector") == "detector")
            n_ours = sum((o["source"] or "detector") == "detector" for o in ours)
            out[login] = {"popular": len(pop), "caught": caught, "ours": n_ours, "matched": matched,
                          "hours": round((b - a) / 3600, 1), "crowd": sum(o["source"] == "crowd" for o in ours)}
            for k in total:
                total[k] += out[login][k]
        total["recall"] = round(total["caught"] / total["popular"], 3) if total["popular"] else None
        total["precision"] = round(total["matched"] / total["ours"], 3) if total["ours"] else None
        return {"total": total, "streamers": out}
