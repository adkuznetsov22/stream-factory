"""add last_metrics_json/last_metrics_at to publish_tasks + index on published_video_metrics

Revision ID: 0038_publish_task_last_metrics
Revises: 0037_pvm_unique_constraint
Create Date: 2026-02-08 15:09:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0038_publish_task_last_metrics"
down_revision: Union[str, None] = "0037_pvm_unique_constraint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Denormalized last-metrics cache on PublishTask
    op.add_column("publish_tasks", sa.Column("last_metrics_json", sa.JSON(), nullable=True))
    op.add_column("publish_tasks", sa.Column("last_metrics_at", sa.DateTime(timezone=True), nullable=True))

    # Composite index for "latest snapshot per task" queries (backup for full history)
    op.create_index(
        "ix_pvm_task_id_snapshot_at_desc",
        "published_video_metrics",
        ["task_id", sa.text("snapshot_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_pvm_task_id_snapshot_at_desc", "published_video_metrics")
    op.drop_column("publish_tasks", "last_metrics_at")
    op.drop_column("publish_tasks", "last_metrics_json")
