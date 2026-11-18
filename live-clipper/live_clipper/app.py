import asyncio
import json
import logging
import secrets
import shutil
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path

import httpx
from pydantic import TypeAdapter

from .audio import loudness_per_second
from .brain import Brain
from .chat import ChatMonitor
from .config import EDITABLE, Settings
from .detector import Detector, Moment
from .discovery import discover
from .ingest import Recorder, Segment
from .monitor import Monitor
from .policy import heuristic_safety
from .judge import merge_safety, safe_judge, safe_verify_clean
from .titles import PROFANITY
from .publisher import Publisher
from .render import LAYOUTS, RenderSpec, Transcriber, cut_source, grab_frame, render_clip
from .store import Store
from .titles import make_meta
from .twitch import LiveStream, live_users

log = logging.getLogger(__name__)


class LogBuffer(logging.Handler):
    def __init__(self, size: int = 2000):
        super().__init__(logging.INFO)
        self.records: deque[dict] = deque(maxlen=size)

    def emit(self, record: logging.LogRecord):
        msg = record.getMessage()
        if record.exc_info and record.levelno >= logging.ERROR:
            msg += f" ({record.exc_info[1]!r})"[:400]
        self.records.append({"ts": record.created, "level": record.levelname, "name": record.name, "msg": msg})


class Channel:
    def __init__(self, stream: LiveStream, app: "App"):
        self.stream = stream
        self.misses = 0
        self.started = time.time()
        self.last_preview = 0.0
        self.chat = ChatMonitor(stream.login, keep_seconds=app.s.buffer_seconds)
        self.detector = Detector(stream.login, self.chat, app.s,
                                 sensitivity=lambda: app.profile(stream.login).get("sensitivity") or 1.0)
        self.recorder = Recorder(stream.login, app.s, on_segment=app.on_segment)
        self.tasks = [asyncio.create_task(self.recorder.run()), asyncio.create_task(self.chat.run())]

    async def stop(self):
        await self.recorder.stop()
        await self.chat.stop()
        for t in self.tasks:
            t.cancel()


