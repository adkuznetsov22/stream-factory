"""tiktok and instagram via apify"""

from __future__ import annotations

from typing import Iterable

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "0015_tiktok_instagram_apify"
down_revision = "0014_youtube_content_v2"
branch_labels = None
depends_on = None


def _has_table(inspector: Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: Inspector, table_name: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not _has_table(inspector, "tiktok_profiles"):
        op.create_table(
            "tiktok_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), unique=True),
            sa.Column("username", sa.String(255), nullable=False, index=True),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("avatar_url", sa.String(512), nullable=True),
            sa.Column("followers", sa.BigInteger(), nullable=True),
            sa.Column("following", sa.BigInteger(), nullable=True),
            sa.Column("likes_total", sa.BigInteger(), nullable=True),
            sa.Column("posts_total", sa.Integer(), nullable=True),
            sa.Column("raw", sa.JSON(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True, index=True),
        )

    if not _has_table(inspector, "tiktok_videos"):
        op.create_table(
            "tiktok_videos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("video_id", sa.String(255), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("views", sa.BigInteger(), nullable=True),
            sa.Column("likes", sa.BigInteger(), nullable=True),
            sa.Column("comments", sa.BigInteger(), nullable=True),
            sa.Column("shares", sa.BigInteger(), nullable=True),
            sa.Column("thumbnail_url", sa.Text(), nullable=True),
            sa.Column("video_url", sa.Text(), nullable=True),
            sa.Column("permalink", sa.Text(), nullable=True),
            sa.Column("raw", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint("account_id", "video_id", name="uq_tiktok_videos_account_video"),
        )
        op.create_index("ix_tiktok_videos_account_id", "tiktok_videos", ["account_id"])

    if not _has_table(inspector, "instagram_profiles"):
        op.create_table(
            "instagram_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), unique=True),
            sa.Column("username", sa.String(255), nullable=False, index=True),
            sa.Column("full_name", sa.String(255), nullable=True),
            sa.Column("avatar_url", sa.String(512), nullable=True),
            sa.Column("followers", sa.BigInteger(), nullable=True),
            sa.Column("following", sa.BigInteger(), nullable=True),
            sa.Column("posts_total", sa.Integer(), nullable=True),
            sa.Column("raw", sa.JSON(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True, index=True),
        )

    if not _has_table(inspector, "instagram_posts"):
        op.create_table(
            "instagram_posts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_id", sa.String(255), nullable=False),
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("media_type", sa.String(32), nullable=True),
            sa.Column("views", sa.BigInteger(), nullable=True),
            sa.Column("likes", sa.BigInteger(), nullable=True),
            sa.Column("comments", sa.BigInteger(), nullable=True),
            sa.Column("thumbnail_url", sa.Text(), nullable=True),
            sa.Column("media_url", sa.Text(), nullable=True),
            sa.Column("permalink", sa.Text(), nullable=True),
            sa.Column("raw", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint("account_id", "post_id", name="uq_instagram_posts_account_post"),
        )
        op.create_index("ix_instagram_posts_account_id", "instagram_posts", ["account_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    for table in ("instagram_posts", "instagram_profiles", "tiktok_videos", "tiktok_profiles"):
        if _has_table(inspector, table):
            op.drop_table(table)
