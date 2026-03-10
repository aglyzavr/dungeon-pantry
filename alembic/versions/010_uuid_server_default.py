"""Use server-side gen_random_uuid() for campaigns and characters id columns

Revision ID: 010
Revises: 009
Create Date: 2026-03-10 12:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "campaigns", "id",
        server_default=op.inline_literal("gen_random_uuid()"),
    )
    op.alter_column(
        "characters", "id",
        server_default=op.inline_literal("gen_random_uuid()"),
    )


def downgrade() -> None:
    op.alter_column("campaigns", "id", server_default=None)
    op.alter_column("characters", "id", server_default=None)
