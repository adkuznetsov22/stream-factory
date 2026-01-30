"""add phones emails and account access fields

Revision ID: 0004_access_contacts
Revises: 0003_metrics_daily
Create Date: 2025-01-16 17:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_access_contacts"
down_revision = "0003_metrics_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("phone_number", name="uq_phones_phone_number"),
    )
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("email_password", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_emails_email"),
    )

    op.add_column("social_accounts", sa.Column("phone_id", sa.Integer(), nullable=True))
    op.add_column("social_accounts", sa.Column("email_id", sa.Integer(), nullable=True))
    op.add_column("social_accounts", sa.Column("account_password", sa.Text(), nullable=True))
    op.add_column("social_accounts", sa.Column("purchase_source_url", sa.Text(), nullable=True))
    op.add_column("social_accounts", sa.Column("raw_import_blob", sa.Text(), nullable=True))

    op.create_foreign_key("fk_social_accounts_phone_id", "social_accounts", "phones", ["phone_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_social_accounts_email_id", "social_accounts", "emails", ["email_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_social_accounts_email_id", "social_accounts", type_="foreignkey")
    op.drop_constraint("fk_social_accounts_phone_id", "social_accounts", type_="foreignkey")
    op.drop_column("social_accounts", "raw_import_blob")
    op.drop_column("social_accounts", "purchase_source_url")
    op.drop_column("social_accounts", "account_password")
    op.drop_column("social_accounts", "email_id")
    op.drop_column("social_accounts", "phone_id")
    op.drop_table("emails")
    op.drop_table("phones")
