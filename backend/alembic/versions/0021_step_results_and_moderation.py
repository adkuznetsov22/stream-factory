"""step_results and moderation support

Revision ID: 0021_step_results_and_moderation
Revises: 0020_add_virality_score
Create Date: 2026-01-28 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0021_step_results_and_moderation"
down_revision: Union[str, None] = "0020_add_virality_score"
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

    # ========== 1. Extend tool_registry ==========
    if not _column_exists(conn, "tool_registry", "description"):
        op.add_column("tool_registry", sa.Column("description", sa.Text(), nullable=True))
    
    if not _column_exists(conn, "tool_registry", "icon"):
        op.add_column("tool_registry", sa.Column("icon", sa.String(64), nullable=True))
    
    if not _column_exists(conn, "tool_registry", "param_schema"):
        op.add_column("tool_registry", sa.Column("param_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    if not _column_exists(conn, "tool_registry", "ui_component"):
        op.add_column("tool_registry", sa.Column("ui_component", sa.String(64), nullable=True))
    
    if not _column_exists(conn, "tool_registry", "supports_preview"):
        op.add_column("tool_registry", sa.Column("supports_preview", sa.Boolean(), nullable=False, server_default=sa.false()))
    
    if not _column_exists(conn, "tool_registry", "supports_retry"):
        op.add_column("tool_registry", sa.Column("supports_retry", sa.Boolean(), nullable=False, server_default=sa.true()))
    
    if not _column_exists(conn, "tool_registry", "supports_manual_edit"):
        op.add_column("tool_registry", sa.Column("supports_manual_edit", sa.Boolean(), nullable=False, server_default=sa.false()))
    
    if not _column_exists(conn, "tool_registry", "order_index"):
        op.add_column("tool_registry", sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"))

    # ========== 2. Add moderation fields to publish_tasks ==========
    if not _column_exists(conn, "publish_tasks", "moderation_mode"):
        op.add_column("publish_tasks", sa.Column("moderation_mode", sa.String(32), nullable=False, server_default="manual"))
    
    if not _column_exists(conn, "publish_tasks", "require_final_approval"):
        op.add_column("publish_tasks", sa.Column("require_final_approval", sa.Boolean(), nullable=False, server_default=sa.true()))
    
    if not _column_exists(conn, "publish_tasks", "current_step_index"):
        op.add_column("publish_tasks", sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"))
    
    if not _column_exists(conn, "publish_tasks", "pipeline_status"):
        op.add_column("publish_tasks", sa.Column("pipeline_status", sa.String(32), nullable=False, server_default="pending"))
    
    if not _column_exists(conn, "publish_tasks", "total_steps"):
        op.add_column("publish_tasks", sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"))

    # ========== 3. Create step_results table ==========
    if not _table_exists(conn, "step_results"):
        op.create_table(
            "step_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("publish_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("step_index", sa.Integer(), nullable=False),
            sa.Column("tool_id", sa.String(64), nullable=False),
            sa.Column("step_name", sa.String(255), nullable=True),
            
            # Execution status
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            
            # Input/Output
            sa.Column("input_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("output_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("logs", sa.Text(), nullable=True),
            
            # Moderation
            sa.Column("moderation_status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("moderation_comment", sa.Text(), nullable=True),
            sa.Column("moderated_by", sa.String(64), nullable=True),
            sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
            
            # Capabilities & versioning
            sa.Column("can_retry", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("previous_version_id", sa.Integer(), sa.ForeignKey("step_results.id", ondelete="SET NULL"), nullable=True),
            
            # Timestamps
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            
            # Unique constraint
            sa.UniqueConstraint("task_id", "step_index", "version", name="uq_step_results_task_step_version"),
        )
        
        # Create index for faster queries
        op.create_index("ix_step_results_moderation_status", "step_results", ["moderation_status"])
        op.create_index("ix_step_results_status", "step_results", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    
    # Drop step_results table
    if _table_exists(conn, "step_results"):
        op.drop_index("ix_step_results_status", table_name="step_results")
        op.drop_index("ix_step_results_moderation_status", table_name="step_results")
        op.drop_table("step_results")
    
    # Remove publish_tasks columns
    for col in ["moderation_mode", "require_final_approval", "current_step_index", "pipeline_status", "total_steps"]:
        if _column_exists(conn, "publish_tasks", col):
            op.drop_column("publish_tasks", col)
    
    # Remove tool_registry columns
    for col in ["description", "icon", "param_schema", "ui_component", "supports_preview", "supports_retry", "supports_manual_edit", "order_index"]:
        if _column_exists(conn, "tool_registry", col):
            op.drop_column("tool_registry", col)
