"""add recommended_duration_sec to export_profiles + update seed data

Revision ID: 0032_export_profile_recommended_duration
Revises: 0031_seed_p01_publish_tool
Create Date: 2026-02-08 14:46:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0032_export_profile_recommended_duration"
down_revision: Union[str, None] = "0031_seed_p01_publish_tool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add recommended_duration_sec column
    op.add_column(
        "export_profiles",
        sa.Column("recommended_duration_sec", sa.Integer(), nullable=False, server_default="60"),
    )

    # Update max_duration_sec defaults for existing builtin profiles
    # max_duration_sec = platform hard limit, recommended_duration_sec = target for generation
    op.execute(sa.text("""
        UPDATE export_profiles
        SET max_duration_sec = 180, recommended_duration_sec = 55
        WHERE target_platform = 'tiktok' AND is_builtin = true
    """))
    op.execute(sa.text("""
        UPDATE export_profiles
        SET max_duration_sec = 180, recommended_duration_sec = 50
        WHERE target_platform = 'youtube_shorts' AND is_builtin = true
    """))
    op.execute(sa.text("""
        UPDATE export_profiles
        SET max_duration_sec = 90, recommended_duration_sec = 45
        WHERE target_platform = 'instagram_reels' AND is_builtin = true
    """))
    op.execute(sa.text("""
        UPDATE export_profiles
        SET max_duration_sec = 180, recommended_duration_sec = 55
        WHERE target_platform = 'vk_clips' AND is_builtin = true
    """))


def downgrade() -> None:
    op.drop_column("export_profiles", "recommended_duration_sec")
