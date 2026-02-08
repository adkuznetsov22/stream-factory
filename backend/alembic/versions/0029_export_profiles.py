"""add export_profiles table and project.export_profile_id

Revision ID: 0029_export_profiles
Revises: 0028_add_project_policy
Create Date: 2026-02-08 14:13:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json


revision: str = "0029_export_profiles"
down_revision: Union[str, None] = "0028_add_project_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUILTIN_PROFILES = [
    {
        "name": "TikTok",
        "target_platform": "tiktok",
        "max_duration_sec": 180,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "codec": "h264",
        "video_bitrate": "6M",
        "audio_bitrate": "128k",
        "audio_sample_rate": 44100,
        "safe_area": json.dumps({
            "top": 150,
            "bottom": 270,
            "left": 40,
            "right": 40,
            "description": "Верх: имя автора/аватар. Низ: описание/кнопки/музыка."
        }),
        "extra": json.dumps({
            "pixel_format": "yuv420p",
            "movflags": "+faststart",
            "max_file_size_mb": 287,
        }),
        "is_builtin": True,
    },
    {
        "name": "YouTube Shorts",
        "target_platform": "youtube_shorts",
        "max_duration_sec": 60,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "codec": "h264",
        "video_bitrate": "8M",
        "audio_bitrate": "192k",
        "audio_sample_rate": 48000,
        "safe_area": json.dumps({
            "top": 120,
            "bottom": 200,
            "left": 40,
            "right": 40,
            "description": "Верх: заголовок канала. Низ: подписка/лайк/комменты."
        }),
        "extra": json.dumps({
            "pixel_format": "yuv420p",
            "movflags": "+faststart",
            "max_file_size_mb": 256,
        }),
        "is_builtin": True,
    },
    {
        "name": "Instagram Reels",
        "target_platform": "instagram_reels",
        "max_duration_sec": 90,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "codec": "h264",
        "video_bitrate": "5M",
        "audio_bitrate": "128k",
        "audio_sample_rate": 44100,
        "safe_area": json.dumps({
            "top": 120,
            "bottom": 320,
            "left": 30,
            "right": 30,
            "description": "Верх: имя/аватар. Низ: описание/аудио/кнопки. Больше safe zone снизу."
        }),
        "extra": json.dumps({
            "pixel_format": "yuv420p",
            "movflags": "+faststart",
            "max_file_size_mb": 250,
            "cover_frame": True,
        }),
        "is_builtin": True,
    },
    {
        "name": "VK Clips",
        "target_platform": "vk_clips",
        "max_duration_sec": 180,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "codec": "h264",
        "video_bitrate": "6M",
        "audio_bitrate": "192k",
        "audio_sample_rate": 44100,
        "safe_area": json.dumps({
            "top": 100,
            "bottom": 250,
            "left": 40,
            "right": 40,
            "description": "Верх: аватар/имя. Низ: описание/лайки/комменты."
        }),
        "extra": json.dumps({
            "pixel_format": "yuv420p",
            "movflags": "+faststart",
            "max_file_size_mb": 2048,
        }),
        "is_builtin": True,
    },
]


def upgrade() -> None:
    op.create_table(
        "export_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("target_platform", sa.String(32), nullable=False),
        sa.Column("max_duration_sec", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("codec", sa.String(16), nullable=False, server_default="h264"),
        sa.Column("video_bitrate", sa.String(16), nullable=False, server_default="8M"),
        sa.Column("audio_bitrate", sa.String(16), nullable=False, server_default="192k"),
        sa.Column("audio_sample_rate", sa.Integer(), nullable=False, server_default="44100"),
        sa.Column("safe_area", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    table = sa.table(
        "export_profiles",
        sa.column("name", sa.String),
        sa.column("target_platform", sa.String),
        sa.column("max_duration_sec", sa.Integer),
        sa.column("width", sa.Integer),
        sa.column("height", sa.Integer),
        sa.column("fps", sa.Integer),
        sa.column("codec", sa.String),
        sa.column("video_bitrate", sa.String),
        sa.column("audio_bitrate", sa.String),
        sa.column("audio_sample_rate", sa.Integer),
        sa.column("safe_area", sa.JSON),
        sa.column("extra", sa.JSON),
        sa.column("is_builtin", sa.Boolean),
    )

    for profile in BUILTIN_PROFILES:
        op.execute(table.insert().values(**profile))

    op.add_column(
        "projects",
        sa.Column(
            "export_profile_id",
            sa.Integer(),
            sa.ForeignKey("export_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "export_profile_id")
    op.drop_table("export_profiles")
