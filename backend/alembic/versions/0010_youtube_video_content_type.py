"""add content type for youtube videos

Revision ID: 0010_youtube_video_content_type
Revises: 0009_vk_profile_and_posts
Create Date: 2025-12-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_youtube_video_content_type"
down_revision = "0009_vk_profile_and_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS content_type VARCHAR(32) NOT NULL DEFAULT 'video'"
    )
    op.execute(
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS live_status VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS duration_seconds INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE youtube_videos DROP COLUMN IF EXISTS duration_seconds")
    op.execute("ALTER TABLE youtube_videos DROP COLUMN IF EXISTS live_status")
    op.execute("ALTER TABLE youtube_videos DROP COLUMN IF EXISTS content_type")
