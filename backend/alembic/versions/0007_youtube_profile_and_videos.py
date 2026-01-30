"""youtube profile and videos tables

Revision ID: 0007_youtube_profile_and_videos
Revises: 0006_add_youtube_channel_id
Create Date: 2025-01-16 20:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007_youtube_profile_and_videos"
down_revision = "0006_add_youtube_channel_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_channels",
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("banner_url", sa.String(length=512), nullable=True),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("subscribers", sa.BigInteger(), nullable=True),
        sa.Column("views_total", sa.BigInteger(), nullable=True),
        sa.Column("videos_total", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_youtube_channels_channel_id", "youtube_channels", ["channel_id"], unique=False)
    op.create_index("ix_youtube_channels_last_synced_at", "youtube_channels", ["last_synced_at"], unique=False)

    op.create_table(
        "youtube_videos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True),
        sa.Column("video_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("privacy_status", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_youtube_videos_video_id", "youtube_videos", ["video_id"], unique=False)
    op.create_index("ix_youtube_videos_published_at", "youtube_videos", ["published_at"], unique=False)
    op.create_index("ix_youtube_videos_last_synced_at", "youtube_videos", ["last_synced_at"], unique=False)
    op.create_unique_constraint("uq_youtube_videos_account_video", "youtube_videos", ["account_id", "video_id"])


def downgrade() -> None:
    op.drop_constraint("uq_youtube_videos_account_video", "youtube_videos", type_="unique")
    op.drop_index("ix_youtube_videos_last_synced_at", table_name="youtube_videos")
    op.drop_index("ix_youtube_videos_published_at", table_name="youtube_videos")
    op.drop_index("ix_youtube_videos_video_id", table_name="youtube_videos")
    op.drop_table("youtube_videos")

    op.drop_index("ix_youtube_channels_last_synced_at", table_name="youtube_channels")
    op.drop_index("ix_youtube_channels_channel_id", table_name="youtube_channels")
    op.drop_table("youtube_channels")
