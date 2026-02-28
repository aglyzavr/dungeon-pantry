"""Make character owner_id nullable

Revision ID: 004
Revises: 003
Create Date: 2026-02-27
"""
import sqlalchemy as sa
from alembic import op


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing FK constraint
    op.drop_constraint(
        "characters_owner_id_fkey",
        "characters",
        type_="foreignkey",
    )

    # Make column nullable
    op.alter_column(
        "characters",
        "owner_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Re-add FK with SET NULL on delete
    op.create_foreign_key(
        "characters_owner_id_fkey",
        "characters",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "characters_owner_id_fkey",
        "characters",
        type_="foreignkey",
    )
    op.alter_column(
        "characters",
        "owner_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "characters_owner_id_fkey",
        "characters",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
