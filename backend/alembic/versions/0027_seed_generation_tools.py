"""seed G01_SCRIPT, G02_CAPTIONS, G03_TTS into tool_registry

Revision ID: 0027_seed_generation_tools
Revises: 0026_brief_extra_fields
Create Date: 2026-02-08 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json


revision: str = "0027_seed_generation_tools"
down_revision: Union[str, None] = "0026_brief_extra_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOOLS = [
    {
        "tool_id": "G01_SCRIPT",
        "name": "Генерация сценария",
        "category": "generation",
        "description": "Генерирует структурированный сценарий из брифа: hook, сегменты, CTA, ключевые слова",
        "icon": "FileText",
        "inputs": json.dumps(["candidate_meta", "brief_data"]),
        "outputs": json.dumps(["script_json", "script_txt"]),
        "default_params": json.dumps({
            "style": "educational",
            "tone": "casual",
            "target_duration_sec": 60,
            "language": "ru",
        }),
        "param_schema": json.dumps({
            "type": "object",
            "properties": {
                "topic": {"type": "string", "title": "Тема"},
                "style": {
                    "type": "select", "title": "Стиль",
                    "default": "educational",
                    "enum": ["educational", "entertaining", "review", "tutorial", "story", "news"],
                },
                "tone": {
                    "type": "select", "title": "Тон",
                    "default": "casual",
                    "enum": ["casual", "formal", "humorous", "serious", "inspirational"],
                },
                "target_duration_sec": {
                    "type": "number", "title": "Длительность (сек)",
                    "default": 60, "minimum": 10, "maximum": 600,
                },
                "language": {
                    "type": "select", "title": "Язык", "default": "ru",
                    "enum": ["ru", "en", "es", "de", "fr"],
                },
            },
        }),
        "is_active": True,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": True,
        "order_index": 101,
    },
    {
        "tool_id": "G02_CAPTIONS",
        "name": "Генерация субтитров",
        "category": "generation",
        "description": "Создаёт SRT/ASS субтитры из сценария без Whisper — на основе сегментов скрипта",
        "icon": "Subtitles",
        "inputs": json.dumps(["script_data"]),
        "outputs": json.dumps(["captions_srt", "captions_ass"]),
        "default_params": json.dumps({
            "format": "srt",
            "max_chars_per_line": 42,
            "also_ass": False,
        }),
        "param_schema": json.dumps({
            "type": "object",
            "properties": {
                "format": {
                    "type": "select", "title": "Формат",
                    "default": "srt", "enum": ["srt", "ass"],
                },
                "max_chars_per_line": {
                    "type": "number", "title": "Макс. символов в строке",
                    "default": 42, "minimum": 20, "maximum": 80,
                },
                "also_ass": {"type": "boolean", "title": "Также создать ASS", "default": False},
                "font": {"type": "string", "title": "Шрифт", "default": "Arial"},
                "font_size": {
                    "type": "number", "title": "Размер шрифта",
                    "default": 48, "minimum": 16, "maximum": 100,
                },
                "position": {
                    "type": "select", "title": "Позиция",
                    "default": "bottom", "enum": ["bottom", "top", "center"],
                },
            },
        }),
        "is_active": True,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "order_index": 102,
    },
    {
        "tool_id": "G03_TTS",
        "name": "Озвучка (TTS)",
        "category": "generation",
        "description": "Генерация голосовой озвучки из текста сценария (edge_tts / stub)",
        "icon": "Volume2",
        "inputs": json.dumps(["script_text"]),
        "outputs": json.dumps(["voice_mp3"]),
        "default_params": json.dumps({
            "provider": "stub",
            "voice": "ru-RU-DmitryNeural",
        }),
        "param_schema": json.dumps({
            "type": "object",
            "properties": {
                "provider": {
                    "type": "select", "title": "Провайдер",
                    "default": "stub", "enum": ["stub", "edge_tts", "elevenlabs"],
                },
                "voice": {"type": "string", "title": "Голос", "default": "ru-RU-DmitryNeural"},
            },
        }),
        "is_active": True,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "order_index": 103,
    },
]


def upgrade() -> None:
    table = sa.table(
        "tool_registry",
        sa.column("tool_id", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("icon", sa.String),
        sa.column("inputs", sa.JSON),
        sa.column("outputs", sa.JSON),
        sa.column("default_params", sa.JSON),
        sa.column("param_schema", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("supports_preview", sa.Boolean),
        sa.column("supports_retry", sa.Boolean),
        sa.column("supports_manual_edit", sa.Boolean),
        sa.column("order_index", sa.Integer),
    )
    for tool in TOOLS:
        op.execute(
            table.insert().values(
                tool_id=tool["tool_id"],
                name=tool["name"],
                category=tool["category"],
                description=tool["description"],
                icon=tool["icon"],
                inputs=tool["inputs"],
                outputs=tool["outputs"],
                default_params=tool["default_params"],
                param_schema=tool["param_schema"],
                is_active=tool["is_active"],
                supports_preview=tool["supports_preview"],
                supports_retry=tool["supports_retry"],
                supports_manual_edit=tool["supports_manual_edit"],
                order_index=tool["order_index"],
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM tool_registry WHERE tool_id IN ('G01_SCRIPT', 'G02_CAPTIONS', 'G03_TTS')")
    )
