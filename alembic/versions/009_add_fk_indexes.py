"""Add indexes on foreign key columns

Revision ID: 009
Revises: 008
Create Date: 2026-03-10 12:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_campaigns_created_by", "campaigns", ["created_by"], if_not_exists=True)
    op.create_index("ix_characters_owner_id", "characters", ["owner_id"], if_not_exists=True)
    op.create_index("ix_share_links_character_id", "share_links", ["character_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_share_links_character_id", table_name="share_links")
    op.drop_index("ix_characters_owner_id", table_name="characters")
    op.drop_index("ix_campaigns_created_by", table_name="campaigns")
