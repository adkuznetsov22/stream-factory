import asyncio
import logging
import os
import re
import textwrap
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Settings
from .ingest import Segment
from .titles import PROFANITY

log = logging.getLogger(__name__)

W, H = 1080, 1920
LAYOUTS = ("blur", "facecam", "full")


async def run_ffmpeg(args: list[str], cwd: Path):
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args,
        cwd=cwd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {err.decode(errors='ignore')[-800:]}")


async def grab_frame(src: Path, out: Path, width: int = 960, at: float = 0.0):
    tmp = out.with_suffix(".tmp.jpg")
    await run_ffmpeg(["-ss", f"{at:.2f}", "-i", str(src.resolve()), "-frames:v", "1", "-vf", f"scale={width}:-2",
                      "-q:v", "5", str(tmp.resolve())], out.parent)
    os.replace(tmp, out)


class Transcriber:
    def __init__(self, s: Settings):
        self.s = s
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.s.whisper_model, device=self.s.whisper_device, compute_type=self.s.whisper_compute_type
                )
        return self._model

    def words(self, wav: Path) -> list[tuple[float, float, str]]:
        with wave.open(str(wav)) as f:
            pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._load().transcribe(pcm, language="ru", word_timestamps=True, vad_filter=True, beam_size=1)
        return [(w.start, w.end, w.word.strip()) for seg in segments for w in (seg.words or []) if w.word.strip()]

    async def lines(self, src: Path, t0: float, t1: float) -> list[dict]:
        """Subtitle lines (<=3 words) for src[t0:t1], timestamps in src time."""
        wav = src.parent / "audio.wav"
        await run_ffmpeg(["-ss", f"{t0:.2f}", "-t", f"{t1 - t0:.2f}", "-i", src.name, "-vn", "-ac", "1", "-ar", "16000",
                          wav.name], src.parent)
        words = await asyncio.to_thread(self.words, wav)
        wav.unlink(missing_ok=True)
        return group_lines([(a + t0, b + t0, w) for a, b, w in words])


def group_lines(words: list[tuple[float, float, str]]) -> list[dict]:
    groups: list[list[tuple[float, float, str]]] = []
    for w in words:
        if groups and len(groups[-1]) < 3 and w[0] - groups[-1][-1][1] < 0.6:
            groups[-1].append(w)
        else:
            groups.append([w])
    return [{"start": round(g[0][0], 2), "end": round(g[-1][1] + 0.15, 2), "text": " ".join(x[2] for x in g)}
            for g in groups]


def mask_profanity(text: str) -> str:
    return PROFANITY.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text)


def _ass_time(t: float) -> str:
    t = max(t, 0.0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def build_ass(lines: list[dict], path: Path, t0: float, t1: float, margin_v: int, mask: bool):
    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,DejaVu Sans,84,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,8,60,60,{margin_v},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ln in lines:
        if ln["end"] <= t0 or ln["start"] >= t1 or not ln["text"].strip():
            continue
        text = mask_profanity(ln["text"]) if mask else ln["text"]
        text = text.upper().replace("{", "(").replace("}", ")").replace("\n", " ")
        out.append(f"Dialogue: 0,{_ass_time(ln['start'] - t0)},{_ass_time(ln['end'] - t0)},Sub,,0,0,0,,{text}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


async def cut_source(segments: list[Segment], clip_dir: Path) -> tuple[Path, float, float]:
    """Concatenate buffer segments into clip_dir/src.ts; returns (path, wall-clock start, duration)."""
    clip_dir.mkdir(parents=True, exist_ok=True)
    (clip_dir / "concat.txt").write_text("".join(f"file '{seg.path.resolve()}'\n" for seg in segments))
    await run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "src.ts"], clip_dir)
    (clip_dir / "concat.txt").unlink(missing_ok=True)
    return clip_dir / "src.ts", segments[0].wall_start, segments[-1].wall_end - segments[0].wall_start


@dataclass
class RenderSpec:
    trim_start: float
    trim_end: float
    overlay: str
    credit: str
    layout: str = "blur"
    facecam: list[float] | None = None
    subtitles: bool = True
    lines: list[dict] = field(default_factory=list)
    blur: list[list[float]] = field(default_factory=list)
    mute: list[list[float]] = field(default_factory=list)


