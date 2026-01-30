"""presets and tool registry

Revision ID: 0018_presets_and_tools
Revises: 0017_add_project_id_to_social_accounts
Create Date: 2025-12-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0018_presets_and_tools"
down_revision: Union[str, None] = "0017_proj_account_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=:tname)"),
        {"tname": table_name},
    )
    return bool(res.scalar())


def _column_exists(conn, table: str, column: str) -> bool:
    res = conn.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name=:tname AND column_name=:cname
            )
            """
        ),
        {"tname": table, "cname": column},
    )
    return bool(res.scalar())


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "tool_registry"):
        op.create_table(
            "tool_registry",
            sa.Column("tool_id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("default_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )

    if not _table_exists(conn, "presets"):
        op.create_table(
            "presets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )

    if not _table_exists(conn, "preset_steps"):
        op.create_table(
            "preset_steps",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("preset_id", sa.Integer(), sa.ForeignKey("presets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tool_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("preset_id", "order_index", name="uq_preset_steps_order"),
        )

    if not _table_exists(conn, "preset_assets"):
        op.create_table(
            "preset_assets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("preset_id", sa.Integer(), sa.ForeignKey("presets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_type", sa.String(length=64), nullable=False),
            sa.Column("asset_id", sa.String(length=255), nullable=False),
            sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )

    if not _column_exists(conn, "projects", "preset_id"):
        op.add_column("projects", sa.Column("preset_id", sa.Integer(), sa.ForeignKey("presets.id", ondelete="SET NULL")))

    # seed tool registry
    tools = [
        ("T01_DOWNLOAD_SOURCE", "Загрузка источника", "video", ["source_url"], ["raw_media"], {"retry": 2}),
        ("T02_PROBE_MEDIA", "Проверка медиа", "video", ["raw_media"], ["probe_meta"], {}),
        ("T03_NORMALIZE_VIDEO", "Нормализация видео", "video", ["raw_media"], ["normalized_video"], {"fps": 30}),
        ("T04_CROP_RESIZE", "Обрезка/Resize", "video", ["normalized_video"], ["cropped_video"], {"width": 1080, "height": 1920}),
        ("T07_EXTRACT_AUDIO", "Извлечение аудио", "audio", ["normalized_video"], ["audio_wav"], {}),
        ("T08_SPEECH_TO_TEXT", "Расшифровка речи", "audio", ["audio_wav"], ["transcript"], {"lang": "auto"}),
        ("T10_VOICE_CONVERT", "Конвертация голоса", "audio", ["audio_wav"], ["voice_converted"], {"voice_id": "default"}),
        ("T11_AUDIO_MIX_NORMALIZE", "Сведение аудио", "audio", ["voice_converted", "bg_music"], ["mixed_audio"], {"lufs": -14}),
        ("T12_REPLACE_AUDIO_IN_VIDEO", "Замена аудио в видео", "video", ["cropped_video", "mixed_audio"], ["video_with_audio"], {}),
        ("T13_BUILD_CAPTIONS", "Сборка субтитров", "text", ["transcript"], ["captions"], {"style": "default"}),
        ("T14_BURN_CAPTIONS", "Вшить субтитры", "video", ["video_with_audio", "captions"], ["video_with_captions"], {}),
        ("T16_GENERATE_PREVIEW", "Генерация превью", "video", ["video_with_audio"], ["preview_image"], {}),
        ("T17_PACKAGE_RESULT", "Сборка результата", "output", ["video_with_captions", "preview_image"], ["package"], {}),
    ]
    insert_stmt = (
        sa.text(
            """
            INSERT INTO tool_registry (tool_id, name, category, inputs, outputs, default_params, is_active)
            VALUES (:tool_id, :name, :category, :inputs, :outputs, :default_params, true)
            ON CONFLICT (tool_id) DO NOTHING
            """
        )
        .bindparams(
            sa.bindparam("tool_id", type_=sa.String()),
            sa.bindparam("name", type_=sa.String()),
            sa.bindparam("category", type_=sa.String()),
            sa.bindparam("inputs", type_=postgresql.JSONB),
            sa.bindparam("outputs", type_=postgresql.JSONB),
            sa.bindparam("default_params", type_=postgresql.JSONB),
        )
    )
    for tool_id, name, category, inputs, outputs, default_params in tools:
        conn.execute(
            insert_stmt,
            {
                "tool_id": tool_id,
                "name": name,
                "category": category,
                "inputs": inputs,
                "outputs": outputs,
                "default_params": default_params,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "projects", "preset_id"):
        op.drop_column("projects", "preset_id")
    if _table_exists(conn, "preset_assets"):
        op.drop_table("preset_assets")
    if _table_exists(conn, "preset_steps"):
        op.drop_table("preset_steps")
    if _table_exists(conn, "presets"):
        op.drop_table("presets")
    if _table_exists(conn, "tool_registry"):
        op.drop_table("tool_registry")
