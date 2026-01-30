"""publish task processing fields

Revision ID: 0019_publish_tasks_processing
Revises: 0018_presets_and_tools
Create Date: 2025-12-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019_publish_tasks_processing"
down_revision: Union[str, None] = "0018_presets_and_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("publish_tasks", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("processing_finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_tasks", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("publish_tasks", sa.Column("preset_id", sa.Integer(), nullable=True))
    op.add_column(
        "publish_tasks",
        sa.Column(
            "artifacts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "publish_tasks",
        sa.Column(
            "dag_debug",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("publish_tasks", "dag_debug")
    op.drop_column("publish_tasks", "artifacts")
    op.drop_column("publish_tasks", "preset_id")
    op.drop_column("publish_tasks", "error_message")
    op.drop_column("publish_tasks", "processing_finished_at")
    op.drop_column("publish_tasks", "processing_started_at")
