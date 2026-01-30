"""add youtube_channel_id and metrics columns

Revision ID: 0006_add_youtube_channel_id
Revises: 0005_phone_email_meta
Create Date: 2025-01-16 19:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_add_youtube_channel_id"
down_revision = "0005_phone_email_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres-safe idempotent DDL
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS youtube_channel_id VARCHAR(255)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_accounts_youtube_channel_id "
        "ON social_accounts (youtube_channel_id)"
    )

    # metrics columns may already exist (created earlier) — add only if missing
    op.execute("ALTER TABLE account_metrics_daily ADD COLUMN IF NOT EXISTS subs BIGINT")
    op.execute("ALTER TABLE account_metrics_daily ADD COLUMN IF NOT EXISTS views BIGINT")
    op.execute("ALTER TABLE account_metrics_daily ADD COLUMN IF NOT EXISTS posts INTEGER")


def downgrade() -> None:
    # safe rollback
    op.execute("ALTER TABLE account_metrics_daily DROP COLUMN IF EXISTS posts")
    op.execute("ALTER TABLE account_metrics_daily DROP COLUMN IF EXISTS views")
    op.execute("ALTER TABLE account_metrics_daily DROP COLUMN IF EXISTS subs")

    op.execute("DROP INDEX IF EXISTS ix_social_accounts_youtube_channel_id")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS youtube_channel_id")
