"""AI judge: a multimodal model watches frames, reads speech and chat, and scores virality and safety."""
import asyncio
import base64
import json
import logging
import re
from pathlib import Path

import httpx

from .config import Settings
from .policy import CATEGORIES, THEMES
from .render import run_ffmpeg

log = logging.getLogger(__name__)

PROMPT = """Ты — редактор вирусных Shorts/Reels/Клипов по стримам GTA 6 для русскоязычной аудитории.
Перед тобой кандидат в клип: {n} кадров по порядку (каждые ~{step:.0f} с), речь стримера, чат и контекст.
Стример: {name}. Название стрима: «{stream_title}».{viewer}

Речь стримера (с таймкодами от начала фрагмента):
{speech}

Чат в момент пика (выборка):
{chat}

Оцени строго и честно. Большинство кандидатов — проходные (виральность 20–50). 80+ только если момент реально
могли бы переслать друзьям: есть завязка и развязка, понятно без контекста стрима, сильная реакция или неожиданность.

Безопасность: оцени каждую категорию уровнем 0 (нет), 1 (сомнительно), 2 (есть), 3 (явно и грубо), с доказательством.
Игровое насилие GTA — норма, это не violence_real. Категории: {cats}.
Последнее изображение — тот же кадр с сеткой 10×10: столбцы A–J слева направо, строки 1–10 сверху вниз.
banners — области с рекламой букмекеров, казино, ставок, промокодов и QR-кодов (оверлей стрима, логотипы, плашки),
по этой сетке: "C2:E3" = от клетки C2 до клетки E3 включительно. Бери все клетки, которых касается реклама. Если рекламы нет — [].

Верни строго JSON без пояснений:
{{"virality": 0-100, "hook": 0-10, "payoff": 0-10, "standalone": 0-10,
 "themes": {{{themes}}},
 "trim": {{"start": секунда_начала, "end": секунда_конца}},
 "overlay": "текст-хук на видео до 40 символов, без кавычек",
 "title": "заголовок до 80 символов, интригует, без кликбейт-лжи",
 "description": "1 предложение",
 "safety": {{"категория": {{"level": 0-3, "evidence": "что именно"}}}},
 "banners": ["C2:E3"],
 "why": "1-2 предложения: почему зайдёт или не зайдёт"}}"""


GRID = "drawgrid=w=iw/10:h=ih/10:t=2:c=yellow@0.8," + ",".join(
    f"drawtext=text='{c}{r + 1}':x=w*{i / 10 + 0.005:.3f}:y=h*{r / 10 + 0.005:.3f}:fontsize=h/45:fontcolor=yellow:"
    "box=1:boxcolor=black@0.5" for i, c in enumerate("ABCDEFGHIJ") for r in range(10))


async def grid_frame(src: Path, at: float) -> str | None:
    f = src.parent / "judge_grid.jpg"
    await run_ffmpeg(["-ss", f"{at:.2f}", "-i", src.name, "-frames:v", "1", "-vf", f"scale=1024:-2,{GRID}", "-q:v", "4",
                      f.name], src.parent)
    if not f.exists():
        return None
    b = base64.b64encode(f.read_bytes()).decode()
    f.unlink()
    return b


async def frames(src: Path, t0: float, t1: float, n: int = 6) -> list[str]:
    step = (t1 - t0) / n
    out = []
    for i in range(n):
        f = src.parent / f"judge_{i}.jpg"
        await run_ffmpeg(["-ss", f"{t0 + step * (i + 0.5):.2f}", "-i", src.name, "-frames:v", "1",
                          "-vf", "scale=512:-2", "-q:v", "5", f.name], src.parent)
        if f.exists():
            out.append(base64.b64encode(f.read_bytes()).decode())
            f.unlink()
    return out


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


async def judge(client: httpx.AsyncClient, s: Settings, src: Path, t0: float, t1: float, name: str, stream_title: str,
                lines: list[dict], chat: list[str], viewer_titles: list[str]) -> dict | None:
    if not (s.openai_api_key or s.openrouter_api_key):
        return None
    imgs = await frames(src, t0, t1)
    grid = await grid_frame(src, (t0 + t1) / 2)
    speech = "\n".join(f"[{ln['start'] - t0:.0f}s] {ln['text']}" for ln in lines if t0 - 1 <= ln["start"] <= t1) or "(речи нет)"
    prompt = PROMPT.format(
        n=len(imgs), step=(t1 - t0) / max(len(imgs), 1), name=name, stream_title=stream_title or "",
        viewer=f"\nЗрители уже нарезали этот момент на Twitch: {'; '.join(viewer_titles)}" if viewer_titles else "",
        speech=speech[:3000], chat="\n".join(chat[-40:])[:2500] or "(нет)",
        cats=", ".join(f"{k} ({v})" for k, v in CATEGORIES.items()),
        themes=", ".join(f'"{k}": 0-1' for k in THEMES))
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in imgs + ([grid] if grid else [])]
    url, key, model = _endpoint(s)
    r = await client.post(url, timeout=60, headers={"Authorization": f"Bearer {key}"}, json={
        "model": model, "messages": [{"role": "user", "content": content}],
        "temperature": 0.2, "response_format": {"type": "json_object"}})
    r.raise_for_status()
    body = r.json()
    out = _json(body["choices"][0]["message"]["content"])
    if "virality" not in out:
        raise RuntimeError("judge returned no virality")
    out["virality"] = max(0.0, min(float(out["virality"]), 100.0))
    trim = out.get("trim") or {}
    try:
        a, b = float(trim.get("start", 0)), float(trim.get("end", t1 - t0))
        out["trim"] = {"start": max(0.0, a), "end": min(t1 - t0, b)} if b - a >= 5 else None
    except (TypeError, ValueError):
        out["trim"] = None
    out["banners"] = _boxes(out.get("banners"))
    out["model"] = model
    out["cost"] = (body.get("usage") or {}).get("cost")
    return out


