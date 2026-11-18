import statistics
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from .chat import HYPE, ChatMonitor
from .config import Settings


@dataclass
class Moment:
    login: str
    onset: float
    peak: float
    score: float
    start: float
    end: float
    chat: list[str] = field(default_factory=list)
    reasons: dict = field(default_factory=dict)


def _robust_z(value: float, history: list[float], floor: float) -> float:
    if len(history) < 10:
        return 0.0
    med = statistics.median(history)
    mad = statistics.median(abs(x - med) for x in history) * 1.4826
    return (value - med) / max(mad, floor)


def top_emotes(messages: list[str], n: int = 5) -> list[list]:
    c = Counter(m.group(0).upper() if m.group(0).isascii() else m.group(0).lower()
                for msg in messages for m in HYPE.finditer(msg))
    return [[k, v] for k, v in c.most_common(n)]


class Detector:
    """Fuses chat burst and audio loudness into a moment score; emits one Moment per burst."""

    WINDOW = 5
    HISTORY = 600

    def __init__(self, login: str, chat: ChatMonitor, s: Settings, sensitivity: Callable[[], float] = lambda: 1.0):
        self.login = login
        self.chat = chat
        self.s = s
        self.sensitivity = sensitivity
        self.audio: dict[int, float] = {}
        self.started = time.time()
        self.last_trigger = 0.0
        self._burst: dict | None = None
        self.last_score = 0.0
        self.last_parts = (0.0, 0.0)
        # per-second (ts, score, z_chat, z_audio) for the live graph
        self.history: deque[tuple[int, float, float, float]] = deque(maxlen=self.HISTORY)
        self.moments: deque[tuple[float, float]] = deque(maxlen=50)

    @property
    def threshold(self) -> float:
        return self.s.trigger_score / max(self.sensitivity() or 1.0, 0.1)

    def add_audio(self, wall_start: float, levels: list[float]):
        for i, db in enumerate(levels):
            self.audio[int(wall_start) + i] = db
        cutoff = int(time.time()) - self.s.baseline_seconds - 60
        if len(self.audio) > self.s.baseline_seconds + 120:
            for k in [k for k in self.audio if k < cutoff]:
                del self.audio[k]

    def _chat_rate(self, end_sec: int) -> float:
        return sum(self.chat.activity(t) for t in range(end_sec - self.WINDOW, end_sec)) / self.WINDOW

    def parts_at(self, now_sec: int) -> tuple[float, float]:
        base_start = max(now_sec - self.s.baseline_seconds, int(self.started) + self.WINDOW)
        base = range(base_start, now_sec - self.WINDOW, self.WINDOW)
        chat_hist = [self._chat_rate(t) for t in base]
        z_chat = _robust_z(self._chat_rate(now_sec), chat_hist, floor=0.5)
        # Audio lags chat by the HLS delay, so look at a wider recent window.
        recent_audio = [self.audio[t] for t in range(now_sec - 15, now_sec) if t in self.audio]
        audio_hist = [v for t, v in self.audio.items() if base_start <= t < now_sec - 15]
        z_audio = _robust_z(max(recent_audio), audio_hist, floor=2.0) if recent_audio else 0.0
        return z_chat, 0.5 * max(z_audio, 0.0)

    def score_at(self, now_sec: int) -> float:
        return sum(self.parts_at(now_sec))

    def tick(self, now: float | None = None) -> Moment | None:
        now = now or time.time()
        sec = int(now)
        warm = now - self.started >= self.s.warmup_seconds
        z_chat, z_audio = self.parts_at(sec) if warm else (0.0, 0.0)
        score = z_chat + z_audio
        self.last_score, self.last_parts = score, (z_chat, z_audio)
        self.history.append((sec, round(score, 2), round(z_chat, 2), round(z_audio, 2)))
        if not warm:
            return None
        thr = self.threshold
        if self._burst is None:
            if score >= thr and now - self.last_trigger >= self.s.cooldown:
                self._burst = {"onset": sec - self.WINDOW, "peak": sec, "score": score, "since": now,
                               "z_chat": z_chat, "z_audio": z_audio}
            return None
        b = self._burst
        if score > b["score"]:
            b.update(score=score, peak=sec, z_chat=z_chat, z_audio=z_audio)
        if score < thr * 0.6 or now - b["since"] > 20:
            self._burst = None
            self.last_trigger = now
            anchor = b["onset"] - self.s.reaction_delay
            start = anchor - self.s.clip_before
            end = max(anchor + self.s.clip_after, b["peak"] - self.s.reaction_delay + 3)
            chat = self.chat.messages_between(b["onset"], b["peak"] + 5)
            self.moments.append((b["onset"], round(b["score"], 2)))
            return Moment(
                login=self.login, onset=b["onset"], peak=b["peak"], score=round(b["score"], 2),
                start=start, end=end, chat=chat,
                reasons={"chat": round(b["z_chat"], 2), "audio": round(b["z_audio"], 2), "threshold": round(thr, 2),
                         "chat_msgs": len(self.chat.messages_between(b["onset"], b["peak"] + 5, limit=10_000)),
                         "emotes": top_emotes(chat)},
            )
        return None
