"""add briefs table and candidate origin/brief_id/meta fields

Revision ID: 0025_briefs_candidate_origin
Revises: 0024_create_candidates
Create Date: 2026-02-08 13:51:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_briefs_candidate_origin"
down_revision: Union[str, None] = "0024_create_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create briefs table
    op.create_table(
        "briefs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_platform", sa.String(32), nullable=True),
        sa.Column("style", sa.String(64), nullable=True),
        sa.Column("tone", sa.String(64), nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("prompts", sa.JSON(), nullable=True),
        sa.Column("assets", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_briefs_project_id", "briefs", ["project_id"])

    # Add new columns to candidates
    op.add_column("candidates", sa.Column("origin", sa.String(16), nullable=False, server_default="REPURPOSE"))
    op.add_column("candidates", sa.Column("brief_id", sa.Integer(), nullable=True))
    op.add_column("candidates", sa.Column("meta", sa.JSON(), nullable=True))

    op.create_index("ix_candidates_origin", "candidates", ["origin"])
    op.create_foreign_key(
        "fk_candidates_brief_id", "candidates", "briefs",
        ["brief_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_candidates_brief_id", "candidates", type_="foreignkey")
    op.drop_index("ix_candidates_origin", table_name="candidates")
    op.drop_column("candidates", "meta")
    op.drop_column("candidates", "brief_id")
    op.drop_column("candidates", "origin")
    op.drop_index("ix_briefs_project_id", table_name="briefs")
    op.drop_table("briefs")
