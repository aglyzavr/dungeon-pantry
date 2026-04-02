"""Add per-campaign character data columns to campaign_characters

Revision ID: 012
Revises: 011
Create Date: 2026-04-02 12:00:00.000000

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add new columns with temporary defaults for backfill
    conn.execute(text("""
        ALTER TABLE campaign_characters
            ADD COLUMN IF NOT EXISTS sheet_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS portrait_data BYTEA,
            ADD COLUMN IF NOT EXISTS portrait_mime_type VARCHAR,
            ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """))

    # 2. Backfill from characters table
    conn.execute(text("""
        UPDATE campaign_characters cc
        SET sheet_data      = c.sheet_data,
            portrait_data   = c.portrait_data,
            portrait_mime_type = c.portrait_mime_type
        FROM characters c
        WHERE cc.character_id = c.id
    """))

    # 3. Drop the server default now that backfill is complete
    conn.execute(text("""
        ALTER TABLE campaign_characters
            ALTER COLUMN sheet_data DROP DEFAULT
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE campaign_characters
            DROP COLUMN IF EXISTS sheet_data,
            DROP COLUMN IF EXISTS portrait_data,
            DROP COLUMN IF EXISTS portrait_mime_type,
            DROP COLUMN IF EXISTS joined_at
    """))
