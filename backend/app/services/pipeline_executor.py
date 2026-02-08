"""
Pipeline Executor Service

Executes preset steps dynamically for publish tasks:
- Registers handlers for each tool_id
- Passes context between steps
- Tracks execution status and timing
- Handles errors gracefully
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx

logger = logging.getLogger("pipeline")


class StepContext:
    """Context passed between pipeline steps."""
    
    def __init__(
        self,
        task_id: int,
        task_dir: Path,
        log_cb: Callable[[str], None],
    ):
        self.task_id = task_id
        self.task_dir = task_dir
        self.log = log_cb
        
        # Input/output paths
        self.raw_path = task_dir / "raw.mp4"
        self.ready_path = task_dir / "ready.mp4"
        self.final_path = task_dir / "final.mp4"
        self.thumb_path = task_dir / "thumb.jpg"
        self.preview_path = task_dir / "preview.mp4"
        self.probe_path = task_dir / "probe.json"
        self.captions_path = task_dir / "captions.srt"
        
        # Current working video (changes as steps process)
        self.current_video: Path | None = None
        
        # Metadata
        self.probe_data: dict = {}
        self.caption_text: str | None = None
        self.download_url: str | None = None
        self.permalink: str | None = None
        
        # Generation metadata (for GENERATE origin candidates)
        self.candidate_meta: dict = {}
        self.brief_data: dict = {}
        
        # Project policy (required transformations)
        self.policy: dict = {}
        
        # Export profile (platform-specific encoding params)
        self.export_profile: dict = {}
        
        # Publishing context (for P01_PUBLISH)
        self.session: Any = None          # AsyncSession — set by task_processor
        self.publish_task: Any = None     # PublishTask ORM object
        self.platform: str | None = None
        self.destination_account_id: int | None = None
        
        # Step outputs accumulator
        self.outputs: dict[str, Any] = {}
    
    def get_input_video(self) -> Path:
        """Get current input video for next step."""
        return self.current_video or self.raw_path
    
    def set_output_video(self, path: Path):
        """Set output video as input for next step."""
        self.current_video = path


StepHandler = Callable[[StepContext, dict], Awaitable[dict]]


class PipelineExecutor:
    """Executes pipeline steps for video processing."""
    
    _handlers: dict[str, StepHandler] = {}
    
    @classmethod
    def register(cls, tool_id: str):
        """Decorator to register a step handler."""
        def decorator(func: StepHandler) -> StepHandler:
            cls._handlers[tool_id] = func
            return func
        return decorator
    
    @classmethod
    def get_handler(cls, tool_id: str) -> StepHandler | None:
        """Get handler for a tool_id."""
        return cls._handlers.get(tool_id)
    
    @classmethod
    def list_handlers(cls) -> list[str]:
        """List all registered handlers."""
        return list(cls._handlers.keys())
    
    def __init__(self, context: StepContext):
        self.context = context
        self.steps_debug: list[dict] = []
    
    async def execute_steps(self, steps: list[dict]) -> dict:
        """
        Execute a list of preset steps.
        
        Args:
            steps: List of step dicts with tool_id, params, enabled, etc.
        
        Returns:
            Dict with execution results
        """
        results = {
            "success": True,
            "steps_executed": 0,
            "steps_skipped": 0,
            "steps_failed": 0,
            "error": None,
            "steps": [],
        }
        
        for step in steps:
            step_id = step.get("id")
            tool_id = step.get("tool_id")
            enabled = step.get("enabled", True)
            params = step.get("params", {})
            name = step.get("name", tool_id)
            
            step_result = {
                "id": step_id,
                "tool_id": tool_id,
                "name": name,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "outputs": {},
                "error": None,
            }
            self.steps_debug.append(step_result)
            
            if not enabled:
                step_result["status"] = "skipped"
                results["steps_skipped"] += 1
                results["steps"].append(step_result)
                continue
            
            handler = self.get_handler(tool_id)
            if not handler:
                self.context.log(f"[{tool_id}] No handler registered, skipping")
                step_result["status"] = "skipped"
                step_result["error"] = "No handler registered"
                results["steps_skipped"] += 1
                results["steps"].append(step_result)
                continue
            
            # Execute step
            step_result["status"] = "processing"
            step_result["started_at"] = datetime.now(timezone.utc).isoformat()
            t_start = datetime.now(timezone.utc)
            
            try:
                self.context.log(f"[{tool_id}] Starting step: {name}")
                outputs = await handler(self.context, params)
                
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                step_result["status"] = "ok"
                step_result["finished_at"] = datetime.now(timezone.utc).isoformat()
                step_result["duration_ms"] = duration_ms
                step_result["outputs"] = outputs
                
                # Store outputs in context
                self.context.outputs[tool_id] = outputs
                
                results["steps_executed"] += 1
                self.context.log(f"[{tool_id}] Completed in {duration_ms}ms")
                
            except Exception as e:
                duration_ms = int((datetime.now(timezone.utc) - t_start).total_seconds() * 1000)
                step_result["status"] = "error"
                step_result["finished_at"] = datetime.now(timezone.utc).isoformat()
                step_result["duration_ms"] = duration_ms
                step_result["error"] = str(e)
                
                results["steps_failed"] += 1
                results["success"] = False
                results["error"] = f"Step {tool_id} failed: {e}"
                
                self.context.log(f"[{tool_id}] Error: {e}")
                
                # Stop pipeline on error
                break
            
            results["steps"].append(step_result)
        
        return results
    
    def get_debug_info(self) -> dict:
        """Get debug info for all steps."""
        return {"steps": self.steps_debug}


# ============== Utility functions ==============

async def run_cmd(cmd: list[str], log_cb: Callable[[str], None]) -> tuple[str, str]:
    """Run a command and return stdout/stderr."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    stdout_dec = stdout.decode(errors="ignore") if stdout else ""
    stderr_dec = stderr.decode(errors="ignore") if stderr else ""
    
    if stdout_dec:
        log_cb(stdout_dec[:1000])
    if stderr_dec:
        log_cb(stderr_dec[:1000])
    
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {proc.returncode}: {' '.join(cmd[:5])}...; "
            f"stderr: {stderr_dec[-400:]}"
        )
    return stdout_dec, stderr_dec


async def download_file(
    url: str,
    dest: Path,
    log_cb: Callable[[str], None],
    retries: int = 2,
    timeout: float = 60.0,
) -> None:
    """Download a file with retries."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    min_size = 200 * 1024  # 200KB
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
        "Accept": "*/*",
    }
    
    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            log_cb(f"Download attempt {attempt}: {url[:100]}...")
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
                async with client.stream("GET", url) as resp:
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Download failed with status {resp.status_code}")
                    
                    with dest.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
            
            size = dest.stat().st_size
            log_cb(f"Downloaded {size} bytes to {dest.name}")
            
            if size < min_size:
                raise RuntimeError(f"File too small: {size} bytes")
            
            # Validate it's a video
            with dest.open("rb") as f:
                head = f.read(2048)
                if b"<html" in head.lower() or b"<!doctype" in head.lower():
                    raise RuntimeError("Downloaded HTML instead of video")
                if b"ftyp" not in head and b"moov" not in head:
                    log_cb("Warning: No ftyp/moov marker, may not be valid video")
            
            return
            
        except Exception as e:
            last_exc = e
            if dest.exists():
                dest.unlink()
            log_cb(f"Download failed: {e}")
            if attempt <= retries:
                await asyncio.sleep(1.5 * attempt)
    
    raise RuntimeError(f"Download failed after {retries + 1} attempts: {last_exc}")


async def download_via_ytdlp(
    url: str,
    dest: Path,
    log_cb: Callable[[str], None],
) -> None:
    """Download video using yt-dlp."""
    cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",
        "-o", str(dest),
        "--no-playlist",
        "--no-warnings",
        url,
    ]
    log_cb(f"yt-dlp download: {url[:80]}...")
    await run_cmd(cmd, log_cb)
    
    if not dest.exists():
        raise RuntimeError("yt-dlp did not create output file")


# ============== Step Handlers ==============

@PipelineExecutor.register("T01_DOWNLOAD")
async def handle_download(ctx: StepContext, params: dict) -> dict:
    """Download source video."""
    if not ctx.download_url:
        raise RuntimeError("No download_url provided")
    
    try:
        await download_file(ctx.download_url, ctx.raw_path, ctx.log)
    except Exception as e:
        # Fallback to yt-dlp
        if ctx.permalink:
            ctx.log(f"Direct download failed ({e}), trying yt-dlp")
            await download_via_ytdlp(ctx.permalink, ctx.raw_path, ctx.log)
        else:
            raise
    
    ctx.current_video = ctx.raw_path
    return {"path": str(ctx.raw_path), "size": ctx.raw_path.stat().st_size}


@PipelineExecutor.register("T02_PROBE")
async def handle_probe(ctx: StepContext, params: dict) -> dict:
    """Probe video metadata with ffprobe."""
    input_path = ctx.get_input_video()
    
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(input_path),
    ]
    
    stdout, _ = await run_cmd(cmd, ctx.log)
    probe_data = json.loads(stdout) if stdout else {}
    
    # Save probe data
    ctx.probe_data = probe_data
    ctx.probe_path.write_text(json.dumps(probe_data, indent=2))
    
    # Extract key info
    duration = None
    width = None
    height = None
    
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            duration = stream.get("duration")
            break
    
    if not duration:
        duration = probe_data.get("format", {}).get("duration")
    
    return {
        "duration": float(duration) if duration else None,
        "width": width,
        "height": height,
        "probe_path": str(ctx.probe_path),
    }


@PipelineExecutor.register("T05_THUMBNAIL")
async def handle_thumbnail(ctx: StepContext, params: dict) -> dict:
    """Extract thumbnail from video."""
    input_path = ctx.get_input_video()
    timestamp = params.get("timestamp", "00:00:01")
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", timestamp,
        "-i", str(input_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(ctx.thumb_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    return {"path": str(ctx.thumb_path)}


@PipelineExecutor.register("T04_CROP_RESIZE")
async def handle_crop_resize(ctx: StepContext, params: dict) -> dict:
    """Crop and resize video to vertical format (9:16). Respects export_profile."""
    input_path = ctx.get_input_video()
    output_path = ctx.ready_path
    
    ep = ctx.export_profile
    width = params.get("width") or ep.get("width") or 1080
    height = params.get("height") or ep.get("height") or 1920
    crf = params.get("crf", 20)
    audio_bitrate = ep.get("audio_bitrate") or "128k"
    
    vf = f"scale='if(gte(a,{width}/{height}),-2,{width})':'if(gte(a,{width}/{height}),{height},-2)',crop={width}:{height},setsar=1"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path), "size": output_path.stat().st_size}


@PipelineExecutor.register("T05_PREVIEW")
async def handle_preview(ctx: StepContext, params: dict) -> dict:
    """Create short preview clip (legacy, use T05_THUMBNAIL)."""
    input_path = ctx.get_input_video()
    duration = params.get("duration", 5)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-t", str(duration),
        "-an",
        "-vf", "scale=480:-2",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        str(ctx.preview_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    return {"path": str(ctx.preview_path)}


@PipelineExecutor.register("T10_WATERMARK_OLD")
async def handle_watermark_old(ctx: StepContext, params: dict) -> dict:
    """Add watermark overlay to video (legacy, use T16_WATERMARK)."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "watermarked.mp4"
    
    text = params.get("text", "@channel")
    position = params.get("position", "bottom")  # top, bottom, center
    fontsize = params.get("fontsize", 24)
    
    y_pos = {
        "top": "50",
        "center": "(h-text_h)/2",
        "bottom": "h-th-50",
    }.get(position, "h-th-50")
    
    vf = f"drawtext=text='{text}':fontsize={fontsize}:fontcolor=white:x=(w-text_w)/2:y={y_pos}:shadowcolor=black:shadowx=2:shadowy=2"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "copy",
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path)}


