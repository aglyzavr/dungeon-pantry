"""Add portrait_path column to characters table

Revision ID: 005
Revises: 004
Create Date: 2026-02-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("portrait_path", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "portrait_path")
