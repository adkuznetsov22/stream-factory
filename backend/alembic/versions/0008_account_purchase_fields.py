"""add purchase/login fields and youtube video unique

Revision ID: 0008_account_purchase_fields
Revises: 0007_youtube_profile_and_videos
Create Date: 2025-12-17
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0008_account_purchase_fields"
down_revision = "0007_youtube_profile_and_videos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS login VARCHAR(255)")
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS purchase_price NUMERIC(12,2)")
    op.execute(
        "ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS purchase_currency VARCHAR(8) DEFAULT 'RUB'"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_social_accounts_platform_login') THEN "
        "ALTER TABLE social_accounts ADD CONSTRAINT uq_social_accounts_platform_login UNIQUE (platform, login); "
        "END IF; END $$;"
    )

    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_youtube_videos_account_video') THEN "
        "ALTER TABLE youtube_videos ADD CONSTRAINT uq_youtube_videos_account_video UNIQUE (account_id, video_id); "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_youtube_videos_account_video') THEN "
        "ALTER TABLE youtube_videos DROP CONSTRAINT uq_youtube_videos_account_video; "
        "END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_social_accounts_platform_login') THEN "
        "ALTER TABLE social_accounts DROP CONSTRAINT uq_social_accounts_platform_login; "
        "END IF; END $$;"
    )
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS purchase_currency")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS purchase_price")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS login")
