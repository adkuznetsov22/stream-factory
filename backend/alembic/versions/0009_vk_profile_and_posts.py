"""add vk profile and posts

Revision ID: 0009_vk_profile_and_posts
Revises: 0008_account_purchase_fields
Create Date: 2025-12-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_vk_profile_and_posts"
down_revision = "0008_account_purchase_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vk_profiles (
            id SERIAL PRIMARY KEY,
            account_id INTEGER UNIQUE NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
            vk_owner_id INTEGER NOT NULL,
            screen_name VARCHAR(255),
            name VARCHAR(255) NOT NULL,
            photo_200 VARCHAR(512),
            is_group BOOLEAN NOT NULL DEFAULT FALSE,
            country VARCHAR(128),
            description TEXT,
            members_count INTEGER,
            followers_count INTEGER,
            last_synced_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vk_profiles_vk_owner_id ON vk_profiles (vk_owner_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vk_posts (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
            vk_owner_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            published_at TIMESTAMPTZ,
            text TEXT,
            permalink VARCHAR(512),
            views INTEGER,
            likes INTEGER,
            reposts INTEGER,
            comments INTEGER,
            attachments_count INTEGER,
            raw JSONB,
            last_synced_at TIMESTAMPTZ,
            CONSTRAINT uq_vk_posts_account_post UNIQUE (account_id, post_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_posts_account_id ON vk_posts (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vk_posts_published_at ON vk_posts (published_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vk_posts_published_at")
    op.execute("DROP INDEX IF EXISTS ix_vk_posts_account_id")
    op.execute("DROP TABLE IF EXISTS vk_posts")
    op.execute("DROP INDEX IF EXISTS ix_vk_profiles_vk_owner_id")
    op.execute("DROP TABLE IF EXISTS vk_profiles")
