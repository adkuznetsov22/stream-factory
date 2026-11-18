import asyncio
import logging
import secrets
import shutil
import statistics
import time
from collections import deque
from typing import TYPE_CHECKING

from . import publish

if TYPE_CHECKING:
    from .app import App

log = logging.getLogger(__name__)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(int(len(values) * q), len(values) - 1)], 1)


class Monitor:
    """Health checks and owner alerts through the Telegram bot."""

    def __init__(self, app: "App"):
        self.app = app
        self.sent: dict[str, float] = {}
        self.disk_samples: deque[tuple[float, int]] = deque(maxlen=200)
        self.data_size = 0
        self.link_code: str | None = None
        self.link_bot: str | None = None

    def bot(self) -> dict | None:
        return next((t["config"] for t in self.app.store.targets()
                     if t["kind"] == "telegram" and (t["config"] or {}).get("bot_token")), None)

    def alert(self, key: str, text: str, every: float = 1800):
        if not self.app.s.alerts_chat_id or time.time() - self.sent.get(key, 0) < every:
            return
        self.sent[key] = time.time()
        asyncio.get_event_loop().create_task(self._send(text))

    async def _send(self, text: str):
        cfg = self.bot()
        if not cfg:
            return
        try:
            await publish._tg(self.app.http, cfg, "sendMessage",
                              data={"chat_id": self.app.s.alerts_chat_id, "text": f"⚠️ Live Clipper\n{text}"}, timeout=15)
        except Exception as e:
            log.warning("алерт не отправлен: %s", e)

    async def start_link(self) -> dict:
        cfg = self.bot()
        if not cfg:
            raise RuntimeError("сначала добавьте площадку Telegram с токеном бота")
        me = await publish._tg(self.app.http, cfg, "getMe", timeout=15)
        self.link_code, self.link_bot = secrets.token_hex(4), me["username"]
        asyncio.create_task(self._wait_link(cfg, self.link_code))
        return {"bot": me["username"], "code": self.link_code, "url": f"https://t.me/{me['username']}?start={self.link_code}"}

    async def _wait_link(self, cfg: dict, code: str):
        offset, deadline = 0, time.time() + 600
        while time.time() < deadline and self.link_code == code:
            try:
                ups = await publish._tg(self.app.http, cfg, "getUpdates", data={"offset": offset, "timeout": 20},
                                        timeout=30)
            except Exception:
                await asyncio.sleep(5)
                continue
            for u in ups:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                if msg.get("text", "").strip() == f"/start {code}":
                    self.app.apply_settings({"alerts_chat_id": str(msg["chat"]["id"])})
                    self.link_code = None
                    await self._send("Алерты подключены: сюда будут приходить ошибки публикации, записи и диска.")
                    log.info("алерты привязаны к Telegram %s", msg["chat"].get("username") or msg["chat"]["id"])
                    return

    def sample_disk(self):
        self.data_size = sum(f.stat().st_size for f in self.app.s.data_dir.rglob("*") if f.is_file())
        self.disk_samples.append((time.time(), shutil.disk_usage(self.app.s.data_dir).free))

    def disk(self) -> dict:
        du = shutil.disk_usage(self.app.s.data_dir)
        hours_left = None
        if len(self.disk_samples) >= 2:
            (t0, f0), (t1, f1) = self.disk_samples[0], self.disk_samples[-1]
            rate = (f0 - f1) / max(t1 - t0, 1)
            if rate > 0:
                hours_left = round(du.free / rate / 3600, 1)
        return {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                "data_gb": round(self.data_size / 1e9, 2), "hours_left": hours_left}

    async def loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                now = time.time()
                for login, ch in self.app.channels.items():
                    if now - ch.started > 120 and now - ch.recorder.latest_wall > 90:
                        self.alert(f"rec:{login}", f"Запись {login} не идёт больше 90 с (переподключаюсь)")
                d = self.disk()
                if d["free_gb"] < 10:
                    self.alert("disk", f"Мало места: свободно {d['free_gb']} ГБ")
            except Exception:
                log.exception("monitor failed")

    def health(self) -> dict:
        now = time.time()
        st = self.app.store
        clips = st.rows("SELECT timings FROM clips WHERE created_at > ? AND timings IS NOT NULL", now - 86400)
        rendered = [c["timings"]["rendered"] for c in clips if isinstance(c["timings"], dict) and "rendered" in c["timings"]]
        posted = [r["d"] for r in st.rows(
            "SELECT p.done_at - c.moment_end AS d FROM publications p JOIN clips c ON c.id = p.clip_id "
            "WHERE p.status = 'done' AND p.done_at > ?", now - 86400)]
        errors = st.rows(
            "SELECT 'публикация' AS kind, t.name AS place, p.error AS error, COUNT(*) AS n, MAX(p.done_at) AS last "
            "FROM publications p JOIN targets t ON t.id = p.target_id WHERE p.status = 'error' AND p.done_at > ? "
            "GROUP BY t.name, p.error UNION ALL "
            "SELECT 'рендер', login, error, COUNT(*), MAX(created_at) FROM clips WHERE status = 'error' AND created_at > ? "
            "GROUP BY login, error ORDER BY last DESC LIMIT 30", now - 86400, now - 86400)
        return {
            "latency": {"render_p50": _pct(rendered, 0.5), "render_p90": _pct(rendered, 0.9),
                        "post_p50": _pct(posted, 0.5), "post_p90": _pct(posted, 0.9),
                        "render_mean": round(statistics.mean(rendered), 1) if rendered else None, "count": len(rendered)},
            "recorders": [{"login": login, "runs": ch.recorder._run, "segment_age": round(now - ch.recorder.latest_wall, 1)
                           if ch.recorder.latest_wall else None, "chat": ch.chat._writer is not None and not ch.chat._writer.is_closing(),
                           "since": ch.started} for login, ch in self.app.channels.items()],
            "errors": errors, "disk": self.disk(), "alerts_chat_id": self.app.s.alerts_chat_id,
            "alerts_linking": bool(self.link_code), "render_queue": self.app.queue.qsize(),
        }
