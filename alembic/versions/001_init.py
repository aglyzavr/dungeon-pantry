"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("role IN ('dm', 'player')", name="users_role_check"),
    )

    # --- campaigns ---
    op.create_table(
        "campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # --- characters ---
    op.create_table(
        "characters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sheet_data", JSONB, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # --- campaign_characters (many-to-many) ---
    op.create_table(
        "campaign_characters",
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", UUID(as_uuid=True),
                  sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("campaign_id", "character_id"),
    )

    # --- character_shares ---
    op.create_table(
        "character_shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("character_id", UUID(as_uuid=True),
                  sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("share_token", UUID(as_uuid=True), unique=True, nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # --- Indexes ---
    op.create_index("idx_characters_owner", "characters", ["owner_id"])
    op.create_index("idx_campaign_characters_campaign", "campaign_characters", ["campaign_id"])
    op.create_index("idx_character_shares_token", "character_shares", ["share_token"])
    op.create_index(
        "idx_characters_sheet_gin", "characters", ["sheet_data"],
        postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("character_shares")
    op.drop_table("campaign_characters")
    op.drop_index("idx_characters_sheet_gin", table_name="characters")
    op.drop_index("idx_characters_owner", table_name="characters")
    op.drop_table("characters")
    op.drop_table("campaigns")
    op.drop_table("users")
