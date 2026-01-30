"""youtube content v2

Revision ID: 0014_youtube_content_v2
Revises: 0013_vk_hotfix_finalize_schema
Create Date: 2025-12-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_youtube_content_v2"
down_revision = "0013_vk_hotfix_finalize_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    stmts = [
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS content_type VARCHAR(16) NOT NULL DEFAULT 'video'",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS live_status VARCHAR(16)",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS scheduled_start_at TIMESTAMPTZ",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS actual_start_at TIMESTAMPTZ",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS actual_end_at TIMESTAMPTZ",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS permalink TEXT",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS raw JSONB",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS likes BIGINT",
        "ALTER TABLE youtube_videos ADD COLUMN IF NOT EXISTS comments BIGINT",
    ]
    for stmt in stmts:
        op.execute(stmt)


def downgrade() -> None:
    stmts = [
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS comments",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS likes",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS raw",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS permalink",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS actual_end_at",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS actual_start_at",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS scheduled_start_at",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS live_status",
        "ALTER TABLE youtube_videos DROP COLUMN IF EXISTS content_type",
    ]
    for stmt in stmts:
        op.execute(stmt)
