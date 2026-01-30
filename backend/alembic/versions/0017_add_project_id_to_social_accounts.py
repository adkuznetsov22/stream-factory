"""add project_id to social_accounts

Revision ID: 0017_proj_account_link
Revises: 0016_projects_and_publish_tasks
Create Date: 2025-12-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0017_proj_account_link"
down_revision: Union[str, None] = "0016_projects_and_publish_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("social_accounts", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_social_accounts_project",
        "social_accounts",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_social_accounts_project_id", "social_accounts", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_social_accounts_project_id", table_name="social_accounts")
    op.drop_constraint("fk_social_accounts_project", "social_accounts", type_="foreignkey")
    op.drop_column("social_accounts", "project_id")