@PipelineExecutor.register("T14_BURN_CAPTIONS")
async def handle_burn_captions(ctx: StepContext, params: dict) -> dict:
    """Burn captions/subtitles into video.

    Параметры (params → export_profile.safe_area → дефолт):
        bottom_margin  – отступ снизу в px (safe_area.bottom)
        top_margin     – отступ сверху в px (safe_area.top)
        font_size      – размер шрифта (36)
        max_lines      – макс. строк на экране (2)
        line_spacing    – межстрочный интервал в px (8)
        outline        – толщина обводки (2)
    """
    input_path = ctx.get_input_video()
    output_path = ctx.final_path

    ep = ctx.export_profile
    safe = ep.get("safe_area", {})

    text = ctx.caption_text or params.get("text", "")

    # ── Параметры с каскадом: params → safe_area → дефолт ──
    bottom_margin = params.get("bottom_margin") or safe.get("bottom") or 50
    top_margin = params.get("top_margin") or safe.get("top") or 120
    margin_l = params.get("margin_l") or safe.get("left") or 30
    margin_r = params.get("margin_r") or safe.get("right") or 30
    font_size = params.get("font_size") or params.get("fontsize") or 36
    max_lines = params.get("max_lines", 2)
    line_spacing = params.get("line_spacing", 8)
    outline = params.get("outline", 2)

    if not text:
        ctx.log("No caption text, skipping burn")
        return {"skipped": True}

    # Если есть готовый SRT/ASS — используем его, иначе создаём простой
    captions_file = ctx.captions_path
    existing_captions = ctx.outputs.get("captions_path")
    if existing_captions and Path(existing_captions).exists():
        captions_file = Path(existing_captions)
    else:
        srt_content = f"1\n00:00:00,000 --> 00:00:05,000\n{text}\n"
        captions_file.write_text(srt_content, encoding="utf-8")

    # force_style для ASS/SRT рендера через libass
    style_parts = [
        f"FontSize={font_size}",
        f"Outline={outline}",
        f"MarginV={bottom_margin}",
        f"MarginL={margin_l}",
        f"MarginR={margin_r}",
        f"Spacing={line_spacing}",
    ]
    # WrapStyle=0 — автоперенос по словам с учётом max_lines
    # Alignment=2 — центр-низ
    style_parts.append("WrapStyle=0")
    style_parts.append("Alignment=2")

    vf = f"subtitles={captions_file}:force_style='{','.join(style_parts)}'"

    audio_bitrate = ep.get("audio_bitrate") or "128k"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        str(output_path),
    ]

    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)

    ctx.log(
        f"[T14_BURN_CAPTIONS] font_size={font_size}, bottom_margin={bottom_margin}, "
        f"top_margin={top_margin}, max_lines={max_lines}, line_spacing={line_spacing}"
    )

    return {
        "path": str(output_path),
        "captions_path": str(captions_file),
        "font_size": font_size,
        "bottom_margin": bottom_margin,
        "top_margin": top_margin,
        "max_lines": max_lines,
        "line_spacing": line_spacing,
    }


@PipelineExecutor.register("T20_SPEED")
async def handle_speed(ctx: StepContext, params: dict) -> dict:
    """Change video speed."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "speed.mp4"
    
    speed = params.get("speed", 1.0)
    if speed == 1.0:
        return {"skipped": True}
    
    # Video speed: setpts=PTS/speed, Audio: atempo=speed
    video_filter = f"setpts=PTS/{speed}"
    audio_filter = f"atempo={speed}" if 0.5 <= speed <= 2.0 else f"atempo={min(max(speed, 0.5), 2.0)}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", video_filter,
        "-af", audio_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path), "speed": speed}


@PipelineExecutor.register("T21_TRIM")
async def handle_trim(ctx: StepContext, params: dict) -> dict:
    """Trim video to specified duration."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "trimmed.mp4"
    
    start = params.get("start", 0)
    duration = params.get("duration")
    end = params.get("end")
    
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    
    if start:
        cmd.extend(["-ss", str(start)])
    if duration:
        cmd.extend(["-t", str(duration)])
    elif end:
        cmd.extend(["-to", str(end)])
    
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        str(output_path),
    ])
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path)}


@PipelineExecutor.register("T30_COPY_READY")
async def handle_copy_ready(ctx: StepContext, params: dict) -> dict:
    """Copy current video to ready.mp4 without re-encoding."""
    input_path = ctx.get_input_video()
    
    if input_path == ctx.ready_path:
        return {"skipped": True, "reason": "already at ready_path"}
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c", "copy",
        str(ctx.ready_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(ctx.ready_path)
    
    return {"path": str(ctx.ready_path)}


# ============== New Tool Handlers ==============

@PipelineExecutor.register("T03_NORMALIZE")
async def handle_normalize(ctx: StepContext, params: dict) -> dict:
    """Normalize video: fps, codec, color space. Respects export_profile."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "normalized.mp4"
    
    ep = ctx.export_profile
    target_fps = params.get("target_fps") or ep.get("fps") or 30
    codec = params.get("codec") or ep.get("codec") or "h264"
    crf = params.get("crf", 23)
    audio_bitrate = ep.get("audio_bitrate") or "192k"
    audio_sample_rate = ep.get("audio_sample_rate") or 48000
    pix_fmt = ep.get("extra", {}).get("pixel_format") or "yuv420p"
    
    codec_lib = "libx264" if codec == "h264" else "libx265"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-r", str(target_fps),
        "-c:v", codec_lib,
        "-preset", "medium",
        "-crf", str(crf),
        "-pix_fmt", pix_fmt,
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", str(audio_sample_rate),
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path), "fps": target_fps, "codec": codec}


@PipelineExecutor.register("T07_EXTRACT_AUDIO")
async def handle_extract_audio(ctx: StepContext, params: dict) -> dict:
    """Extract audio track from video."""
    input_path = ctx.get_input_video()
    audio_format = params.get("format", "wav")
    sample_rate = params.get("sample_rate", 44100)
    
    ext = audio_format if audio_format in ["wav", "mp3", "aac"] else "wav"
    output_path = ctx.task_dir / f"audio.{ext}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-ar", str(sample_rate),
    ]
    
    if ext == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif ext == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    
    cmd.append(str(output_path))
    
    await run_cmd(cmd, ctx.log)
    ctx.outputs["audio_path"] = str(output_path)
    
    return {"path": str(output_path), "format": ext, "sample_rate": sample_rate}


@PipelineExecutor.register("T06_BG_MUSIC")
async def handle_bg_music(ctx: StepContext, params: dict) -> dict:
    """Add background music to video."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "with_music.mp4"
    
    music_path = params.get("music_path")
    volume = params.get("volume", 0.3)
    fade_in = params.get("fade_in", 2)
    fade_out = params.get("fade_out", 2)
    
    if not music_path:
        ctx.log("No music_path provided, skipping background music")
        return {"skipped": True}
    
    # Get video duration for fade out timing
    duration = ctx.probe_data.get("format", {}).get("duration")
    dur_float = float(duration) if duration else 60
    
    # Build audio filter for music with fade and volume
    music_filter = f"volume={volume}"
    if fade_in > 0:
        music_filter = f"afade=t=in:d={fade_in},{music_filter}"
    if fade_out > 0 and dur_float > fade_out:
        music_filter = f"{music_filter},afade=t=out:st={dur_float - fade_out}:d={fade_out}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-i", str(music_path),
        "-filter_complex",
        f"[1:a]{music_filter}[music];[0:a][music]amix=inputs=2:duration=first[out]",
        "-map", "0:v:0",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path), "volume": volume}