def _blur_prefix(fps: int, boxes: list[list[float]]) -> str:
    """Blur normalized [x, y, w, h] regions of the source frame (ads, promo codes) before layout."""
    if not boxes:
        return f"[0:v]fps={fps},"
    out = f"[0:v]fps={fps}[s0];"
    for i, (x, y, w, h) in enumerate(boxes):
        out += (f"[s{i}]split=2[m{i}][c{i}];[c{i}]crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},boxblur=25:4[b{i}];"
                f"[m{i}][b{i}]overlay=main_w*{x:.4f}:main_h*{y:.4f}[s{i + 1}];")
    return out + f"[s{len(boxes)}]"


def _video_filter(s: Settings, spec: RenderSpec, clip_dir: Path) -> tuple[str, int]:
    fps = s.output_fps
    pre = _blur_prefix(fps, spec.blur)
    cam = spec.facecam if spec.layout == "facecam" and spec.facecam else None
    if cam:
        x, y, w, h = cam
        chain = (
            f"{pre}split=2[a][b];"
            f"[a]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={W}:640:force_original_aspect_ratio=increase,crop={W}:640[cam];"
            f"[b]scale=-2:1280,crop={W}:1280[game];[cam][game]vstack[base];"
        )
        title_y, sub_margin = H - 360, 560
    elif spec.layout == "full":
        chain = f"{pre}scale=-2:{H},crop={W}:{H}[base];"
        title_y, sub_margin = 220, 1150
    else:
        gh = s.gameplay_height
        chain = (
            f"{pre}split=2[a][b];"
            f"[a]scale=-2:480,crop=270:480,boxblur=10:1,scale={W}:{H},eq=brightness=-0.12[bg];"
            f"[b]scale=-2:{gh},crop={W}:{gh}[fg];[bg][fg]overlay=0:(H-h)/2[base];"
        )
        title_y, sub_margin = max((H - gh) // 2 - 330, 60), (H - gh) // 2 + gh + 40
    font = s.font_file
    filters = []
    if spec.overlay.strip():
        text = re.sub(r"[^\w\s.,!?…:;«»\"'()+%№-]", "", spec.overlay).strip()
        lines = textwrap.wrap(text.upper(), 18, break_long_words=False)[:3] or [""]
        (clip_dir / "title.txt").write_text("\n".join(lines), encoding="utf-8")
        size = min(68, int(960 / (0.66 * max(len(x) for x in lines))))
        filters.append(f"drawtext=fontfile={font}:textfile=title.txt:fontsize={size}:fontcolor=white:line_spacing=12:"
                       f"box=1:boxcolor=black@0.6:boxborderw=26:x=(w-text_w)/2:y={title_y}")
    (clip_dir / "credit.txt").write_text(spec.credit, encoding="utf-8")
    filters.append(f"drawtext=fontfile={font}:textfile=credit.txt:fontsize=40:fontcolor=white@0.85:"
                   f"shadowcolor=black:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-150")
    if spec.subtitles and spec.lines:
        build_ass(spec.lines, clip_dir / "subs.ass", spec.trim_start, spec.trim_end, sub_margin, s.mask_subtitles)
        filters.append(f"ass=subs.ass:fontsdir={Path(font).parent}")
    return chain + "[base]" + ",".join(filters) + "[v]", sub_margin


def _encoder_args(s: Settings) -> list[str]:
    if "nvenc" in s.video_encoder:
        return ["-c:v", s.video_encoder, "-preset", "p4", "-cq", "23", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]


async def render_clip(s: Settings, clip_dir: Path, spec: RenderSpec) -> Path:
    vf, _ = _video_filter(s, spec, clip_dir)
    await run_ffmpeg(
        ["-ss", f"{spec.trim_start:.2f}", "-t", f"{spec.trim_end - spec.trim_start:.2f}", "-i", "src.ts",
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0?", *_encoder_args(s), "-pix_fmt", "yuv420p",
         *(["-af", ",".join(f"volume=enable='between(t,{a - spec.trim_start:.2f},{b - spec.trim_start:.2f})':volume=0"
                           for a, b in spec.mute)] if spec.mute else []),
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "clip.tmp.mp4"],
        clip_dir,
    )
    os.replace(clip_dir / "clip.tmp.mp4", clip_dir / "clip.mp4")
    await grab_frame(clip_dir / "clip.mp4", clip_dir / "thumb.jpg", width=360, at=1.0)
    return clip_dir / "clip.mp4"
