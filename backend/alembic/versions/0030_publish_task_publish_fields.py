"""add publishing result fields to publish_tasks

Revision ID: 0030_publish_task_publish_fields
Revises: 0029_export_profiles
Create Date: 2026-02-08 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030_publish_task_publish_fields"
down_revision: Union[str, None] = "0029_export_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("publish_tasks", sa.Column("published_url", sa.Text(), nullable=True))
    op.add_column("publish_tasks", sa.Column("published_external_id", sa.Text(), nullable=True))
    op.add_column("publish_tasks", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("publish_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("publish_tasks", "publish_error")
    op.drop_column("publish_tasks", "published_at")
    op.drop_column("publish_tasks", "published_external_id")
    op.drop_column("publish_tasks", "published_url")
