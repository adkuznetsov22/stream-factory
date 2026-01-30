"""add virality_score and usage tracking fields

Revision ID: 0020_add_virality_score
Revises: 0019_publish_tasks_processing
Create Date: 2026-01-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0020_add_virality_score"
down_revision: Union[str, None] = "0019_publish_tasks_processing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # YouTube videos
    op.add_column("youtube_videos", sa.Column("virality_score", sa.Float(), nullable=True))
    op.add_column("youtube_videos", sa.Column("used_in_task_id", sa.Integer(), nullable=True))
    op.add_column("youtube_videos", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_youtube_videos_virality_score", "youtube_videos", ["virality_score"])

    # TikTok videos
    op.add_column("tiktok_videos", sa.Column("virality_score", sa.Float(), nullable=True))
    op.add_column("tiktok_videos", sa.Column("used_in_task_id", sa.Integer(), nullable=True))
    op.add_column("tiktok_videos", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tiktok_videos_virality_score", "tiktok_videos", ["virality_score"])

    # VK videos
    op.add_column("vk_videos", sa.Column("virality_score", sa.Float(), nullable=True))
    op.add_column("vk_videos", sa.Column("used_in_task_id", sa.Integer(), nullable=True))
    op.add_column("vk_videos", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_vk_videos_virality_score", "vk_videos", ["virality_score"])

    # VK clips
    op.add_column("vk_clips", sa.Column("virality_score", sa.Float(), nullable=True))
    op.add_column("vk_clips", sa.Column("used_in_task_id", sa.Integer(), nullable=True))
    op.add_column("vk_clips", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_vk_clips_virality_score", "vk_clips", ["virality_score"])

    # Instagram posts
    op.add_column("instagram_posts", sa.Column("virality_score", sa.Float(), nullable=True))
    op.add_column("instagram_posts", sa.Column("used_in_task_id", sa.Integer(), nullable=True))
    op.add_column("instagram_posts", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_instagram_posts_virality_score", "instagram_posts", ["virality_score"])


def downgrade() -> None:
    # Instagram posts
    op.drop_index("ix_instagram_posts_virality_score", table_name="instagram_posts")
    op.drop_column("instagram_posts", "used_at")
    op.drop_column("instagram_posts", "used_in_task_id")
    op.drop_column("instagram_posts", "virality_score")

    # VK clips
    op.drop_index("ix_vk_clips_virality_score", table_name="vk_clips")
    op.drop_column("vk_clips", "used_at")
    op.drop_column("vk_clips", "used_in_task_id")
    op.drop_column("vk_clips", "virality_score")

    # VK videos
    op.drop_index("ix_vk_videos_virality_score", table_name="vk_videos")
    op.drop_column("vk_videos", "used_at")
    op.drop_column("vk_videos", "used_in_task_id")
    op.drop_column("vk_videos", "virality_score")

    # TikTok videos
    op.drop_index("ix_tiktok_videos_virality_score", table_name="tiktok_videos")
    op.drop_column("tiktok_videos", "used_at")
    op.drop_column("tiktok_videos", "used_in_task_id")
    op.drop_column("tiktok_videos", "virality_score")

    # YouTube videos
    op.drop_index("ix_youtube_videos_virality_score", table_name="youtube_videos")
    op.drop_column("youtube_videos", "used_at")
    op.drop_column("youtube_videos", "used_in_task_id")
    op.drop_column("youtube_videos", "virality_score")
