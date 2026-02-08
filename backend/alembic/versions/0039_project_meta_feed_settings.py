"""add meta and feed_settings JSON columns to projects

Revision ID: 0039_project_meta_feed_settings
Revises: 0038_publish_task_last_metrics
Create Date: 2026-02-08 15:33:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0039_project_meta_feed_settings"
down_revision: Union[str, None] = "0038_publish_task_last_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("meta", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("feed_settings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "feed_settings")
    op.drop_column("projects", "meta")
