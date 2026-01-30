"""create account_metrics_daily

Revision ID: 0003_metrics_daily
Revises: 0002_create_account_onboarding
Create Date: 2025-01-16 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_metrics_daily"
down_revision = "0002_create_account_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_metrics_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("subs", sa.BigInteger(), nullable=True),
        sa.Column("posts", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_account_metrics_daily_account_date", "account_metrics_daily", ["account_id", "date"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_account_metrics_daily_account_date", table_name="account_metrics_daily")
    op.drop_table("account_metrics_daily")
