"""add label/notes to phones and emails

Revision ID: 0005_phone_email_meta
Revises: 0004_access_contacts
Create Date: 2025-01-16 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_phone_email_meta"
down_revision = "0004_access_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("phones", sa.Column("label", sa.String(length=128), nullable=True))
    op.add_column("phones", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("emails", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("emails", "notes")
    op.drop_column("phones", "notes")
    op.drop_column("phones", "label")
