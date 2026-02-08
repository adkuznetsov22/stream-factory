"""seed P01_PUBLISH into tool_registry

Revision ID: 0031_seed_p01_publish_tool
Revises: 0030_publish_task_publish_fields
Create Date: 2026-02-08 14:32:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json


revision: str = "0031_seed_p01_publish_tool"
down_revision: Union[str, None] = "0030_publish_task_publish_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table = sa.table(
        "tool_registry",
        sa.column("tool_id", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("icon", sa.String),
        sa.column("inputs", sa.JSON),
        sa.column("outputs", sa.JSON),
        sa.column("default_params", sa.JSON),
        sa.column("param_schema", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("supports_preview", sa.Boolean),
        sa.column("supports_retry", sa.Boolean),
        sa.column("supports_manual_edit", sa.Boolean),
        sa.column("order_index", sa.Integer),
    )

    op.execute(
        table.insert().values(
            tool_id="P01_PUBLISH",
            name="Публикация на платформу",
            category="publishing",
            description=(
                "Публикует финальное видео на выбранную платформу (TikTok, YouTube, Instagram, VK) "
                "через PublisherAdapter. Обновляет статусы задачи и кандидата. "
                "Рекомендуется ставить последним шагом пресета после T18_QC."
            ),
            icon="Upload",
            inputs=json.dumps(["video_file"]),
            outputs=json.dumps(["published_url", "published_external_id"]),
            default_params=json.dumps({
                "auto_publish": True,
            }),
            param_schema=json.dumps({
                "type": "object",
                "properties": {
                    "auto_publish": {
                        "type": "boolean",
                        "title": "Автопубликация",
                        "description": "Публиковать автоматически после QC",
                        "default": True,
                    },
                },
            }),
            is_active=True,
            supports_preview=False,
            supports_retry=True,
            supports_manual_edit=False,
            order_index=999,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM tool_registry WHERE tool_id = 'P01_PUBLISH'")
    )