class App:
    def __init__(self, s: Settings):
        self.s = s
        self.channels: dict[str, Channel] = {}
        self.queue: asyncio.Queue[tuple] = asyncio.Queue()
        self.rendering: set[int] = set()
        self.store = Store(s.data_dir / "clips.db")
        self.transcriber = Transcriber(s)
        self.http = httpx.AsyncClient()
        self.logs = LogBuffer()
        logging.getLogger("live_clipper").addHandler(self.logs)
        self.discovery_kick = asyncio.Event()
        self.previews = s.data_dir / "previews"
        self.previews.mkdir(parents=True, exist_ok=True)
        self._migrate_settings()
        self.apply_settings(self.store.get_settings(), save=False)
        self.reload_profiles()
        self.publisher = Publisher(self)
        self.monitor = Monitor(self)
        self.brain = Brain(self)
        self.publisher.seed_targets()
        self._migrate_legacy()
        self.admin_password = s.admin_password or self._generated_password()

    # ---- settings / streamer profiles ------------------------------------------
    def apply_settings(self, values: dict, save: bool = True) -> dict:
        clean = {k: TypeAdapter(Settings.model_fields[k].annotation).validate_python(v)
                 for k, v in values.items() if k in EDITABLE}
        if "layout" in clean and clean["layout"] not in LAYOUTS:
            raise ValueError(f"layout: {', '.join(LAYOUTS)}")
        for k, v in clean.items():
            setattr(self.s, k, v)
        if save and clean:
            self.store.set_settings(clean)
            self.discovery_kick.set()
        return clean

    def _migrate_settings(self):
        stored = self.store.get_settings()
        if self.store.streamers() or stored.get("_streamers_migrated"):
            return
        for login in stored.get("whitelist", self.s.whitelist):
            self.store.upsert_streamer(login, list="white")
        for login in stored.get("blacklist", self.s.blacklist):
            self.store.upsert_streamer(login, list="black")
        for login, rect in stored.get("facecam", self.s.facecam).items():
            self.store.upsert_streamer(login, facecam=rect, layout="facecam")
        self.store.set_settings({"_streamers_migrated": True})

    def reload_profiles(self):
        self.profiles = {p["login"]: p for p in self.store.streamers()}
        self.s.whitelist = [k for k, p in self.profiles.items() if p["list"] == "white"]
        self.s.blacklist = [k for k, p in self.profiles.items() if p["list"] == "black"]
        self.discovery_kick.set()

    def profile(self, login: str) -> dict:
        return self.profiles.get(login) or {}

    def _migrate_legacy(self):
        for c in self.store.rows("SELECT id, path FROM clips WHERE status = 'rendered'"):
            meta_file = Path(c["path"] or "").parent / "meta.json"
            meta = json.loads(meta_file.read_text()) if c["path"] and meta_file.exists() else None
            if meta:
                transcript = meta.pop("transcript", "")
                meta = {k: meta[k] for k in ("overlay", "title", "description") if k in meta}
                meta["description"] = meta.get("description", "").split("\n\nСтрим:")[0]
                self.store.update(c["id"], status="ready", meta=meta, transcript=transcript)
            else:
                self.store.update(c["id"], status="ready", path=None)

    def _generated_password(self) -> str:
        path = self.s.data_dir / "admin_password.txt"
        if not path.exists():
            path.write_text(secrets.token_urlsafe(12))
            path.chmod(0o600)
        log.warning("LC_ADMIN_PASSWORD не задан: пароль админки лежит в %s", path)
        return path.read_text().strip()

    # ---- pipeline --------------------------------------------------------------
    async def on_segment(self, login: str, seg: Segment):
        ch = self.channels.get(login)
        if not ch:
            return
        try:
            ch.detector.add_audio(seg.wall_start, await loudness_per_second(seg.path))
            if time.time() - ch.last_preview > 10:
                ch.last_preview = time.time()
                await grab_frame(seg.path, self.previews / f"{login}.jpg")
        except Exception:
            log.debug("[%s] segment analysis failed", login, exc_info=True)

    async def discovery_loop(self):
        while True:
            try:
                streams = {st.login: st for st in await discover(self.http, self.s)}
                for login, st in streams.items():
                    if login in self.profiles:
                        self.store.upsert_streamer(login, display_name=st.display_name, avatar=st.avatar,
                                                   last_live_at=time.time())
                    if login in self.channels:
                        self.channels[login].stream, self.channels[login].misses = st, 0
                    else:
                        log.info("старт записи %s (%d зрителей)", st.display_name, st.viewers)
                        self.channels[login] = Channel(st, self)
                blocked = set(self.s.blacklist)
                for login in list(self.channels):
                    if login not in streams:
                        ch = self.channels[login]
                        ch.misses += 1
                        if ch.misses >= self.s.drop_after_misses or login in blocked:
                            log.info("стоп записи %s", login)
                            await ch.stop()
                            del self.channels[login]
            except Exception:
                log.exception("discovery failed")
            self.discovery_kick.clear()
            try:
                await asyncio.wait_for(self.discovery_kick.wait(), self.s.discovery_interval)
            except TimeoutError:
                pass

    def _linked(self, a: str, b: str) -> bool:
        def mentions(x: str, y: str) -> bool:
            ch = self.channels.get(x)
            title = (ch.stream.title if ch else "").lower()
            other = self.channels.get(y)
            names = {y, other.stream.display_name.lower()} if other else {y}
            return any(n and n in title for n in names)
        return mentions(a, b) or mentions(b, a)

    def _dedup(self, clip_id: int, m: Moment):
        w = self.s.dedup_window
        for c in self.store.rows(
                "SELECT id, login, score, status FROM clips WHERE id != ? AND login != ? AND duplicate_of IS NULL "
                "AND ABS(moment_start - ?) < ? AND created_at > ?", clip_id, m.login, m.start, w, time.time() - 600):
            if not self._linked(m.login, c["login"]):
                continue
            if c["score"] >= m.score or c["status"] == "published":
                self.store.update(clip_id, duplicate_of=c["id"])
                log.info("момент #%d %s — дубль #%d %s (совместный стрим)", clip_id, m.login, c["id"], c["login"])
            else:
                self.store.update(c["id"], duplicate_of=clip_id)
                log.info("момент #%d %s — дубль #%d %s (совместный стрим)", c["id"], c["login"], clip_id, m.login)
            return

    def submit(self, m: Moment, manual: bool = False, source: str = "detector") -> int:
        clip_id = self.store.add(m.login, m.start, m.end, m.score, manual=manual)
        self.store.update(clip_id, source="manual" if manual else source)
        ch = self.channels.get(m.login)
        reasons = {**m.reasons, "chat_sample": m.chat[-30:]}
        self.store.update(clip_id, reasons=reasons, stream_title=ch.stream.title if ch else None)
        if not manual:
            self._dedup(clip_id, m)
        self.queue.put_nowait(("new", clip_id, m, time.time()))
        log.info("момент #%d %s балл=%.1f%s", clip_id, m.login, m.score, " (вручную)" if manual else "")
        return clip_id

    def manual_clip(self, login: str, seconds: float) -> int:
        ch = self.channels.get(login)
        if not ch or not ch.recorder.segments:
            raise KeyError(login)
        end = ch.recorder.latest_wall
        start = max(end - seconds, ch.recorder.segments[0].wall_start)
        m = Moment(login, end - 5, end - 2, round(ch.detector.last_score, 2), start, end,
                   ch.chat.messages_between(start, end), {"manual": True})
        return self.submit(m, manual=True)

    def rerender(self, clip_id: int, edit: dict):
        self.store.update(clip_id, status="rendering", edit=edit, updated_at=time.time())
        self.queue.put_nowait(("edit", clip_id, None, time.time()))

    async def detect_loop(self):
        while True:
            for ch in list(self.channels.values()):
                m = ch.detector.tick()
                if time.time() - ch.started > 60:
                    self.brain.log_second(ch, int(time.time()))
                if m:
                    self.submit(m)
            await asyncio.sleep(1)

    async def render_worker(self):
        while True:
            kind, clip_id, m, queued_at = await self.queue.get()
            self.rendering.add(clip_id)
            if (self.store.clip(clip_id) or {}).get("status") != "rejected":
                self.store.update(clip_id, status="rendering")
            try:
                if kind == "new":
                    await self.process(clip_id, m, queued_at)
                else:
                    await self.process_edit(clip_id)
            except Exception as e:
                log.exception("клип #%d не собрался", clip_id)
                self.store.update(clip_id, status="error", error=str(e)[:500])
                self.monitor.alert(f"render:{clip_id}", f"Клип #{clip_id} не собрался: {str(e)[:200]}")
            finally:
                self.rendering.discard(clip_id)

    def spec(self, clip: dict) -> RenderSpec:
        e, prof = clip["edit"], self.profile(clip["login"])
        layout = e.get("layout") or prof.get("layout") or self.s.layout
        return RenderSpec(
            trim_start=e["trim_start"], trim_end=e["trim_end"], overlay=e.get("overlay", ""),
            credit=f"twitch.tv/{clip['login']}", layout=layout,
            facecam=e.get("facecam") or prof.get("facecam"),
            subtitles=e.get("subtitles", self.s.subtitles), lines=clip["subs"] or [],
            blur=e.get("blur") or [], mute=e.get("mute") or [],
        )

    async def process(self, clip_id: int, m: Moment, detected_at: float):
        ch = self.channels.get(m.login)
        if not ch:
            raise RuntimeError("стрим уже не пишется")
        pad = self.s.source_padding
        deadline = time.time() + 90
        while ch.recorder.latest_wall < m.end + 1 and time.time() < deadline:
            await asyncio.sleep(0.5)
        segments = ch.recorder.range(m.start - pad, m.end + 1)
        if not segments:
            raise RuntimeError("нет сегментов в буфере")
        clip_dir = self.s.clips_dir / f"{m.login}_{int(m.start)}"
        t = {"detected": detected_at, "buffered": time.time()}
        src, src_wall, src_dur = await cut_source(segments, clip_dir)
        trim = (max(m.start - src_wall, 0.0), min(m.end - src_wall, src_dur))
        try:
            lines = await self.transcriber.lines(src, *trim)
        except Exception:
            log.warning("[%s] речь не распознана (нет звука?)", m.login)
            lines = []
        transcript = " ".join(ln["text"] for ln in lines)
        t["transcribed"] = time.time()
        st = ch.stream
        meta = await make_meta(self.http, self.s, m.login, st.display_name, st.title, transcript, m.chat)
        edit = {"trim_start": round(trim[0], 2), "trim_end": round(trim[1], 2), "overlay": meta["overlay"],
                "subtitles": self.s.subtitles, "subs_range": [trim[0], trim[1]], "src_wall": src_wall}
        hype = [[round(sec - src_wall, 1), score] for sec, score, *_ in ch.detector.history
                if src_wall <= sec <= src_wall + src_dur]
        titles = [r["title"] for r in self.store.rows("SELECT title FROM viewer_clips WHERE clip_id = ?", clip_id)]
        safety = heuristic_safety(transcript, m.chat, titles)
        verdict = await safe_judge(self.http, self.s, src, trim[0], trim[1], st.display_name, st.title, lines, m.chat, titles)
        t["judged"] = time.time()
        if verdict:
            safety = merge_safety(safety, verdict)
            meta = {**meta, **{k: verdict[k] for k in ("overlay", "title", "description") if verdict.get(k)}}
            if verdict.get("trim"):
                trim = (trim[0] + verdict["trim"]["start"], trim[0] + verdict["trim"]["end"])
                edit.update(trim_start=round(trim[0], 2), trim_end=round(trim[1], 2), overlay=meta["overlay"])
            if verdict.get("banners"):
                edit["blur"] = verdict["banners"]
        edit["mute"] = [[ln["start"] - 0.15, ln["end"] + 0.15] for ln in lines if PROFANITY.search(ln["text"])]
        self.store.update(clip_id, edit=edit, subs=lines, src_path=str(src), src_duration=round(src_dur, 2), safety=safety,
                          judge=verdict)
        video = await render_clip(self.s, clip_dir, self.spec(self.store.clip(clip_id)))
        t["rendered"] = time.time()
        if edit.get("blur"):
            safety["blur_check"] = await safe_verify_clean(self.http, self.s, video)
            self.store.update(clip_id, safety=safety)
            t["verified"] = time.time()
        (clip_dir / "meta.json").write_text(
            json.dumps({**meta, "moment": asdict(m), "transcript": transcript}, ensure_ascii=False, indent=2))
        timings = {k: round(v - m.end, 1) for k, v in t.items()}
        timings["ready"] = round(time.time() - m.end, 1)
        reasons = {**(self.store.clip(clip_id)["reasons"] or {}), "hype": hype}
        rejected = self.store.clip(clip_id)["status"] == "rejected"
        self.store.update(clip_id, status="rejected" if rejected else "ready", title=meta["title"], meta=meta, transcript=transcript,
                          path=str(video), timings=timings, reasons=reasons, updated_at=time.time())
        log.info("клип #%d %s готов через %.0f с после момента", clip_id, m.login, timings["ready"])
        asyncio.create_task(self._source_preview(clip_dir))

    async def _source_preview(self, clip_dir: Path):
        try:
            from .render import run_ffmpeg
            await run_ffmpeg(["-i", "src.ts", "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast",
                              "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", "source.mp4"],
                             clip_dir)
        except Exception:
            log.warning("не удалось сделать превью исходника %s", clip_dir.name)

    async def process_edit(self, clip_id: int):
        c = self.store.clip(clip_id)
        if not c["src_path"] or not Path(c["src_path"]).exists():
            raise RuntimeError("исходник уже удалён, менять можно только текст")
        e = c["edit"]
        lo, hi = e.get("subs_range") or [0, 0]
        if (e["trim_start"] < lo - 0.5 or e["trim_end"] > hi + 0.5):
            lines = await self.transcriber.lines(Path(c["src_path"]), e["trim_start"], e["trim_end"])
            e["subs_range"] = [e["trim_start"], e["trim_end"]]
            self.store.update(clip_id, subs=lines, edit=e)
            c = self.store.clip(clip_id)
        src = Path(c["src_path"])
        cur = c.get("judge") or {}
        lines = [ln for ln in c["subs"] or [] if e["trim_start"] - 1 <= ln["start"] <= e["trim_end"]]
        transcript = " ".join(ln["text"] for ln in lines)
        reasons = c["reasons"] or {}
        titles = [r["title"] for r in self.store.rows("SELECT title FROM viewer_clips WHERE clip_id = ?", clip_id)]
        safety = heuristic_safety(transcript, reasons.get("chat_sample", []), titles)
        verdict = await safe_judge(self.http, self.s, src, e["trim_start"], e["trim_end"], c["login"],
                                   c.get("stream_title") or "", lines, reasons.get("chat_sample", []), titles)
        if verdict:
            safety = merge_safety(safety, verdict)
            e["blur"] = verdict.get("banners") or []
        elif cur or self.s.openrouter_api_key or self.s.openai_api_key:
            safety["categories"]["unchecked"] = {"level": 2, "evidence": "после монтажа ИИ-проверка не выполнена"}
        e["mute"] = sorted({tuple(x) for x in (e.get("mute") or [])} | {
            (ln["start"] - 0.15, ln["end"] + 0.15) for ln in lines if PROFANITY.search(ln["text"])})
        self.store.update(clip_id, edit=e, safety=safety, judge=verdict or cur or None)
        c = self.store.clip(clip_id)
        video = await render_clip(self.s, src.parent, self.spec(c))
        if e.get("blur"):
            safety["blur_check"] = await safe_verify_clean(self.http, self.s, video)
            self.store.update(clip_id, safety=safety)
        status = "published" if self.store.row(
            "SELECT 1 FROM publications WHERE clip_id = ? AND status = 'done'", clip_id) else "ready"
        if c["status"] == "rejected":
            status = "rejected"
        self.store.update(clip_id, status=status, path=str(video), version=(c["version"] or 1) + 1,
                          updated_at=time.time(), error=None)
        log.info("клип #%d перерендерен", clip_id)

    # ---- housekeeping ----------------------------------------------------------
    async def retention_loop(self):
        while True:
            try:
                await asyncio.to_thread(self.cleanup)
            except Exception:
                log.exception("cleanup failed")
            await asyncio.sleep(600)

    def cleanup(self):
        now = time.time()
        removed = 0
        for c in self.store.rows("SELECT id, status, path, src_path, created_at FROM clips WHERE path IS NOT NULL "
                                 "OR src_path IS NOT NULL"):
            age = now - c["created_at"]
            keep = self.s.retention_published_hours if c["status"] == "published" else self.s.retention_hours
            if c["path"] and age > keep * 3600:
                shutil.rmtree(Path(c["path"]).parent, ignore_errors=True)
                self.store.update(c["id"], path=None, src_path=None)
                removed += 1
            elif c["src_path"] and age > self.s.retention_source_hours * 3600:
                Path(c["src_path"]).unlink(missing_ok=True)
                (Path(c["src_path"]).parent / "source.mp4").unlink(missing_ok=True)
                self.store.update(c["id"], src_path=None)
        referenced = {Path(r["path"]).parent.name for r in self.store.rows("SELECT path FROM clips WHERE path IS NOT NULL")}
        if self.s.clips_dir.exists():
            for d in self.s.clips_dir.iterdir():
                if d.name not in referenced and now - d.stat().st_mtime > max(self.s.retention_hours, 1) * 3600:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
        if removed:
            log.info("очистка: удалено %d старых клипов", removed)
        self.store.execute("DELETE FROM features WHERE sec < ?", now - self.s.feature_days * 86400)
        self.monitor.sample_disk()

    async def run(self):
        import uvicorn

        from .admin import create_api

        self.s.data_dir.mkdir(parents=True, exist_ok=True)
        stuck = self.store.rows("SELECT id FROM clips WHERE status IN ('detected', 'rendering')")
        for r in stuck:
            self.store.update(r["id"], status="error", error="прервано перезапуском сервиса")
        if stuck:
            log.info("перезапуск: %d незавершённых клипов помечены ошибкой", len(stuck))
        if self.s.buffer_dir.exists():
            for d in self.s.buffer_dir.iterdir():
                shutil.rmtree(d, ignore_errors=True)
        server = uvicorn.Server(uvicorn.Config(create_api(self), host=self.s.admin_host, port=self.s.admin_port,
                                               log_level="warning", lifespan="off"))
        log.info("админка: http://%s:%d", self.s.admin_host, self.s.admin_port)
        workers = [self.render_worker() for _ in range(self.s.render_concurrency)]
        await asyncio.gather(server.serve(), self.discovery_loop(), self.detect_loop(), self.publisher.loop(),
                             self.publisher.views_loop(), self.monitor.loop(), self.brain.crowd_loop(), self.brain.train_loop(), self.retention_loop(), *workers)

    async def test(self, login: str, record_seconds: int, clip_seconds: int):
        """Record one channel for N seconds, then cut the last clip_seconds into a finished clip."""
        st = next(iter(await live_users(self.http, [login])), None)
        if not st:
            raise SystemExit(f"{login} is offline")
        ch = self.channels[login] = Channel(st, self)
        await asyncio.sleep(record_seconds)
        clip_id = self.manual_clip(login, clip_seconds)
        _, _, m, t = self.queue.get_nowait()
        await self.process(clip_id, m, t)
        await ch.stop()
        print(json.dumps(self.store.clip(clip_id), ensure_ascii=False, indent=2))