@PipelineExecutor.register("T12_REPLACE_AUDIO")
async def handle_replace_audio(ctx: StepContext, params: dict) -> dict:
    """Replace audio track in video."""
    input_path = ctx.get_input_video()
    audio_path = params.get("audio_path") or ctx.outputs.get("mixed_audio") or ctx.outputs.get("audio_path")
    output_path = ctx.task_dir / "replaced_audio.mp4"
    
    if not audio_path:
        ctx.log("No audio path provided, keeping original audio")
        return {"skipped": True}
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path)}


@PipelineExecutor.register("T15_EFFECTS")
async def handle_effects(ctx: StepContext, params: dict) -> dict:
    """Apply visual effects for uniqueness."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "effects.mp4"
    
    mirror = params.get("mirror", False)
    zoom_max = params.get("zoom_max", 1.0)
    color_shift = params.get("color_shift", 0)
    grain = params.get("grain", 0)
    strip_metadata = params.get("strip_metadata", True)
    
    filters = []
    
    # Mirror (horizontal flip)
    if mirror:
        filters.append("hflip")
    
    # Random zoom (slight)
    if zoom_max > 1.0:
        zoom_val = zoom_max
        filters.append(f"scale=iw*{zoom_val}:ih*{zoom_val},crop=iw/{zoom_val}:ih/{zoom_val}")
    
    # Color shift (hue rotation)
    if color_shift != 0:
        filters.append(f"hue=h={color_shift}")
    
    # Film grain
    if grain > 0:
        filters.append(f"noise=c0s={int(grain * 20)}:c0f=t+u")
    
    vf = ",".join(filters) if filters else None
    
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    
    if vf:
        cmd.extend(["-vf", vf])
    
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "copy",
    ])
    
    if strip_metadata:
        cmd.extend(["-map_metadata", "-1"])
    
    cmd.append(str(output_path))
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {
        "path": str(output_path),
        "effects_applied": {
            "mirror": mirror,
            "zoom": zoom_max,
            "color_shift": color_shift,
            "grain": grain,
        }
    }


@PipelineExecutor.register("T16_WATERMARK")
async def handle_watermark_new(ctx: StepContext, params: dict) -> dict:
    """Add watermark (text or image) to video."""
    input_path = ctx.get_input_video()
    output_path = ctx.task_dir / "watermarked.mp4"
    
    wm_type = params.get("type", "text")
    position = params.get("position", "bottom_right")
    opacity = params.get("opacity", 0.7)
    margin = params.get("margin", 20)
    
    # Position mapping
    pos_map = {
        "top_left": f"x={margin}:y={margin}",
        "top_right": f"x=w-tw-{margin}:y={margin}",
        "bottom_left": f"x={margin}:y=h-th-{margin}",
        "bottom_right": f"x=w-tw-{margin}:y=h-th-{margin}",
        "center": "x=(w-tw)/2:y=(h-th)/2",
    }
    pos_expr = pos_map.get(position, pos_map["bottom_right"])
    
    if wm_type == "text":
        text = params.get("text", "@channel")
        size = params.get("size", 24)
        
        # Escape special characters
        text_escaped = text.replace("'", "\\'").replace(":", "\\:")
        
        vf = f"drawtext=text='{text_escaped}':fontsize={size}:fontcolor=white@{opacity}:{pos_expr}:shadowcolor=black@0.5:shadowx=2:shadowy=2"
    else:
        # Image watermark
        image_path = params.get("image_path")
        if not image_path:
            ctx.log("No image path for watermark, skipping")
            return {"skipped": True}
        
        vf = f"movie={image_path}[wm];[in][wm]overlay={pos_expr.replace('tw', 'overlay_w').replace('th', 'overlay_h')}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "copy",
        str(output_path),
    ]
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    return {"path": str(output_path), "type": wm_type, "position": position}


@PipelineExecutor.register("T17_PACKAGE")
async def handle_package(ctx: StepContext, params: dict) -> dict:
    """Final packaging with optimized encoding. Respects export_profile.

    Applies: codec, bitrate, fps, max_duration, pixel_format, movflags
    from the selected ExportProfile. Step params override profile values.
    """
    input_path = ctx.get_input_video()
    output_path = ctx.final_path
    
    ep = ctx.export_profile
    ep_extra = ep.get("extra", {})
    
    codec = params.get("codec") or ep.get("codec") or "h264"
    preset_enc = params.get("preset", "slow")
    crf = params.get("crf", 20)
    video_bitrate = params.get("video_bitrate") or ep.get("video_bitrate")
    audio_bitrate = params.get("audio_bitrate") or ep.get("audio_bitrate") or "192k"
    audio_sample_rate = ep.get("audio_sample_rate") or 44100
    fps = ep.get("fps")
    pix_fmt = ep_extra.get("pixel_format") or "yuv420p"
    movflags = ep_extra.get("movflags") or "+faststart"
    max_duration = ep.get("max_duration_sec")
    
    codec_lib = "libx264" if codec == "h264" else "libx265"
    
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    
    # Обрезка по max_duration если задан
    if max_duration:
        cmd.extend(["-t", str(max_duration)])
    
    cmd.extend(["-c:v", codec_lib, "-preset", preset_enc, "-crf", str(crf)])
    
    # Видео битрейт (если задан — использовать вместо CRF-only)
    if video_bitrate:
        cmd.extend(["-b:v", video_bitrate, "-maxrate", video_bitrate, "-bufsize", video_bitrate])
    
    if fps:
        cmd.extend(["-r", str(fps)])
    
    cmd.extend([
        "-pix_fmt", pix_fmt,
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", str(audio_sample_rate),
        "-movflags", movflags,
        "-map_metadata", "-1",
        str(output_path),
    ])
    
    await run_cmd(cmd, ctx.log)
    ctx.set_output_video(output_path)
    
    size = output_path.stat().st_size
    profile_name = ep.get("name", "default")
    ctx.log(f"[T17_PACKAGE] Packaged with profile '{profile_name}': {codec}, {size} bytes")
    
    return {
        "path": str(output_path),
        "size": size,
        "codec": codec,
        "export_profile": profile_name,
        "max_duration_sec": max_duration,
    }


@PipelineExecutor.register("T18_QC")
async def handle_qc(ctx: StepContext, params: dict) -> dict:
    """Quality control check.

    Includes project policy enforcement: if the project requires certain
    transformations (voice change, caption rewrite, visual transform, hook
    rewrite) but none of the executed pipeline steps correspond to those
    requirements, QC will fail with a clear error.
    """
    input_path = ctx.get_input_video()
    
    min_bitrate = params.get("min_bitrate", "2M")
    check_audio = params.get("check_audio_levels", True)
    
    # Probe the video
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(input_path),
    ]
    
    stdout, _ = await run_cmd(cmd, ctx.log)
    probe_data = json.loads(stdout) if stdout else {}
    
    warnings = []
    errors = []
    
    # ── Policy enforcement ──────────────────────────────────────
    policy = ctx.policy or {}
    executed_tools = set(ctx.outputs.keys())

    POLICY_TOOL_MAP = {
        "require_voice_change": {
            "tools": {"T10_VOICE_CONVERT", "G03_TTS", "T12_REPLACE_AUDIO"},
            "label": "Замена голоса / озвучка (T10_VOICE_CONVERT / G03_TTS / T12_REPLACE_AUDIO)",
        },
        "require_caption_rewrite": {
            "tools": {"T13_BUILD_CAPTIONS", "T14_BURN_CAPTIONS", "G02_CAPTIONS"},
            "label": "Перезапись субтитров (T13_BUILD_CAPTIONS / T14_BURN_CAPTIONS / G02_CAPTIONS)",
        },
        "require_visual_transform": {
            "tools": {"T15_EFFECTS", "T04_CROP_RESIZE", "T16_WATERMARK"},
            "label": "Визуальная трансформация (T15_EFFECTS / T04_CROP_RESIZE / T16_WATERMARK)",
        },
        "require_hook_rewrite": {
            "tools": {"G01_SCRIPT", "T21_TRIM"},
            "label": "Переписывание хука (G01_SCRIPT / T21_TRIM)",
        },
    }

    policy_violations = []
    for policy_key, mapping in POLICY_TOOL_MAP.items():
        if policy.get(policy_key):
            if not executed_tools & mapping["tools"]:
                policy_violations.append(
                    f"Policy '{policy_key}' requires: {mapping['label']}, "
                    f"but none of [{', '.join(sorted(mapping['tools']))}] were executed"
                )

    if policy_violations:
        for v in policy_violations:
            errors.append(v)
            ctx.log(f"[T18_QC] POLICY VIOLATION: {v}")

    # ── Video quality checks ────────────────────────────────────
    video_stream = None
    audio_stream = None
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video" and not video_stream:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and not audio_stream:
            audio_stream = stream
    
    if not video_stream:
        errors.append("No video stream found")
    else:
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        if width < 720 or height < 720:
            warnings.append(f"Low resolution: {width}x{height}")
    
    if not audio_stream and check_audio:
        warnings.append("No audio stream found")
    
    # Check bitrate
    format_info = probe_data.get("format", {})
    bitrate = int(format_info.get("bit_rate", 0))
    min_br_val = int(min_bitrate.replace("M", "000000").replace("k", "000"))
    
    if bitrate > 0 and bitrate < min_br_val:
        warnings.append(f"Low bitrate: {bitrate / 1_000_000:.2f} Mbps")
    
    # Check file size
    size = int(format_info.get("size", 0))
    if size < 500_000:
        warnings.append(f"Small file size: {size / 1024:.1f} KB")
    
    passed = len(errors) == 0
    if params.get("fail_on_warning", False) and warnings:
        passed = False
    
    result = {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
        "policy_violations": policy_violations,
        "video_info": {
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
            "codec": video_stream.get("codec_name") if video_stream else None,
        },
        "audio_info": {
            "codec": audio_stream.get("codec_name") if audio_stream else None,
            "sample_rate": audio_stream.get("sample_rate") if audio_stream else None,
        },
        "bitrate_mbps": bitrate / 1_000_000 if bitrate else None,
        "size_mb": size / 1_000_000 if size else None,
    }
    
    if not passed:
        raise RuntimeError(f"QC failed: {errors + warnings}")
    
    # Copy to ready if passed
    if input_path != ctx.ready_path:
        import shutil
        shutil.copy2(input_path, ctx.ready_path)
        ctx.set_output_video(ctx.ready_path)
    
    return result


@PipelineExecutor.register("T08_SPEECH_TO_TEXT")
async def handle_speech_to_text(ctx: StepContext, params: dict) -> dict:
    """Transcribe audio using Whisper."""
    import os
    
    # Get audio path from previous step or extract
    audio_path = ctx.outputs.get("audio_path")
    if not audio_path:
        # Extract audio first
        input_video = ctx.get_input_video()
        audio_path = ctx.task_dir / "audio_for_stt.wav"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-vn", "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le",
            str(audio_path),
        ]
        await run_cmd(cmd, ctx.log)
    
    model = params.get("model", "base")
    language = params.get("language")  # None = auto-detect
    
    # Check if whisper is available
    whisper_cmd = params.get("whisper_cmd", "whisper")
    
    output_dir = ctx.task_dir / "whisper_out"
    output_dir.mkdir(exist_ok=True)
    
    cmd = [
        whisper_cmd,
        str(audio_path),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", "all",
    ]
    
    if language:
        cmd.extend(["--language", language])
    
    try:
        await run_cmd(cmd, ctx.log)
    except Exception as e:
        # Fallback: try with openai-whisper python module
        ctx.log(f"CLI whisper failed ({e}), trying Python module")
        try:
            import whisper as whisper_module
            model_obj = whisper_module.load_model(model)
            result = model_obj.transcribe(str(audio_path), language=language)
            
            # Save outputs
            text = result.get("text", "")
            segments = result.get("segments", [])
            
            # Save text
            txt_path = output_dir / "transcript.txt"
            txt_path.write_text(text, encoding="utf-8")
            
            # Save SRT
            srt_path = output_dir / "transcript.srt"
            srt_content = _segments_to_srt(segments)
            srt_path.write_text(srt_content, encoding="utf-8")
            
            # Save JSON
            json_path = output_dir / "transcript.json"
            json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            
            ctx.caption_text = text
            ctx.outputs["transcript_text"] = text
            ctx.outputs["transcript_segments"] = segments
            ctx.outputs["srt_path"] = str(srt_path)

            # Update content_signature with transcript (more accurate)
            _update_content_signature(ctx, text)
            
            return {
                "text": text[:500] + "..." if len(text) > 500 else text,
                "language": result.get("language"),
                "segments_count": len(segments),
                "srt_path": str(srt_path),
                "txt_path": str(txt_path),
            }
        except ImportError:
            raise RuntimeError("Whisper not available. Install with: pip install openai-whisper")
    
    # Parse CLI output
    srt_files = list(output_dir.glob("*.srt"))
    txt_files = list(output_dir.glob("*.txt"))
    json_files = list(output_dir.glob("*.json"))
    
    text = ""
    if txt_files:
        text = txt_files[0].read_text(encoding="utf-8")
    
    srt_path = str(srt_files[0]) if srt_files else None
    
    ctx.caption_text = text
    ctx.outputs["transcript_text"] = text
    ctx.outputs["srt_path"] = srt_path

    # Update content_signature with transcript (more accurate)
    _update_content_signature(ctx, text)
    
    return {
        "text": text[:500] + "..." if len(text) > 500 else text,
        "srt_path": srt_path,
        "txt_path": str(txt_files[0]) if txt_files else None,
    }


def _update_content_signature(ctx: StepContext, transcript: str):
    """Update content_signature on the publish task's linked candidate using transcript."""
    if not transcript or not transcript.strip():
        return
    try:
        from app.services.dedupe import compute_signature
        sig = compute_signature(transcript)
        if sig and hasattr(ctx, "publish_task") and ctx.publish_task:
            task = ctx.publish_task
            if hasattr(task, "candidate") and task.candidate:
                meta = task.candidate.meta or {}
                meta["content_signature"] = sig
                meta["content_signature_source"] = "whisper"
                task.candidate.meta = meta
        ctx.outputs["content_signature"] = sig
        ctx.outputs["content_signature_source"] = "whisper"
    except Exception:
        pass  # non-critical


