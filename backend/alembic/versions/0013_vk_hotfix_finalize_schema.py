"""vk hotfix finalize schema

Revision ID: 0013_vk_hotfix_finalize_schema
Revises: 0012_vk_sync_status
Create Date: 2025-12-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_vk_hotfix_finalize_schema"
down_revision = "0012_vk_sync_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # rename owner_id -> vk_owner_id in vk_videos if needed
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='vk_videos' AND column_name='owner_id'
            )
            AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='vk_videos' AND column_name='vk_owner_id'
            ) THEN
                ALTER TABLE vk_videos RENAME COLUMN owner_id TO vk_owner_id;
            END IF;
        END$$;
        """
    )
    # ensure columns exist in vk_videos
    for stmt in [
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS vk_full_id VARCHAR(255)",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS likes BIGINT",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS comments BIGINT",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS reposts BIGINT",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS thumbnail_url TEXT",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS permalink TEXT",
        "ALTER TABLE vk_videos ADD COLUMN IF NOT EXISTS raw JSONB",
    ]:
        op.execute(stmt)

    # rename owner_id -> vk_owner_id in vk_clips if needed
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='vk_clips' AND column_name='owner_id'
            )
            AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='vk_clips' AND column_name='vk_owner_id'
            ) THEN
                ALTER TABLE vk_clips RENAME COLUMN owner_id TO vk_owner_id;
            END IF;
        END$$;
        """
    )
    # ensure columns exist in vk_clips
    for stmt in [
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS media_type VARCHAR(32) NOT NULL DEFAULT 'clip'",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS vk_full_id VARCHAR(255)",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS likes BIGINT",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS comments BIGINT",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS reposts BIGINT",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS thumbnail_url TEXT",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS permalink TEXT",
        "ALTER TABLE vk_clips ADD COLUMN IF NOT EXISTS raw JSONB",
    ]:
        op.execute(stmt)

    # backfill VK accounts slug/login/handle/url
    op.execute(
        """
        WITH vk_accounts AS (
            SELECT id, login, handle, url
            FROM social_accounts
            WHERE platform = 'VK'
        ), normalized AS (
            SELECT
                id,
                lower(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    coalesce(NULLIF(login,''), NULLIF(url,''), NULLIF(handle,'')),
                                    '^@', '', 'g'
                                ),
                                '^(https?://)', '', 'gi'
                            ),
                            '^(m\\.)?vk\\.com/', '', 'gi'
                        ),
                        '[^A-Za-z0-9_.-]+', '', 'g'
                    )
                ) AS slug
            FROM vk_accounts
        )
        UPDATE social_accounts s
        SET
            login = n.slug,
            handle = '@' || n.slug,
            url = 'https://vk.com/' || n.slug
        FROM normalized n
        WHERE s.id = n.id AND n.slug IS NOT NULL AND n.slug <> '';
        """
    )


def downgrade() -> None:
    # no-op: keep schema as finalized
    pass
