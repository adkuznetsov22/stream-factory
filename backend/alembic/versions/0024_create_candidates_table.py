"""create candidates table

Revision ID: 0024_create_candidates
Revises: 0023_add_requires_moderation
Create Date: 2026-02-08 13:38:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024_create_candidates"
down_revision: Union[str, None] = "0023_add_requires_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_video_id", sa.String(512), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        # Metrics
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("subscribers", sa.BigInteger(), nullable=True),
        # Scoring
        sa.Column("virality_score", sa.Float(), nullable=True),
        sa.Column("virality_factors", sa.JSON(), nullable=True),
        # Status
        sa.Column("status", sa.String(16), nullable=False, server_default="NEW"),
        sa.Column("manual_rating", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Link
        sa.Column("linked_publish_task_id", sa.Integer(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_publish_task_id"], ["publish_tasks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "platform", "platform_video_id", name="uq_candidate_video"),
    )
    op.create_index("ix_candidates_project_id", "candidates", ["project_id"])
    op.create_index("ix_candidates_virality_score", "candidates", ["virality_score"])
    op.create_index("ix_candidates_status", "candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_candidates_status", table_name="candidates")
    op.drop_index("ix_candidates_virality_score", table_name="candidates")
    op.drop_index("ix_candidates_project_id", table_name="candidates")
    op.drop_table("candidates")
