"""Per-target content strategy: safety rules per category, profanity handling, theme priorities."""
import copy
import re

CATEGORIES = {
    "sexual": "18+ и обнажёнка",
    "sexual_hint": "намёки и юмор 18+",
    "gambling": "казино, ставки, промокоды",
    "politics": "политика и реальные политики",
    "extremism": "экстремизм, терроризм",
    "drugs": "наркотики",
    "hate": "оскорбления по нации, религии, ориентации",
    "violence_real": "реальное насилие (не игровое)",
    "personal_data": "личные данные на экране",
    "music": "чужая музыка (риск Content ID)",
    "unchecked": "не проверено ИИ",
}
THEMES = {"funny": "смешно", "fail": "фейл", "epic": "эпик, скилл", "drama": "конфликт, драма",
          "reaction": "реакция стримера", "wholesome": "мило, душевно", "scary": "испуг, скример"}
ACTIONS = ("allow", "review", "block", "blur")
BLURRABLE = {"gambling"}

PRESETS = {
    "strict": {"profanity": "block", "categories": {c: "block" for c in CATEGORIES} | {"music": "review"},
               "min_virality": 60, "review_level": 1},
    "moderate": {"profanity": "mute", "categories": {c: "block" for c in CATEGORIES} | {"sexual_hint": "allow", "music": "review", "violence_real": "review",
                                                                                         "gambling": "blur"},
                 "min_virality": 50, "review_level": 2},
    "soft": {"profanity": "allow", "categories": {c: "block" for c in CATEGORIES} | {"sexual_hint": "allow", "music": "allow",
                                                                                     "violence_real": "review", "personal_data": "review",
                                                                                     "gambling": "blur"},
             "min_virality": 40, "review_level": 2},
}
DEFAULT = {"preset": "moderate", **PRESETS["moderate"], "themes": {t: 1.0 for t in THEMES}, "streamers": {},
           "explore": 0.1}


def normalize(p: dict | None) -> dict:
    out = copy.deepcopy(DEFAULT)
    if not p:
        return out
    if p.get("preset") in PRESETS:
        out.update(copy.deepcopy(PRESETS[p["preset"]]), preset=p["preset"])
    for k in ("profanity", "min_virality", "explore", "preset", "review_level"):
        if k in p:
            out[k] = p[k]
    out["categories"].update({k: v for k, v in (p.get("categories") or {}).items() if k in CATEGORIES and v in ACTIONS and (v != "blur" or k in BLURRABLE)})
    out["themes"].update({k: max(0.0, min(float(v), 3.0)) for k, v in (p.get("themes") or {}).items() if k in THEMES})
    out["streamers"] = {k.lower(): max(0.0, min(float(v), 3.0)) for k, v in (p.get("streamers") or {}).items()}
    if out["profanity"] not in ("allow", "mute", "block"):
        out["profanity"] = "mute"
    return out


# ---- heuristic safety (works without the AI judge; the judge refines it) ------------------------
RULES = {
    "sexual": r"(голая|голый|голые|сиськ|титьк|порн|секс\b|трах|минет|стриптиз|nsfw|нюдс)",
    "sexual_hint": r"(стрип|стрипух|поцелу|сосать|сосёт|жоп|попк|шлюх|грязнул)",
    "gambling": r"(казино|казик|ставк|букмекер|1xbet|1хбет|фонбет|винлайн|pin-?up|пинап|промокод|слоты|рулетк|депозит|дэп\b|занос)",
    "politics": r"(путин|зеленск|навальн|байден|трамп|сво\b|мобилизац|украин|выбор[ыа]|госдум|кремл|пригожин)",
    "extremism": r"(теракт|террорист|игил|джихад|взорвать (школ|метро)|нацист|зиг\b|хайль)",
    "drugs": r"(наркот|героин|кокаин|меф\b|мефедрон|закладк|травк|гашиш|шишк[иу] курить|соль\b)",
    "hate": r"(хохл|чурк|хач\b|жид\b|пидор|пидр|негр|нигер|nigg|даун\b|аутист)",
}
RULES = {k: re.compile(v, re.IGNORECASE) for k, v in RULES.items()}


def heuristic_safety(transcript: str, chat: list[str], titles: list[str]) -> dict:
    """Levels 0..3 per category with evidence. Speech counts most, viewer clip titles next, chat least."""
    from .titles import PROFANITY
    cats = {}
    for cat, rx in RULES.items():
        speech = rx.findall(transcript or "")
        head = [t for t in titles if rx.search(t or "")]
        crowd = sum(1 for m in chat if rx.search(m))
        level = 3 if len(speech) >= 2 else 2 if speech or head else 1 if crowd >= 3 else 0
        if level:
            ev = (speech[:3] and f"речь: {', '.join(map(str, speech[:3]))}") or (head and f"клип зрителей: «{head[0]}»") \
                or f"чат: {crowd} сообщ."
            cats[cat] = {"level": level, "evidence": ev}
    prof = len(PROFANITY.findall(transcript or ""))
    return {"categories": cats, "profanity": prof, "source": "heuristic"}


def decide(policy: dict, clip: dict) -> dict:
    """allow / review / block for this target, plus the rank used to pick between clips."""
    p = normalize(policy)
    safety = clip.get("safety") or {}
    judge = clip.get("judge") or {}
    reasons, action = [], "allow"
    for cat, info in (safety.get("categories") or {}).items():
        lvl = info.get("level", 0)
        rule = p["categories"].get(cat, "review")
        if rule == "blur":
            check = safety.get("blur_check") or {}
            if (safety.get("speech") or {}).get(cat, 0) >= 2:
                rule = "block"
            elif check.get("ok"):
                continue
            elif lvl >= p["review_level"]:
                action = "block" if action == "block" else "review"
                reasons.append(f"{CATEGORIES.get(cat, cat)}: замазать не удалось — {check.get('evidence') or info.get('evidence', '')}")
                continue
        if lvl >= 2 and rule == "block":
            action, _ = "block", reasons.append(f"{CATEGORIES.get(cat, cat)}: {info.get('evidence', '')}")
        elif lvl >= p["review_level"] and rule != "allow" and action != "block":
            action, _ = "review", reasons.append(f"возможно {CATEGORIES.get(cat, cat)}: {info.get('evidence', '')}")
    if safety.get("profanity") and p["profanity"] == "block":
        action, _ = "block", reasons.append(f"мат в речи ({safety['profanity']})")
    virality = judge.get("virality")
    if virality is None:
        virality = min(100.0, 25 + (clip.get("score") or 0) * 5)
    themes = judge.get("themes") or {}
    theme_w = max((p["themes"].get(t, 1.0) for t, v in themes.items() if v >= 0.5), default=1.0)
    rank = virality * theme_w * p["streamers"].get(clip.get("login", ""), 1.0)
    if action == "allow" and virality < p["min_virality"]:
        action, _ = "skip", reasons.append(f"виральность {virality:.0f} < {p['min_virality']}")
    return {"action": action, "reasons": reasons, "rank": round(rank, 1), "virality": round(virality, 1),
            "mute": p["profanity"] == "mute" and bool(safety.get("profanity"))}
