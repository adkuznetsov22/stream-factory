"""add topic, target_duration_sec, reference_urls, llm_prompt_template to briefs

Revision ID: 0026_brief_extra_fields
Revises: 0025_briefs_candidate_origin
Create Date: 2026-02-08 13:54:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_brief_extra_fields"
down_revision: Union[str, None] = "0025_briefs_candidate_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("briefs", sa.Column("topic", sa.Text(), nullable=True))
    op.add_column("briefs", sa.Column("target_duration_sec", sa.Integer(), nullable=True))
    op.add_column("briefs", sa.Column("reference_urls", sa.JSON(), nullable=True))
    op.add_column("briefs", sa.Column("llm_prompt_template", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("briefs", "llm_prompt_template")
    op.drop_column("briefs", "reference_urls")
    op.drop_column("briefs", "target_duration_sec")
    op.drop_column("briefs", "topic")
