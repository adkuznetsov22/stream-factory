import asyncio

import numpy as np

SAMPLE_RATE = 8000


async def loudness_per_second(path) -> list[float]:
    """RMS level in dBFS for each second of the file's audio."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    pcm, _ = await proc.communicate()
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    out = []
    for i in range(0, len(samples), SAMPLE_RATE):
        chunk = samples[i : i + SAMPLE_RATE]
        if len(chunk) < SAMPLE_RATE // 4:
            break
        rms = float(np.sqrt(np.mean(chunk**2))) + 1e-9
        out.append(float(20 * np.log10(rms)))
    return out
