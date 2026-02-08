"""add published_video_metrics table

Revision ID: 0035_published_video_metrics
Revises: 0034_seed_vk_video_profile
Create Date: 2026-02-08 14:56:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0035_published_video_metrics"
down_revision: Union[str, None] = "0034_seed_vk_video_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "published_video_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("publish_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=True),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("hours_since_publish", sa.Integer(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("published_video_metrics")