def _segments_to_srt(segments: list) -> str:
    """Convert Whisper segments to SRT format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg.get("start", 0))
        end = _format_srt_time(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT time format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@PipelineExecutor.register("T09_TRANSLATE")
async def handle_translate_text(ctx: StepContext, params: dict) -> dict:
    """Translate transcribed text."""
    import os
    
    text = ctx.outputs.get("transcript_text") or ctx.caption_text
    if not text:
        ctx.log("No text to translate")
        return {"skipped": True}
    
    source_lang = params.get("source_lang", "auto")
    target_lang = params.get("target_lang", "ru")
    provider = params.get("provider", "google")
    
    if provider == "google":
        # Use deep-translator library
        try:
            from deep_translator import GoogleTranslator
            
            # Split into chunks if too long (deep-translator limit is 5000)
            max_chunk = 4500
            chunks = [text[i:i+max_chunk] for i in range(0, len(text), max_chunk)]
            translated_chunks = []
            
            src = source_lang if source_lang != "auto" else "auto"
            translator = GoogleTranslator(source=src, target=target_lang)
            
            for chunk in chunks:
                result = translator.translate(chunk)
                translated_chunks.append(result)
            
            translated = " ".join(translated_chunks)
            detected_lang = source_lang
            
        except ImportError:
            ctx.log("deep-translator not installed, using placeholder")
            translated = f"[TRANSLATION TO {target_lang}]: {text[:200]}..."
            detected_lang = source_lang
    
    elif provider == "deepl":
        # DeepL API
        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPL_API_KEY not set")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api-free.deepl.com/v2/translate",
                data={
                    "auth_key": api_key,
                    "text": text,
                    "target_lang": target_lang.upper(),
                }
            )
            resp.raise_for_status()
            data = resp.json()
            translated = data["translations"][0]["text"]
            detected_lang = data["translations"][0].get("detected_source_language", source_lang)
    
    else:
        translated = text
        detected_lang = source_lang
    
    # Save translated text
    translated_path = ctx.task_dir / "translated.txt"
    translated_path.write_text(translated, encoding="utf-8")
    
    ctx.outputs["translated_text"] = translated
    ctx.caption_text = translated
    
    return {
        "original_length": len(text),
        "translated_length": len(translated),
        "source_lang": detected_lang,
        "target_lang": target_lang,
        "path": str(translated_path),
    }


@PipelineExecutor.register("T10_VOICE_CONVERT")
async def handle_voice_convert(ctx: StepContext, params: dict) -> dict:
    """Convert voice using TTS or voice cloning."""
    import os
    
    text = ctx.outputs.get("translated_text") or ctx.caption_text
    if not text:
        ctx.log("No text for voice synthesis")
        return {"skipped": True}
    
    provider = params.get("provider", "edge_tts")
    voice = params.get("voice", "ru-RU-DmitryNeural")
    output_path = ctx.task_dir / "voice_synth.mp3"
    
    if provider == "edge_tts":
        # Microsoft Edge TTS (free)
        try:
            import edge_tts
            
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
            
        except ImportError:
            ctx.log("edge_tts not installed, using placeholder")
            # Create silent audio as placeholder
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", "5",
                str(output_path),
            ]
            await run_cmd(cmd, ctx.log)
    
    elif provider == "elevenlabs":
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        voice_id = params.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
        
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key},
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                }
            )
            resp.raise_for_status()
            
            with output_path.open("wb") as f:
                f.write(resp.content)
    
    ctx.outputs["synth_audio_path"] = str(output_path)
    
    return {
        "path": str(output_path),
        "provider": provider,
        "voice": voice,
        "size": output_path.stat().st_size,
    }


@PipelineExecutor.register("T11_AUDIO_MIX")
async def handle_mix_audio(ctx: StepContext, params: dict) -> dict:
    """Mix original audio with synthesized voice."""
    original_audio = ctx.outputs.get("audio_path")
    synth_audio = ctx.outputs.get("synth_audio_path")
    
    if not synth_audio:
        ctx.log("No synthesized audio to mix")
        return {"skipped": True}
    
    output_path = ctx.task_dir / "mixed_audio.mp3"
    
    voice_volume = params.get("voice_volume", 1.0)
    music_volume = params.get("music_volume", 0.3)
    
    if original_audio:
        # Mix both tracks
        cmd = [
            "ffmpeg", "-y",
            "-i", str(synth_audio),
            "-i", str(original_audio),
            "-filter_complex",
            f"[0:a]volume={voice_volume}[voice];[1:a]volume={music_volume}[bg];[voice][bg]amix=inputs=2:duration=first[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_path),
        ]
    else:
        # Just copy synth audio
        cmd = [
            "ffmpeg", "-y",
            "-i", str(synth_audio),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_path),
        ]
    
    await run_cmd(cmd, ctx.log)
    ctx.outputs["mixed_audio"] = str(output_path)
    
    return {
        "path": str(output_path),
        "voice_volume": voice_volume,
        "music_volume": music_volume,
    }


@PipelineExecutor.register("T13_BUILD_CAPTIONS")
async def handle_build_captions(ctx: StepContext, params: dict) -> dict:
    """Build styled ASS/SRT captions."""
    segments = ctx.outputs.get("transcript_segments", [])
    text = ctx.outputs.get("translated_text") or ctx.caption_text
    
    style = params.get("style", "default")
    format_type = params.get("format", "ass")
    font = params.get("font", "Arial")
    font_size = params.get("font_size", 48)
    outline = params.get("outline", 2)
    position = params.get("position", "bottom")  # bottom, top, center
    
    if format_type == "ass":
        output_path = ctx.task_dir / "captions.ass"
        content = _build_ass_file(
            segments=segments,
            text=text,
            font=font,
            font_size=font_size,
            outline=outline,
            position=position,
            style=style,
        )
    else:
        output_path = ctx.task_dir / "captions.srt"
        if segments:
            content = _segments_to_srt(segments)
        else:
            # Simple single subtitle
            content = f"1\n00:00:00,000 --> 00:00:10,000\n{text[:200] if text else ''}\n"
    
    output_path.write_text(content, encoding="utf-8")
    ctx.outputs["captions_path"] = str(output_path)
    ctx.captions_path = output_path
    
    return {
        "path": str(output_path),
        "format": format_type,
        "segments_count": len(segments),
        "style": style,
    }


def _build_ass_file(
    segments: list,
    text: str,
    font: str,
    font_size: int,
    outline: int,
    position: str,
    style: str,
    *,
    margin_v: int = 50,
    margin_l: int = 50,
    margin_r: int = 50,
    spacing: int = 0,
) -> str:
    """Build ASS subtitle file with configurable margins and spacing."""
    # Alignment: 1=left, 2=center, 3=right; +0=bottom, +4=middle, +8=top
    alignment = {"bottom": 2, "top": 8, "center": 5}.get(position, 2)
    
    # Style presets
    styles = {
        "default": {"primary": "&H00FFFFFF", "outline_color": "&H00000000", "bold": 0},
        "bold": {"primary": "&H00FFFFFF", "outline_color": "&H00000000", "bold": 1},
        "yellow": {"primary": "&H0000FFFF", "outline_color": "&H00000000", "bold": 1},
        "gradient": {"primary": "&H00FF88FF", "outline_color": "&H00440044", "bold": 1},
        "neon": {"primary": "&H0000FF00", "outline_color": "&H00FF00FF", "bold": 1},
    }
    
    style_params = styles.get(style, styles["default"])
    
    header = f"""[Script Info]
