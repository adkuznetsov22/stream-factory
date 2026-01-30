"""create account_onboarding table

Revision ID: 0002_create_account_onboarding
Revises: 0001_create_social_accounts
Create Date: 2025-01-16 15:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_create_account_onboarding"
down_revision = "0001_create_social_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_onboarding",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_onboarding")
