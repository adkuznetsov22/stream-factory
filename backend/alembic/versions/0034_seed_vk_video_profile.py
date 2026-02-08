"""seed VK Video export profile (16:9 landscape)

Revision ID: 0034_seed_vk_video_profile
Revises: 0033_export_profile_safe_area_mode
Create Date: 2026-02-08 14:46:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json


revision: str = "0034_seed_vk_video_profile"
down_revision: Union[str, None] = "0033_export_profile_safe_area_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table = sa.table(
        "export_profiles",
        sa.column("name", sa.String),
        sa.column("target_platform", sa.String),
        sa.column("max_duration_sec", sa.Integer),
        sa.column("recommended_duration_sec", sa.Integer),
        sa.column("width", sa.Integer),
        sa.column("height", sa.Integer),
        sa.column("fps", sa.Integer),
        sa.column("codec", sa.String),
        sa.column("video_bitrate", sa.String),
        sa.column("audio_bitrate", sa.String),
        sa.column("audio_sample_rate", sa.Integer),
        sa.column("safe_area", sa.JSON),
        sa.column("safe_area_mode", sa.String),
        sa.column("extra", sa.JSON),
        sa.column("is_builtin", sa.Boolean),
    )

    op.execute(
        table.insert().values(
            name="VK Video",
            target_platform="vk_video",
            max_duration_sec=7200,          # 2 часа — формально VK разрешает до 2 ГБ
            recommended_duration_sec=300,   # 5 минут — типичное короткое видео
            width=1920,
            height=1080,
            fps=30,
            codec="h264",
            video_bitrate="8M",
            audio_bitrate="192k",
            audio_sample_rate=44100,
            safe_area=json.dumps({
                "top": 0,
                "bottom": 80,
                "left": 0,
                "right": 0,
                "description": "Низ: плеер-контролы VK. Для 16:9 safe area минимальна.",
            }),
            safe_area_mode="platform_default",
            extra=json.dumps({
                "pixel_format": "yuv420p",
                "movflags": "+faststart",
                "max_file_size_mb": 2048,
                "aspect_ratio": "16:9",
            }),
            is_builtin=True,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM export_profiles WHERE target_platform = 'vk_video' AND is_builtin = true"))
