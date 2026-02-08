"""add priority field to publish_tasks

Revision ID: 0041_task_priority
Revises: 0040_task_control_fields
Create Date: 2026-02-08 17:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0041_task_priority"
down_revision: Union[str, None] = "0040_task_control_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("publish_tasks", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_publish_tasks_status_priority_created", "publish_tasks", ["status", "priority", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_publish_tasks_status_priority_created", table_name="publish_tasks")
    op.drop_column("publish_tasks", "priority")
