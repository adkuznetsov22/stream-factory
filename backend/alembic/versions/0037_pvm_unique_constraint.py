"""add unique constraint (platform, external_id, snapshot_at) to published_video_metrics

Revision ID: 0037_pvm_unique_constraint
Revises: 0036_seed_a01_script_analysis_tool
Create Date: 2026-02-08 15:08:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0037_pvm_unique_constraint"
down_revision: Union[str, None] = "0036_seed_a01_script_analysis_tool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_pvm_platform_extid_snap",
        "published_video_metrics",
        ["platform", "external_id", "snapshot_at"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_pvm_platform_extid_snap", "published_video_metrics", type_="unique")
