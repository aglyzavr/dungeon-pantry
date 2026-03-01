"""Add theme column to users table

Revision ID: 008
Revises: 007
Create Date: 2026-03-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("theme", sa.String(length=10), nullable=False, server_default="light"),
    )
    op.create_check_constraint(
        "users_theme_check",
        "users",
        "theme IN ('light', 'dark')",
    )


def downgrade() -> None:
    op.drop_constraint("users_theme_check", "users", type_="check")
    op.drop_column("users", "theme")
