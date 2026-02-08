"""
LLM Provider interface for content generation from briefs.

Swap the concrete implementation to connect a real model (OpenAI, Claude, local LLM).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class GeneratedContent:
    """Result of LLM content generation from a brief."""

    def __init__(
        self,
        hook: str,
        script: str,
        captions_draft: str,
        keywords: list[str],
        *,
        title_suggestion: str | None = None,
        model: str = "stub",
        raw: dict | None = None,
    ):
        self.hook = hook
        self.script = script
        self.captions_draft = captions_draft
        self.keywords = keywords
        self.title_suggestion = title_suggestion
        self.model = model
        self.raw = raw

    def to_meta(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "script": self.script,
            "captions_draft": self.captions_draft,
            "keywords": self.keywords,
            "title_suggestion": self.title_suggestion,
            "model": self.model,
            "generation_id": uuid.uuid4().hex[:12],
        }


class LLMProvider(ABC):
    """Abstract LLM provider. Implement `generate` to plug in a real model."""

    @abstractmethod
    async def generate(
        self,
        *,
        title: str,
        topic: str | None = None,
        description: str | None = None,
        style: str | None = None,
        tone: str | None = None,
        language: str = "ru",
        target_platform: str | None = None,
        target_duration_sec: int | None = None,
        reference_urls: list | None = None,
        llm_prompt_template: str | None = None,
    ) -> GeneratedContent:
        ...


class StubLLMProvider(LLMProvider):
    """Deterministic stub that returns plausible placeholder content."""

    async def generate(
        self,
        *,
        title: str,
        topic: str | None = None,
        description: str | None = None,
        style: str | None = None,
        tone: str | None = None,
        language: str = "ru",
        target_platform: str | None = None,
        target_duration_sec: int | None = None,
        reference_urls: list | None = None,
        llm_prompt_template: str | None = None,
    ) -> GeneratedContent:
        platform_tag = target_platform or "universal"
        dur = target_duration_sec or 60
        topic_text = topic or title

        hook = (
            f"[HOOK] Вы не поверите, что произошло с {topic_text}! "
            f"Смотрите до конца — будет неожиданный финал."
        )

        script = (
            f"[SCRIPT] Сценарий для {platform_tag} ({dur}с)\n\n"
            f"0:00–0:03 — Хук: {hook}\n"
            f"0:03–0:{dur//3:02d} — Введение в тему: {topic_text}\n"
            f"0:{dur//3:02d}–0:{2*dur//3:02d} — Основная часть\n"
            f"0:{2*dur//3:02d}–0:{dur:02d} — CTA и заключение\n"
        )
        if description:
            script += f"\nДоп. контекст: {description}\n"
        if style:
            script += f"Стиль: {style}\n"
        if tone:
            script += f"Тон: {tone}\n"

        captions_draft = (
            f"{hook}\n\n"
            f"Подробнее о {topic_text} в нашем новом видео!\n\n"
            f"#shorts #{platform_tag}"
        )

        keywords = [
            topic_text.split()[0] if topic_text else "контент",
            platform_tag,
            style or "видео",
            "trending",
            "viral",
        ]

        return GeneratedContent(
            hook=hook,
            script=script,
            captions_draft=captions_draft,
            keywords=keywords,
            title_suggestion=f"{topic_text} — {platform_tag} ({style or 'video'})",
            model="stub-v1",
            raw={"note": "stub generation, replace with real LLM"},
        )


# Singleton — swap this to use a real provider
_provider: LLMProvider = StubLLMProvider()


def get_llm_provider() -> LLMProvider:
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    global _provider
    _provider = provider
