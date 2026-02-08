"""add pause/cancel/celery_task_id fields to publish_tasks

Revision ID: 0040_task_control_fields
Revises: 0039_project_meta_feed_settings
Create Date: 2026-02-08 17:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0040_task_control_fields"
down_revision: Union[str, None] = "0039_project_meta_feed_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("publish_tasks", sa.Column("pause_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("pause_reason", sa.Text(), nullable=True))
    op.add_column("publish_tasks", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("publish_tasks", sa.Column("celery_task_id", sa.Text(), nullable=True))

    op.create_index("ix_publish_tasks_status_pause", "publish_tasks", ["status", "pause_requested_at"])
    op.create_index("ix_publish_tasks_status_cancel", "publish_tasks", ["status", "cancel_requested_at"])


def downgrade() -> None:
    op.drop_index("ix_publish_tasks_status_cancel", table_name="publish_tasks")
    op.drop_index("ix_publish_tasks_status_pause", table_name="publish_tasks")
    op.drop_column("publish_tasks", "celery_task_id")
    op.drop_column("publish_tasks", "cancel_reason")
    op.drop_column("publish_tasks", "canceled_at")
    op.drop_column("publish_tasks", "cancel_requested_at")
    op.drop_column("publish_tasks", "pause_reason")
    op.drop_column("publish_tasks", "paused_at")
    op.drop_column("publish_tasks", "pause_requested_at")
