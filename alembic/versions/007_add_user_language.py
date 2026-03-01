"""Add language column to users table

Revision ID: 007
Revises: 006
Create Date: 2026-03-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=5), nullable=False, server_default="en"),
    )
    op.create_check_constraint(
        "users_language_check",
        "users",
        "language IN ('en', 'ru')",
    )


def downgrade() -> None:
    op.drop_constraint("users_language_check", "users", type_="check")
    op.drop_column("users", "language")
