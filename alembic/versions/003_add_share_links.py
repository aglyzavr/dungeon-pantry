"""Add share_links table

Revision ID: 003
Revises: 002
Create Date: 2026-02-27
"""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "character_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_share_links_character_id", "share_links", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_share_links_character_id")
    op.drop_table("share_links")
