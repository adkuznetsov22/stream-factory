import asyncio
import logging
import os
import shutil
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)


@dataclass
class Segment:
    path: Path
    wall_start: float
    wall_end: float


class Recorder:
    """streamlink | ffmpeg -f segment into a rolling on-disk buffer with wall-clock timestamps."""

    def __init__(self, login: str, s: Settings, on_segment: Callable[[str, Segment], Awaitable[None]] | None = None):
        self.login = login
        self.s = s
        self.dir = s.buffer_dir / login
        self.segments: deque[Segment] = deque()
        self.on_segment = on_segment
        self._active = True
        self._procs: list[asyncio.subprocess.Process] = []
        self._run = 0

    @property
    def latest_wall(self) -> float:
        return self.segments[-1].wall_end if self.segments else 0.0

    def range(self, t0: float, t1: float) -> list[Segment]:
        return [seg for seg in self.segments if seg.wall_end > t0 and seg.wall_start < t1]

    async def run(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        while self._active:
            try:
                await self._run_once()
            except Exception:
                log.exception("[%s] recorder crashed", self.login)
            if self._active:
                await asyncio.sleep(5)

    async def stop(self):
        self._active = False
        for p in self._procs:
            if p.returncode is None:
                p.kill()

    async def _run_once(self):
        self._run += 1
        prefix = f"r{self._run:03d}_"
        list_file = self.dir / f"{prefix}list.csv"
        read_fd, write_fd = os.pipe()
        streamlink = await asyncio.create_subprocess_exec(
            "streamlink", "--twitch-disable-ads", "--twitch-low-latency", "--hls-live-edge", "2",
            "--stream-segment-threads", "2", "-O", f"https://twitch.tv/{self.login}", self.s.quality,
            stdout=write_fd, stderr=asyncio.subprocess.DEVNULL,
        )
        ffmpeg = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
            "-f", "segment", "-segment_time", str(self.s.segment_seconds), "-reset_timestamps", "1",
            "-segment_list", list_file.name, "-segment_list_type", "csv", "-segment_list_flags", "live",
            f"{prefix}%08d.ts",
            stdin=read_fd, cwd=self.dir, stderr=asyncio.subprocess.DEVNULL,
        )
        os.close(read_fd)
        os.close(write_fd)
        self._procs = [streamlink, ffmpeg]
        log.info("[%s] recording started (run %d)", self.login, self._run)
        tail = asyncio.create_task(self._tail(list_file, ffmpeg))
        await ffmpeg.wait()
        if streamlink.returncode is None:
            streamlink.kill()
        await streamlink.wait()
        await tail
        log.info("[%s] recording stopped (run %d)", self.login, self._run)

    async def _tail(self, list_file: Path, ffmpeg: asyncio.subprocess.Process):
        pos = 0
        while True:
            done = ffmpeg.returncode is not None
            if list_file.exists():
                with list_file.open() as f:
                    f.seek(pos)
                    chunk = f.read()
                    complete = chunk[: chunk.rfind("\n") + 1]
                    pos += len(complete)
                for line in complete.splitlines():
                    await self._add(line)
            self._evict()
            if done:
                return
            await asyncio.sleep(0.3)

    async def _add(self, line: str):
        name, start, end = line.split(",")[:3]
        now = time.time()
        seg = Segment(self.dir / name, now - (float(end) - float(start)), now)
        self.segments.append(seg)
        if self.on_segment:
            asyncio.create_task(self.on_segment(self.login, seg))

    def _evict(self):
        cutoff = time.time() - self.s.buffer_seconds
        while self.segments and self.segments[0].wall_end < cutoff:
            self.segments.popleft().path.unlink(missing_ok=True)
