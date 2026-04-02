"""Add id column to campaign_characters table

Revision ID: 013
Revises: 012
Create Date: 2026-04-02
"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # 1. Check if id column exists; if not, add it
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name='campaign_characters' AND column_name='id'
        )
    """))
    has_id = result.scalar()
    
    if not has_id:
        # Add id column with UUID type and server default
        conn.execute(text("""
            ALTER TABLE campaign_characters
            ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid()
        """))
        
        # Drop the old composite primary key
        conn.execute(text("""
            ALTER TABLE campaign_characters
            DROP CONSTRAINT campaign_characters_pkey
        """))
        
        # Make id the primary key
        conn.execute(text("""
            ALTER TABLE campaign_characters
            ADD PRIMARY KEY (id)
        """))
        
        # Add unique constraint on (campaign_id, character_id) to preserve the original uniqueness
        conn.execute(text("""
            ALTER TABLE campaign_characters
            ADD CONSTRAINT uq_campaign_characters_campaign_character 
            UNIQUE (campaign_id, character_id)
        """))


def downgrade() -> None:
    conn = op.get_bind()
    
    # 1. Drop the unique constraint
    conn.execute(text("""
        ALTER TABLE campaign_characters
        DROP CONSTRAINT uq_campaign_characters_campaign_character
    """))
    
    # 2. Drop the id primary key
    conn.execute(text("""
        ALTER TABLE campaign_characters
        DROP CONSTRAINT campaign_characters_pkey
    """))
    
    # 3. Restore composite primary key
    conn.execute(text("""
        ALTER TABLE campaign_characters
        ADD PRIMARY KEY (campaign_id, character_id)
    """))
    
    # 4. Drop the id column
    conn.execute(text("""
        ALTER TABLE campaign_characters
        DROP COLUMN id
    """))
