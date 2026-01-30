"""add sync status and vk media type

Revision ID: 0012_vk_sync_status
Revises: 0011_vk_videos_and_clips
Create Date: 2025-12-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_vk_sync_status"
down_revision = "0011_vk_videos_and_clips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS sync_status VARCHAR(32)")
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS sync_error TEXT")
    op.execute("ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ")

    op.execute(
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS media_type VARCHAR(32) NOT NULL DEFAULT 'clip'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE vk_clips DROP COLUMN IF EXISTS media_type")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS last_synced_at")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS sync_error")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS sync_status")