CELL = re.compile(r"^\s*([A-J])(10|[1-9])\s*(?::\s*([A-J])(10|[1-9]))?\s*$", re.I)


def _boxes(raw) -> list[list[float]]:
    """Grid ranges like "C2:E3" -> normalized [x, y, w, h] with a small margin."""
    out = []
    for b in raw if isinstance(raw, list) else []:
        m = CELL.match(str(b))
        if not m:
            continue
        c0, r0 = "ABCDEFGHIJ".index(m[1].upper()), int(m[2]) - 1
        c1, r1 = ("ABCDEFGHIJ".index(m[3].upper()), int(m[4]) - 1) if m[3] else (c0, r0)
        c0, c1, r0, r1 = min(c0, c1), max(c0, c1), min(r0, r1), max(r0, r1)
        x, y = max(0.0, c0 / 10 - 0.02), max(0.0, r0 / 10 - 0.02)
        w, h = min(1.0, (c1 + 1) / 10 + 0.02) - x, min(1.0, (r1 + 1) / 10 + 0.02) - y
        if w * h <= 0.25:
            out.append([round(x, 4), round(y, 4), round(w, 4), round(h, 4)])
    return out[:5]


VERIFY = """Это кадры готового вертикального ролика. Видна ли на них где-либо читаемая реклама букмекера, казино, ставок,
промокод или название беттинг-бренда (FONBET, PARI, 1xBet, Winline и т.п.)? Размытые пятна не считаются.
Верни строго JSON: {"visible": true/false, "evidence": "что и где видно"}"""


async def verify_clean(client: httpx.AsyncClient, s: Settings, video: Path) -> dict:
    """Second look at the rendered clip: did the blur actually hide the ads?"""
    dur = await _duration(video)
    imgs = await frames(video, 0, dur, n=4)
    url, key, model = _endpoint(s)
    r = await client.post(url, timeout=60, headers={"Authorization": f"Bearer {key}"}, json={
        "model": model, "temperature": 0, "messages": [{"role": "user", "content": [{"type": "text", "text": VERIFY}] + [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in imgs]}]})
    r.raise_for_status()
    out = _json(r.json()["choices"][0]["message"]["content"])
    return {"ok": not out.get("visible", True), "evidence": str(out.get("evidence", ""))[:200]}


async def _duration(video: Path) -> float:
    p = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                             str(video), stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    return float(out.strip() or 30)


async def safe_verify_clean(*args) -> dict:
    try:
        return await asyncio.wait_for(verify_clean(*args), 60)
    except Exception as e:
        log.warning("проверка блюра не удалась: %s", str(e)[:200])
        return {"ok": False, "evidence": "проверка не удалась"}


def _endpoint(s: Settings) -> tuple[str, str, str]:
    if s.openai_api_key:
        return "https://api.openai.com/v1/chat/completions", s.openai_api_key, s.openai_judge_model
    return "https://openrouter.ai/api/v1/chat/completions", s.openrouter_api_key, s.judge_model


def merge_safety(heur: dict, ai: dict | None) -> dict:
    cats = {k: dict(v) for k, v in (heur.get("categories") or {}).items()}
    for k, v in ((ai or {}).get("safety") or {}).items():
        if k not in CATEGORIES or not isinstance(v, dict):
            continue
        lvl = int(v.get("level") or 0)
        if lvl > cats.get(k, {}).get("level", 0):
            cats[k] = {"level": lvl, "evidence": f"ИИ: {v.get('evidence', '')}"[:200]}
        elif k in cats and lvl == 0 and cats[k]["level"] <= 1:
            cats.pop(k)
    return {**heur, "categories": cats, "speech": {k: v["level"] for k, v in (heur.get("categories") or {}).items()
                                                   if str(v.get("evidence", "")).startswith("речь")},
            "source": "ai+heuristic" if ai else "heuristic"}


async def safe_judge(*args) -> dict | None:
    try:
        return await asyncio.wait_for(judge(*args), 75)
    except Exception as e:
        log.warning("ИИ-судья недоступен: %s", str(e)[:200])
        return None
