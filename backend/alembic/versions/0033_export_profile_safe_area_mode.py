"""add safe_area_mode to export_profiles

Revision ID: 0033_export_profile_safe_area_mode
Revises: 0032_export_profile_recommended_duration
Create Date: 2026-02-08 14:46:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0033_export_profile_safe_area_mode"
down_revision: Union[str, None] = "0032_export_profile_recommended_duration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "export_profiles",
        sa.Column("safe_area_mode", sa.String(32), nullable=False, server_default="platform_default"),
    )
    # All existing builtin profiles use platform defaults
    op.execute(sa.text("""
        UPDATE export_profiles
        SET safe_area_mode = 'platform_default'
        WHERE is_builtin = true
    """))


def downgrade() -> None:
    op.drop_column("export_profiles", "safe_area_mode")
