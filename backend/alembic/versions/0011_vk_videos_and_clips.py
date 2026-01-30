"""add vk videos and clips

Revision ID: 0011_vk_videos_and_clips
Revises: 0010_youtube_video_content_type
Create Date: 2025-12-17
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0011_vk_videos_and_clips"
down_revision = "0010_youtube_video_content_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vk_videos (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
            vk_owner_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            published_at TIMESTAMPTZ,
            duration_seconds INTEGER,
            views BIGINT,
            likes BIGINT,
            comments BIGINT,
            reposts BIGINT,
            thumbnail_url TEXT,
            permalink TEXT,
            raw JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_vk_videos_account_owner_video UNIQUE (account_id, vk_owner_id, video_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_videos_account_id ON vk_videos (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_videos_owner_id ON vk_videos (vk_owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_videos_date ON vk_videos (published_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vk_clips (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
            vk_owner_id INTEGER NOT NULL,
            clip_id INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            published_at TIMESTAMPTZ,
            duration_seconds INTEGER,
            views BIGINT,
            likes BIGINT,
            comments BIGINT,
            reposts BIGINT,
            thumbnail_url TEXT,
            permalink TEXT,
            raw JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_vk_clips_account_owner_clip UNIQUE (account_id, vk_owner_id, clip_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_clips_account_id ON vk_clips (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_clips_owner_id ON vk_clips (vk_owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_clips_date ON vk_clips (published_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vk_clips_date")
    op.execute("DROP INDEX IF EXISTS ix_vk_clips_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_vk_clips_account_id")
    op.execute("DROP TABLE IF EXISTS vk_clips")
    op.execute("DROP INDEX IF EXISTS ix_vk_videos_date")
    op.execute("DROP INDEX IF EXISTS ix_vk_videos_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_vk_videos_account_id")
    op.execute("DROP TABLE IF EXISTS vk_videos")
