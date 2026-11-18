import asyncio
import logging
import random
import re
import time
from collections import deque

log = logging.getLogger(__name__)

HYPE = re.compile(
    r"(KEKW|OMEGALUL|LUL|LULW|Pog|PogU|PogChamp|monkaS|WutFace|D:|xd|хаха|ахах|ору|жесть|имба|лол|клип|clip|\+\+\+|!!!|😂|🤣|💀|😱)",
    re.IGNORECASE,
)


class ChatMonitor:
    """Anonymous Twitch IRC reader; keeps weighted per-second activity."""

    def __init__(self, login: str, keep_seconds: int = 900):
        self.login = login
        self.keep = keep_seconds
        self.buckets: dict[int, float] = {}
        self.messages: deque[tuple[float, str]] = deque()
        self._active = True
        self._writer: asyncio.StreamWriter | None = None

    def activity(self, second: int) -> float:
        return self.buckets.get(second, 0.0)

    def messages_between(self, t0: float, t1: float, limit: int = 60) -> list[str]:
        return [m for ts, m in self.messages if t0 <= ts <= t1][:limit]

    async def stop(self):
        self._active = False
        if self._writer:
            self._writer.close()

    async def run(self):
        while self._active:
            try:
                await self._run_once()
            except Exception as e:
                log.warning("[%s] chat disconnected: %s", self.login, e)
            if self._active:
                await asyncio.sleep(3)

    async def _run_once(self):
        reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
        self._writer = writer
        nick = f"justinfan{random.randint(10000, 99999)}"
        writer.write(f"PASS SCHMOOPIIE\r\nNICK {nick}\r\nJOIN #{self.login}\r\n".encode())
        await writer.drain()
        log.info("[%s] chat connected", self.login)
        while self._active:
            raw = await asyncio.wait_for(reader.readline(), timeout=360)
            if not raw:
                raise ConnectionError("eof")
            line = raw.decode(errors="ignore").rstrip("\r\n")
            if line.startswith("PING"):
                writer.write(b"PONG :tmi.twitch.tv\r\n")
                await writer.drain()
                continue
            if " PRIVMSG " in line:
                text = line.split(" :", 1)[1] if " :" in line else ""
                self._record(time.time(), text)

    def _record(self, ts: float, text: str):
        weight = 1.0 + 0.5 * min(len(HYPE.findall(text)), 4)
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
            weight += 0.5
        sec = int(ts)
        self.buckets[sec] = self.buckets.get(sec, 0.0) + weight
        self.messages.append((ts, text))
        cutoff = ts - self.keep
        while self.messages and self.messages[0][0] < cutoff:
            self.messages.popleft()
        if len(self.buckets) > self.keep + 60:
            for k in [k for k in self.buckets if k < cutoff]:
                del self.buckets[k]
