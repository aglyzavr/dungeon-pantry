"""Add portrait_data and portrait_mime_type columns to characters table

Revision ID: 006
Revises: 005
Create Date: 2026-03-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("portrait_data", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "characters",
        sa.Column("portrait_mime_type", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "portrait_mime_type")
    op.drop_column("characters", "portrait_data")
