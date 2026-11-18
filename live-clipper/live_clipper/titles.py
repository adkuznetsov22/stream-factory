import json
import logging
import re

import httpx

from .config import Settings

log = logging.getLogger(__name__)

PROMPT = """Ты делаешь вирусные шортсы по GTA 6 из стримов русскоязычных стримеров.
Стример: {name}. Название стрима: {stream_title}
Речь в клипе: {transcript}
Реакция чата: {chat}

Верни строго JSON: {{"overlay": "хук на видео, до 40 символов", "title": "заголовок ролика до 90 символов, с эмодзи", "description": "1-2 предложения"}}"""


PROFANITY = re.compile(r"\b\w*(бля|ху[йяеё]|пизд|еба|ёба|еб[уи]|сук[аи]|сучк|муда|пидор|залуп|дроч)\w*", re.IGNORECASE)


def clean(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", PROFANITY.sub("", text))
    text = re.sub(r"\s+([,.!?…])", r"\1", text)
    text = re.sub(r"[,.]+([?!…])", r"\1", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"(^|[.!?…]\s*),\s*", r"\1", text)
    return re.sub(r"^[\s,.!?…-]+", "", text).strip(" ,-")


def best_phrase(transcript: str) -> str:
    sentences = [x.strip(" ,") for x in re.findall(r"[^.!?…]+[.!?…]*", clean(transcript))]
    sentences = [x for x in sentences if len(x.split()) >= 2]
    if not sentences:
        return ""
    def rank(x: str) -> tuple:
        n = len(x.split())
        return (x[-1:] in "!?", 3 <= n <= 12, -abs(n - 7))
    return " ".join(max(sentences, key=rank).split()[:12])


def fallback(name: str, transcript: str) -> dict:
    phrase = best_phrase(transcript)
    words = phrase.split()
    overlay = " ".join(words[:6]).rstrip(",") if 2 <= len(words) else f"{name} в GTA 6"
    title = f"{name} в GTA 6" + (f": «{phrase}»" if phrase else " 😂")
    return {"overlay": overlay[:40], "title": title[:95], "description": clean(transcript)[:300] or phrase}


async def make_meta(client: httpx.AsyncClient, s: Settings, login: str, name: str, stream_title: str,
                    transcript: str, chat: list[str]) -> dict:
    """overlay (text on video), title and description; links and hashtags are added per platform template."""
    meta = fallback(name, transcript)
    if s.openrouter_api_key:
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
                json={
                    "model": s.openrouter_model,
                    "messages": [{"role": "user", "content": PROMPT.format(
                        name=name, stream_title=stream_title, transcript=transcript[:1500] or "-",
                        chat=" | ".join(chat[:40])[:1500] or "-",
                    )}],
                    "temperature": 0.8,
                },
                timeout=20,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
            meta.update({k: str(v) for k, v in data.items() if k in meta and v})
        except Exception:
            log.exception("llm title failed, using fallback")
    meta = {k: clean(v) for k, v in meta.items()}
    meta["title"] = meta["title"][:95]
    return meta