Title: Auto Generated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{style_params['primary']},&H000000FF,{style_params['outline_color']},&H80000000,{style_params['bold']},0,0,0,100,100,{spacing},0,1,{outline},1,{alignment},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    if segments:
        for seg in segments:
            start = _format_ass_time(seg.get("start", 0))
            end = _format_ass_time(seg.get("end", 0))
            seg_text = seg.get("text", "").strip().replace("\n", "\\N")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{seg_text}")
    elif text:
        # Single caption
        events.append(f"Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,,{text[:100]}")
    
    return header + "\n".join(events) + "\n"


def _format_ass_time(seconds: float) -> str:
    """Format seconds to ASS time format (H:MM:SS.cc)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


# ============== Analysis Tools (A-series) ==============

@PipelineExecutor.register("A01_SCRIPT_ANALYSIS")
async def handle_script_analysis(ctx: StepContext, params: dict) -> dict:
    """Analyze Whisper transcript to extract reusable script patterns.

    Extracts from the transcript:
    - hook: opening line / attention grabber (first ~3 seconds)
    - structure: temporal breakdown (intro / body segments / outro)
    - theses: key talking points / main ideas
    - cta: call-to-action phrases
    - retention_pattern: content density over time (where engagement peaks)

    Saves result to candidate.meta.script_analysis (via ctx.session)
    and ctx.outputs["script_analysis"] for downstream G01_SCRIPT.
    """
    import re as _re

    # ── Gather transcript ────────────────────────────────────
    transcript_text = (
        ctx.outputs.get("transcript_text")
        or ctx.caption_text
        or ""
    )
    segments = ctx.outputs.get("transcript_segments") or []

    if not transcript_text and not segments:
        # Try reading from file
        txt_path = ctx.task_dir / "whisper_out" / "transcript.txt"
        if txt_path.exists():
            transcript_text = txt_path.read_text(encoding="utf-8")
        json_path = ctx.task_dir / "whisper_out" / "transcript.json"
        if json_path.exists():
            import json as _json
            raw = _json.loads(json_path.read_text(encoding="utf-8"))
            segments = raw.get("segments", [])
            if not transcript_text:
                transcript_text = raw.get("text", "")

    if not transcript_text:
        raise RuntimeError("A01_SCRIPT_ANALYSIS: no transcript found — run T08_SPEECH_TO_TEXT first")

    # ── Compute total duration ───────────────────────────────
    total_duration = 0.0
    if segments:
        total_duration = max((s.get("end", 0) for s in segments), default=0)
    if not total_duration:
        # Estimate from probe data
        total_duration = float(ctx.outputs.get("duration") or 60)

    # ── 1. Hook (first ~3 seconds) ───────────────────────────
    hook_text = ""
    if segments:
        hook_segs = [s for s in segments if s.get("start", 0) < 3.5]
        hook_text = " ".join(s.get("text", "").strip() for s in hook_segs).strip()
    if not hook_text:
        # Fallback: first sentence
        sentences = _split_sentences(transcript_text)
        hook_text = sentences[0] if sentences else transcript_text[:100]

    # ── 2. Structure (temporal breakdown) ────────────────────
    structure = _analyze_structure(segments, total_duration)

    # ── 3. Theses (key talking points) ───────────────────────
    sentences = _split_sentences(transcript_text)
    theses = _extract_theses(sentences, max_theses=params.get("max_theses", 5))

    # ── 4. CTA detection ────────────────────────────────────
    cta = _detect_cta(segments, sentences, total_duration)

    # ── 5. Retention pattern ────────────────────────────────
    retention = _analyze_retention(segments, total_duration)

    # ── Build result ────────────────────────────────────────
    analysis = {
        "hook": hook_text,
        "structure": structure,
        "theses": theses,
        "cta": cta,
        "retention_pattern": retention,
        "total_duration_sec": round(total_duration, 1),
        "transcript_length": len(transcript_text),
        "segments_count": len(segments),
    }

    # Save to file
    analysis_path = ctx.task_dir / "script_analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    # Store in context for G01_SCRIPT
    ctx.outputs["script_analysis"] = analysis

    # Persist to candidate.meta if session available
    if ctx.session and ctx.publish_task:
        try:
            from app.models import Candidate
            from sqlalchemy import select as _select
            cand_q = await ctx.session.execute(
                _select(Candidate).where(
                    Candidate.linked_publish_task_id == ctx.publish_task.id
                )
            )
            candidate = cand_q.scalar_one_or_none()
            if candidate:
                meta = candidate.meta or {}
                meta["script_analysis"] = analysis
                candidate.meta = meta
                ctx.session.add(candidate)
                await ctx.session.commit()
                ctx.log(f"[A01] Saved script_analysis to candidate #{candidate.id}.meta")
        except Exception as e:
            ctx.log(f"[A01] Could not save to candidate.meta: {e}")

    ctx.log(
        f"[A01] Analysis: hook={len(hook_text)}ch, "
        f"{len(structure['blocks'])} blocks, {len(theses)} theses, "
        f"CTA={'yes' if cta['detected'] else 'no'}, "
        f"retention_zones={len(retention['zones'])}"
    )

    return {
        "path": str(analysis_path),
        "hook": hook_text[:200],
        "blocks_count": len(structure["blocks"]),
        "theses_count": len(theses),
        "cta_detected": cta["detected"],
        "retention_zones": len(retention["zones"]),
    }


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    import re as _re
    raw = _re.split(r'(?<=[.!?…])\s+', text.strip())
    return [s.strip() for s in raw if s.strip() and len(s.strip()) > 3]


def _analyze_structure(segments: list, total_duration: float) -> dict:
    """Break transcript into temporal blocks: intro, body parts, outro."""
    if not segments or total_duration <= 0:
        return {"blocks": [], "pattern": "unknown"}

    # Define time boundaries
    intro_end = min(total_duration * 0.1, 5.0)
    outro_start = max(total_duration * 0.85, total_duration - 8.0)

    blocks = []

    # Intro
    intro_segs = [s for s in segments if s.get("end", 0) <= intro_end + 1]
    if intro_segs:
        blocks.append({
            "type": "intro",
            "start_sec": 0,
            "end_sec": round(intro_end, 1),
            "text": " ".join(s.get("text", "").strip() for s in intro_segs),
            "word_count": sum(len(s.get("text", "").split()) for s in intro_segs),
        })

    # Body — split into chunks of ~15 seconds
    body_segs = [
        s for s in segments
        if s.get("start", 0) >= intro_end and s.get("end", 0) <= outro_start
    ]
    if body_segs:
        chunk_dur = 15.0
        chunk_start = intro_end
        chunk_idx = 0
        while chunk_start < outro_start:
            chunk_end = min(chunk_start + chunk_dur, outro_start)
            chunk_texts = [
                s for s in body_segs
                if s.get("start", 0) >= chunk_start - 0.5 and s.get("start", 0) < chunk_end
            ]
            if chunk_texts:
                blocks.append({
                    "type": "body",
                    "index": chunk_idx,
                    "start_sec": round(chunk_start, 1),
                    "end_sec": round(chunk_end, 1),
                    "text": " ".join(s.get("text", "").strip() for s in chunk_texts),
                    "word_count": sum(len(s.get("text", "").split()) for s in chunk_texts),
                })
                chunk_idx += 1
            chunk_start = chunk_end

    # Outro
    outro_segs = [s for s in segments if s.get("start", 0) >= outro_start - 0.5]
    if outro_segs:
        blocks.append({
            "type": "outro",
            "start_sec": round(outro_start, 1),
            "end_sec": round(total_duration, 1),
            "text": " ".join(s.get("text", "").strip() for s in outro_segs),
            "word_count": sum(len(s.get("text", "").split()) for s in outro_segs),
        })

    # Classify pattern
    body_count = sum(1 for b in blocks if b["type"] == "body")
    pattern = "unknown"
    if body_count <= 1:
        pattern = "single_point"
    elif body_count <= 3:
        pattern = "listicle_short"
    elif body_count <= 5:
        pattern = "listicle_medium"
    else:
        pattern = "deep_dive"

    return {"blocks": blocks, "pattern": pattern, "body_segments": body_count}


def _extract_theses(sentences: list[str], max_theses: int = 5) -> list[dict]:
    """Extract key talking points from sentences.

    Heuristic: longer sentences with content words are more likely to be theses.
    Skip very short sentences and filler phrases.
    """
    import re as _re

    FILLER_PATTERNS = [
        r"^(ну|так|вот|ладно|окей|хорошо|да\b|нет\b|ага|угу)",
        r"^(well|so|okay|right|yeah|um|uh)\b",
    ]

    scored = []
    for i, sent in enumerate(sentences):
        words = sent.split()
        if len(words) < 4:
            continue
        # Skip fillers
        is_filler = any(_re.match(p, sent.lower()) for p in FILLER_PATTERNS)
        if is_filler:
            continue

        # Score: word count + unique words ratio
        unique_ratio = len(set(w.lower() for w in words)) / len(words)
        score = len(words) * unique_ratio
        scored.append({"index": i, "text": sent, "score": round(score, 2)})

    # Top N by score
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:max_theses]
    # Re-sort by original order
    top.sort(key=lambda x: x["index"])

    return [{"text": t["text"], "position": t["index"]} for t in top]


_CTA_KEYWORDS_RU = [
    "подписывайтесь", "подпишись", "подписка", "лайк", "ставьте лайк",
    "комментарий", "напишите", "поделитесь", "репост", "ссылка в описании",
    "сохраняйте", "отправьте другу", "нажмите", "кнопк", "колокольчик",
]
_CTA_KEYWORDS_EN = [
    "subscribe", "like", "comment", "share", "follow",
    "link in bio", "link in description", "hit the bell",
    "let me know", "drop a comment", "save this", "send to a friend",
]


def _detect_cta(segments: list, sentences: list[str], total_duration: float) -> dict:
    """Detect call-to-action in the transcript."""
    all_cta_kw = _CTA_KEYWORDS_RU + _CTA_KEYWORDS_EN
    cta_phrases = []

    # Check last 15% of video (or last 10 seconds)
    cta_zone_start = max(total_duration * 0.85, total_duration - 10) if total_duration > 0 else 0

    for seg in segments:
        text_lower = seg.get("text", "").lower()
        for kw in all_cta_kw:
            if kw in text_lower:
                cta_phrases.append({
                    "text": seg.get("text", "").strip(),
                    "keyword": kw,
                    "start_sec": seg.get("start"),
                    "in_outro": seg.get("start", 0) >= cta_zone_start,
                })
                break

    # Also check sentences (for non-segment mode)
    if not cta_phrases and sentences:
        for sent in sentences[-3:]:
            text_lower = sent.lower()
            for kw in all_cta_kw:
                if kw in text_lower:
                    cta_phrases.append({
                        "text": sent,
                        "keyword": kw,
                        "in_outro": True,
                    })
                    break

    return {
        "detected": len(cta_phrases) > 0,
        "phrases": cta_phrases,
        "in_outro": any(p.get("in_outro") for p in cta_phrases),
    }


def _analyze_retention(segments: list, total_duration: float) -> dict:
    """Analyze content density over time to identify retention patterns.

    Divides video into zones and measures words-per-second as proxy for
    content density. High density = more talking = likely higher retention.
    """
    if not segments or total_duration <= 0:
        return {"zones": [], "avg_wps": 0, "peak_zone": None}

    # Divide into 5 equal zones
    n_zones = min(5, max(2, int(total_duration / 10)))
    zone_dur = total_duration / n_zones
    zones = []

    peak_wps = 0
    peak_idx = 0

    for i in range(n_zones):
        z_start = i * zone_dur
        z_end = (i + 1) * zone_dur
        zone_segs = [
            s for s in segments
            if s.get("start", 0) >= z_start - 0.5 and s.get("start", 0) < z_end
        ]
        word_count = sum(len(s.get("text", "").split()) for s in zone_segs)
        wps = round(word_count / zone_dur, 2) if zone_dur > 0 else 0

        label = "intro" if i == 0 else ("outro" if i == n_zones - 1 else f"mid_{i}")

        zones.append({
            "index": i,
            "label": label,
            "start_sec": round(z_start, 1),
            "end_sec": round(z_end, 1),
            "word_count": word_count,
            "words_per_sec": wps,
        })

        if wps > peak_wps:
            peak_wps = wps
            peak_idx = i

    total_words = sum(z["word_count"] for z in zones)
    avg_wps = round(total_words / total_duration, 2) if total_duration > 0 else 0

    return {
        "zones": zones,
        "avg_wps": avg_wps,
        "peak_zone": zones[peak_idx]["label"] if zones else None,
        "total_words": total_words,
    }


# ============== Generation Pipeline Tools (G-series) ==============

@PipelineExecutor.register("G01_SCRIPT")
async def handle_generate_script(ctx: StepContext, params: dict) -> dict:
    """Generate video script from candidate meta / brief data.

    Reads candidate_meta (hook, script, keywords) or brief_data (topic, style)
    and produces a structured script JSON saved to task folder.

    If script_analysis is available (from A01_SCRIPT_ANALYSIS), uses the
    original video's hook, structure, theses and CTA as a blueprint to
    generate a NEW version — same ideas, different words.
    """
    meta = ctx.candidate_meta or {}
    brief = ctx.brief_data or {}

    # ── Script analysis from A01 (if available) ──────────────
    analysis = (
        ctx.outputs.get("script_analysis")
        or meta.get("script_analysis")
        or {}
    )
    has_analysis = bool(analysis and analysis.get("hook"))

    # Gather inputs — analysis overrides generic defaults
    hook = analysis.get("hook") or meta.get("hook") or params.get("hook", "")
    existing_script = meta.get("script") or params.get("script", "")
    topic = brief.get("topic") or meta.get("topic") or params.get("topic", "Untitled")
    style = brief.get("style") or params.get("style", "educational")
    tone = brief.get("tone") or params.get("tone", "casual")
    target_duration = (
        brief.get("target_duration_sec")
        or params.get("target_duration_sec")
        or ctx.export_profile.get("recommended_duration_sec")
        or 60
    )
    keywords = meta.get("keywords") or params.get("keywords", [])
    language = brief.get("language") or params.get("language", "ru")

    dur = int(target_duration)
    segments = []

    if has_analysis:
        # ── Build script FROM analysis blueprint ─────────────
        ctx.log("[G01_SCRIPT] Using A01 script_analysis as blueprint")

        src_blocks = analysis.get("structure", {}).get("blocks", [])
        src_theses = analysis.get("theses", [])
        src_cta = analysis.get("cta", {})

        # Scale source timing to target duration
        src_dur = analysis.get("total_duration_sec") or dur
        time_scale = dur / src_dur if src_dur > 0 else 1.0

        seg_idx = 0

        # Hook from analysis
        segments.append({
            "index": seg_idx,
            "type": "hook",
            "start_sec": 0,
            "end_sec": min(3, dur),
            "text": f"[ПЕРЕПИСАТЬ] {hook}",
            "source_text": hook,
            "notes": "rewrite the hook — same idea, new words",
        })
        seg_idx += 1

        # Body segments from structure blocks
        thesis_iter = iter(src_theses)
        for block in src_blocks:
            if block.get("type") not in ("body",):
                continue
            scaled_start = round(block.get("start_sec", 0) * time_scale, 1)
            scaled_end = round(block.get("end_sec", 0) * time_scale, 1)
            # Clamp to target duration
            scaled_start = min(scaled_start, dur - 1)
            scaled_end = min(scaled_end, dur)

            # Attach thesis if available
            thesis = next(thesis_iter, None)
            thesis_text = thesis["text"] if thesis else block.get("text", "")

            segments.append({
                "index": seg_idx,
                "type": "body",
                "start_sec": scaled_start,
                "end_sec": scaled_end,
                "text": f"[ПЕРЕПИСАТЬ] {thesis_text}",
                "source_text": thesis_text,
                "notes": f"rewrite body segment — same thesis, new delivery. style: {style}, tone: {tone}",
            })
            seg_idx += 1

        # If no body blocks from analysis, create from theses
        if not any(s["type"] == "body" for s in segments):
            body_start = min(3, dur)
            body_end = max(body_start + 1, dur - 5)
            for i, thesis in enumerate(src_theses):
                n = len(src_theses) or 1
                seg_start = body_start + i * ((body_end - body_start) // n)
                seg_end = body_start + (i + 1) * ((body_end - body_start) // n)
                segments.append({
                    "index": seg_idx,
                    "type": "body",
                    "start_sec": seg_start,
                    "end_sec": seg_end,
                    "text": f"[ПЕРЕПИСАТЬ] {thesis['text']}",
                    "source_text": thesis["text"],
                    "notes": f"rewrite thesis {i+1}/{len(src_theses)}, style: {style}",
                })
                seg_idx += 1

        # CTA from analysis
        cta_text = ""
        if src_cta.get("detected") and src_cta.get("phrases"):
            cta_text = src_cta["phrases"][0].get("text", "")
        cta_fallback = cta_text or "Подписывайтесь и ставьте лайк!"

        body_end_sec = segments[-1]["end_sec"] if segments else dur - 5
        segments.append({
            "index": seg_idx,
            "type": "cta",
            "start_sec": body_end_sec,
            "end_sec": dur,
            "text": f"[ПЕРЕПИСАТЬ] {cta_fallback}",
            "source_text": cta_fallback,
            "notes": "rewrite CTA — same intent, fresh phrasing",
        })

    else:
        # ── Original template-based generation ───────────────
        segments.append({
            "index": 0,
            "type": "hook",
            "start_sec": 0,
            "end_sec": min(3, dur),
            "text": hook or f"Привет! Сегодня поговорим о {topic}",
            "notes": "attention-grabbing opening",
        })

        body_start = min(3, dur)
        body_end = max(body_start + 1, dur - 5)
        body_duration = body_end - body_start
        n_body = max(1, body_duration // 15)

        for i in range(n_body):
            seg_start = body_start + i * (body_duration // n_body)
            seg_end = body_start + (i + 1) * (body_duration // n_body)
            segments.append({
                "index": i + 1,
                "type": "body",
                "start_sec": seg_start,
                "end_sec": seg_end,
                "text": f"[Основная часть {i + 1}/{n_body}] — раскрытие темы «{topic}»",
                "notes": f"segment {i+1}, style: {style}, tone: {tone}",
            })

        segments.append({
            "index": len(segments),
            "type": "cta",
            "start_sec": body_end,
            "end_sec": dur,
            "text": "Подписывайтесь и ставьте лайк! До встречи в следующем видео.",
            "notes": "call to action + closing",
        })

    script_data = {
        "topic": topic,
        "style": style,
        "tone": tone,
        "language": language,
        "target_duration_sec": dur,
        "hook": hook,
        "keywords": keywords,
        "segments": segments,
        "full_text": existing_script or "\n".join(s["text"] for s in segments),
        "based_on_analysis": has_analysis,
        "retention_pattern": analysis.get("retention_pattern") if has_analysis else None,
    }

    # Save to task folder
    script_path = ctx.task_dir / "script.json"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(json.dumps(script_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also save plain text version
    text_path = ctx.task_dir / "script.txt"
    text_path.write_text(script_data["full_text"], encoding="utf-8")

    # Store in context for downstream steps
    ctx.outputs["script_data"] = script_data
    ctx.outputs["script_path"] = str(script_path)
    ctx.caption_text = script_data["full_text"]

    mode = "from_analysis" if has_analysis else "template"
    ctx.log(f"[G01_SCRIPT] Generated script ({mode}): {len(segments)} segments, {dur}s, {len(keywords)} keywords")

    return {
        "path": str(script_path),
        "text_path": str(text_path),
        "segments_count": len(segments),
        "duration_sec": dur,
        "topic": topic,
        "style": style,
        "based_on_analysis": has_analysis,
    }


@PipelineExecutor.register("G02_CAPTIONS")
async def handle_generate_captions(ctx: StepContext, params: dict) -> dict:
    """Generate SRT/ASS captions from script segments.

    Параметры (params → export_profile.safe_area → дефолт):
        bottom_margin  – отступ снизу в px (safe_area.bottom, 50)
        top_margin     – отступ сверху в px (safe_area.top, 120)
        font_size      – размер шрифта для ASS (48)
        max_lines      – макс. строк на экране (2)
        line_spacing    – межстрочный интервал для ASS (8)
        max_chars_per_line – макс. символов в строке для переноса (42)
    """
    script_data = ctx.outputs.get("script_data") or {}
    segments = script_data.get("segments", [])
    meta = ctx.candidate_meta or {}

    ep = ctx.export_profile
    safe = ep.get("safe_area", {})

    # ── Параметры с каскадом: params → safe_area → дефолт ──
    bottom_margin = params.get("bottom_margin") or safe.get("bottom") or 50
    top_margin = params.get("top_margin") or safe.get("top") or 120
    font_size = params.get("font_size", 48)
    max_lines = params.get("max_lines", 2)
    line_spacing = params.get("line_spacing", 8)
    max_chars = params.get("max_chars_per_line", 42)

    # Fallback: build segments from meta captions_draft
    if not segments:
        captions_draft = meta.get("captions_draft") or ctx.caption_text or ""
        if captions_draft:
            lines = [l.strip() for l in captions_draft.split("\n") if l.strip()]
            dur = script_data.get("target_duration_sec", 60) or 60
            per_line = max(2, dur // max(len(lines), 1))
            segments = []
            for i, line in enumerate(lines):
                segments.append({
                    "index": i,
                    "type": "caption",
                    "start_sec": i * per_line,
                    "end_sec": (i + 1) * per_line,
                    "text": line,
                })

    if not segments:
        ctx.log("[G02_CAPTIONS] No segments to build captions from")
        return {"skipped": True, "reason": "no segments"}

    fmt = params.get("format", "srt")

    # Word-wrap с учётом max_lines
    def wrap(text: str, limit: int, max_ln: int) -> str:
        words = text.split()
        lines: list[str] = []
        current = ""
        for w in words:
            if current and len(current) + 1 + len(w) > limit:
                lines.append(current)
                current = w
            else:
                current = f"{current} {w}".strip()
        if current:
            lines.append(current)
        # Ограничение по max_lines
        if len(lines) > max_ln:
            lines = lines[:max_ln]
            lines[-1] = lines[-1][:limit - 1] + "…"
        return "\n".join(lines)

    # Build SRT
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg.get("start_sec", 0))
        end = _format_srt_time(seg.get("end_sec", 0))
        text = wrap(seg.get("text", ""), max_chars, max_lines)
        srt_lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    srt_content = "\n".join(srt_lines)
    srt_path = ctx.task_dir / "captions.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    ctx.outputs["captions_path"] = str(srt_path)
    ctx.outputs["captions_segments"] = segments
    ctx.captions_path = srt_path

    # Сохраняем caption-параметры в outputs для T14_BURN_CAPTIONS
    ctx.outputs["caption_params"] = {
        "bottom_margin": bottom_margin,
        "top_margin": top_margin,
        "font_size": font_size,
        "max_lines": max_lines,
        "line_spacing": line_spacing,
    }

    # Optionally build ASS too
    ass_path = None
    if fmt == "ass" or params.get("also_ass", False):
        font = params.get("font", "Arial")
        outline = params.get("outline", 2)
        position = params.get("position", "bottom")
        style = params.get("style", "bold")
        margin_l = safe.get("left") or 30
        margin_r = safe.get("right") or 30

        ass_content = _build_ass_file(
            segments=[{
                "start": s.get("start_sec", 0),
                "end": s.get("end_sec", 0),
                "text": s.get("text", ""),
            } for s in segments],
            text=ctx.caption_text or "",
            font=font, font_size=font_size, outline=outline,
            position=position, style=style,
            margin_v=bottom_margin, margin_l=margin_l, margin_r=margin_r,
            spacing=line_spacing,
        )
        ass_path = ctx.task_dir / "captions.ass"
        ass_path.write_text(ass_content, encoding="utf-8")

    ctx.log(
        f"[G02_CAPTIONS] {len(segments)} segments, font_size={font_size}, "
        f"bottom_margin={bottom_margin}, max_lines={max_lines}, line_spacing={line_spacing}"
    )

    return {
        "srt_path": str(srt_path),
        "ass_path": str(ass_path) if ass_path else None,
        "segments_count": len(segments),
        "format": fmt,
        "font_size": font_size,
        "bottom_margin": bottom_margin,
        "top_margin": top_margin,
        "max_lines": max_lines,
        "line_spacing": line_spacing,
    }


@PipelineExecutor.register("G03_TTS")
async def handle_generate_tts(ctx: StepContext, params: dict) -> dict:
    """Generate TTS audio from script text (stub: creates silent placeholder).

    When a real TTS provider is configured (edge_tts, elevenlabs, etc.),
    swap the stub section below. The output audio is saved as voice.mp3
    in the task folder and registered for downstream audio mixing.
    """
    script_data = ctx.outputs.get("script_data") or {}
    text = script_data.get("full_text") or ctx.caption_text or ""

    if not text:
        ctx.log("[G03_TTS] No text for TTS")
        return {"skipped": True, "reason": "no text"}

    provider = params.get("provider", "stub")
    voice = params.get("voice", "ru-RU-DmitryNeural")
    output_path = ctx.task_dir / "voice.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration_sec = script_data.get("target_duration_sec", 30) or 30

    if provider == "edge_tts":
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
        except ImportError:
            ctx.log("[G03_TTS] edge_tts not installed, falling back to stub")
            provider = "stub"

    if provider == "stub":
        # Generate silent audio placeholder with correct duration
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_sec),
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(output_path),
        ]
        await run_cmd(cmd, ctx.log)

    size = output_path.stat().st_size if output_path.exists() else 0

    # Register for downstream steps (T11_AUDIO_MIX, T12_REPLACE_AUDIO)
    ctx.outputs["synth_audio_path"] = str(output_path)
    ctx.outputs["audio_path"] = str(output_path)

    ctx.log(f"[G03_TTS] Generated audio: {provider}, {size} bytes, {duration_sec}s")

    return {
        "path": str(output_path),
        "provider": provider,
        "voice": voice,
        "duration_sec": duration_sec,
        "size": size,
        "text_length": len(text),
    }


# ============== Publishing ==============

@PipelineExecutor.register("P01_PUBLISH")
async def handle_publish(ctx: StepContext, params: dict) -> dict:
    """Publish the final video to the destination platform.

    Выполняется как последний шаг пресета (после T18_QC).
    Использует PublisherAdapter для загрузки на платформу.

    Устойчивость:
    - Idempotency: (task_id, destination_id) — повторный запуск не дублирует
    - Retry: до 3 попыток с backoff (60с / 300с / 1200с) для retryable ошибок
    - Fatal ошибки (нет токена, невалидный файл) — немедленный fail
    - Каждая попытка логируется в StepResult.output_data.attempts[]
    """
    import asyncio
    import traceback
    from sqlalchemy import text as sa_text
    from app.models import PublishTask, SocialAccount, Candidate, CandidateStatus, StepResult
    from app.services.publisher_adapter import get_publisher, PublishResult

    session = ctx.session
    task = ctx.publish_task

    if not session or not task:
        raise RuntimeError("P01_PUBLISH requires session and publish_task in StepContext")

    # ── Idempotency check ────────────────────────────────────
    # Считаем задачу уже опубликованной, если есть published_url ИЛИ published_external_id
    already_published = (
        task.status == "published"
        and (task.published_url or task.published_external_id)
    )
    if already_published:
        ctx.log(
            f"[P01_PUBLISH] Idempotency: task #{task.id} already published "
            f"(url={task.published_url}, ext_id={task.published_external_id}) — skipping"
        )
        return {
            "published": True,
            "published_url": task.published_url,
            "published_external_id": task.published_external_id,
            "platform": task.platform,
            "idempotent_skip": True,
        }

    # ── In-progress protection (advisory lock per task) ──────
    # Prevents a second worker from publishing the same task concurrently.
    # Lock key: 800_000 + task_id — unique per task, separate namespace from scheduler locks.
    publish_lock_key = 800_000 + task.id
    lock_result = await session.execute(sa_text(f"SELECT pg_try_advisory_lock({publish_lock_key})"))
    lock_acquired = bool(lock_result.scalar())

    if not lock_acquired:
        ctx.log(
            f"[P01_PUBLISH] Advisory lock NOT acquired for task #{task.id} — "
            f"another worker is already publishing this task, skipping"
        )
        return {
            "published": False,
            "skipped": True,
            "reason": "concurrent_publish_in_progress",
        }

    try:
        # Re-read task status under lock to catch race condition
        await session.refresh(task)
        if task.status == "publishing":
            ctx.log(
                f"[P01_PUBLISH] Task #{task.id} status is 'publishing' (race detected) — skipping"
            )
            return {
                "published": False,
                "skipped": True,
                "reason": "already_publishing",
            }
        if task.status == "published" and (task.published_url or task.published_external_id):
            ctx.log(
                f"[P01_PUBLISH] Task #{task.id} was published between lock acquire and re-check — skipping"
            )
            return {
                "published": True,
                "published_url": task.published_url,
                "published_external_id": task.published_external_id,
                "platform": task.platform,
                "idempotent_skip": True,
            }

        return await _do_publish(ctx, params, task, session)
    finally:
        # Always release advisory lock
        await session.execute(sa_text(f"SELECT pg_advisory_unlock({publish_lock_key})"))


async def _do_publish(ctx: StepContext, params: dict, task, session) -> dict:
    """Core publish logic — called under advisory lock."""
    import asyncio
    import traceback
    from sqlalchemy import select as sa_select
    from app.models import SocialAccount, Candidate, CandidateStatus
    from app.services.publisher_adapter import get_publisher, PublishResult

    # ── Resolve output video ─────────────────────────────────
    input_path = ctx.get_input_video()
    if not input_path or not input_path.exists():
        for name in ("final.mp4", "ready.mp4", "output.mp4"):
            p = ctx.task_dir / name
            if p.exists():
                input_path = p
                break

    if not input_path or not input_path.exists():
        raise RuntimeError(f"P01_PUBLISH: no output video found in {ctx.task_dir}")

    # ── Resolve adapter ──────────────────────────────────────
    account = await session.get(SocialAccount, ctx.destination_account_id)
    if not account:
        raise RuntimeError(f"P01_PUBLISH: destination account #{ctx.destination_account_id} not found")

    platform = (ctx.platform or task.platform or "").lower()
    adapter = get_publisher(platform)
    if not adapter:
        raise RuntimeError(f"P01_PUBLISH: no adapter for platform '{platform}'")

    # ── Prepare metadata ─────────────────────────────────────
    title = task.caption_text or task.instructions or f"Video #{task.id}"
    description = task.caption_text or ""
    tags: list[str] = []
    if task.artifacts and isinstance(task.artifacts, dict):
        t = task.artifacts.get("tags") or task.artifacts.get("hashtags") or []
        if isinstance(t, list):
            tags = [str(x) for x in t]

    # ── Retry loop ───────────────────────────────────────────
    MAX_ATTEMPTS = 3
    BACKOFF_SECONDS = [60, 300, 1200]  # 1м, 5м, 20м
    attempts: list[dict] = []
    final_result: PublishResult | None = None

    for attempt_num in range(1, MAX_ATTEMPTS + 1):
        attempt_start = datetime.now(timezone.utc)

        # Mark as publishing
        task.status = "publishing"
        session.add(task)
        await session.commit()
        ctx.log(
            f"[P01_PUBLISH] Attempt {attempt_num}/{MAX_ATTEMPTS} — "
            f"{platform} via {adapter.__class__.__name__}"
        )

        attempt_record: dict = {
            "attempt": attempt_num,
            "started_at": attempt_start.isoformat(),
            "platform": platform,
        }

        try:
            result: PublishResult = await adapter.publish(
                task=task,
                account=account,
                file_path=input_path,
                title=title,
                description=description,
                tags=tags,
            )
        except Exception as exc:
            tb = traceback.format_exc()
            result = PublishResult(
                success=False,
                platform=platform,
                error=f"Unhandled exception: {exc}",
                retryable=True,  # неизвестные ошибки считаем retryable
            )
            attempt_record["stacktrace"] = tb

        attempt_end = datetime.now(timezone.utc)
        attempt_record["finished_at"] = attempt_end.isoformat()
        attempt_record["duration_ms"] = int((attempt_end - attempt_start).total_seconds() * 1000)
        attempt_record["success"] = result.success
        attempt_record["error"] = result.error
        attempt_record["retryable"] = result.retryable
        attempt_record["external_id"] = result.external_id
        attempt_record["url"] = result.url
        attempts.append(attempt_record)

        if result.success:
            final_result = result
            ctx.log(f"[P01_PUBLISH] Attempt {attempt_num} succeeded: {result.url}")
            break

        # Fatal error — не retry
        if not result.retryable:
            final_result = result
            ctx.log(f"[P01_PUBLISH] Attempt {attempt_num} FATAL error (no retry): {result.error}")
            break

        # Retryable — ждём backoff если не последняя попытка
        if attempt_num < MAX_ATTEMPTS:
            wait = BACKOFF_SECONDS[attempt_num - 1]
            ctx.log(
                f"[P01_PUBLISH] Attempt {attempt_num} retryable error: {result.error}. "
                f"Waiting {wait}s before retry..."
            )
            await asyncio.sleep(wait)
        else:
            final_result = result
            ctx.log(f"[P01_PUBLISH] Attempt {attempt_num} failed, no more retries: {result.error}")

    # ── Persist result ───────────────────────────────────────
    now = datetime.now(timezone.utc)

    if final_result and final_result.success:
        task.status = "published"
        task.published_url = final_result.url
        task.published_external_id = final_result.external_id
        task.published_at = now
        task.publish_error = None
        session.add(task)

        # Update linked Candidate → USED
        cand_q = await session.execute(
            sa_select(Candidate).where(Candidate.linked_publish_task_id == task.id)
        )
        candidate = cand_q.scalar_one_or_none()
        if candidate:
            candidate.status = CandidateStatus.used.value
            session.add(candidate)
            ctx.log(f"[P01_PUBLISH] Candidate #{candidate.id} → USED")

        await session.commit()

        return {
            "published": True,
            "published_url": final_result.url,
            "published_external_id": final_result.external_id,
            "platform": final_result.platform,
            "attempts_count": len(attempts),
            "attempts": attempts,
        }
    else:
        error_msg = final_result.error if final_result else "All publish attempts failed"
        task.status = "error"
        task.publish_error = error_msg
        task.error_message = f"P01_PUBLISH failed after {len(attempts)} attempt(s): {error_msg}"
        session.add(task)
        await session.commit()

        # Сохранить подробности всех попыток в StepResult
        # (pipeline executor сохранит основной StepResult,
        #  но attempts[] будет в output_data через raise)
        raise RuntimeError(
            f"P01_PUBLISH failed after {len(attempts)} attempt(s): {error_msg}"
            f" | attempts: {json.dumps(attempts, default=str)}"
        )
