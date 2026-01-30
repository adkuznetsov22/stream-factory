"""add requires_moderation to preset_steps

Revision ID: 0023
Revises: 0022_seed_tools_full
Create Date: 2026-01-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_add_requires_moderation"
down_revision = "0022_seed_tools_full"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preset_steps",
        sa.Column("requires_moderation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("preset_steps", "requires_moderation")
