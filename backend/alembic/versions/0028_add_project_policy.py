"""add policy JSON to projects

Revision ID: 0028_add_project_policy
Revises: 0027_seed_generation_tools
Create Date: 2026-02-08 14:07:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028_add_project_policy"
down_revision: Union[str, None] = "0027_seed_generation_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "policy")
