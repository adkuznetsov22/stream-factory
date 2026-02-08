"""seed A01_SCRIPT_ANALYSIS tool in tool_registry

Revision ID: 0036_seed_a01_script_analysis_tool
Revises: 0035_published_video_metrics
Create Date: 2026-02-08 15:03:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0036_seed_a01_script_analysis_tool"
down_revision: Union[str, None] = "0035_published_video_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table = sa.table(
        "tool_registry",
        sa.column("tool_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("category", sa.String),
        sa.column("version", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("params_schema", sa.JSON),
    )
    op.execute(
        table.insert().values(
            tool_id="A01_SCRIPT_ANALYSIS",
            name="Script Analysis",
            description=(
                "Analyze Whisper transcript to extract reusable script patterns: "
                "hook, structure, theses, CTA, retention pattern. "
                "Saves to candidate.meta.script_analysis for G01_SCRIPT."
            ),
            category="analysis",
            version="1.0.0",
            is_active=True,
            params_schema={
                "type": "object",
                "properties": {
                    "max_theses": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of key theses to extract",
                    },
                },
            },
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM tool_registry WHERE tool_id = 'A01_SCRIPT_ANALYSIS'"))
