"""Add proficiency dots and passive senses to character schema (JSONB — no DDL change)

Revision ID: 002
Revises: 001
Create Date: 2026-02-27
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSONB schema evolution — no DDL required.
    # New fields added to character JSON:
    #   - per-skill: { bonus, proficient }
    #   - per ability: saving_throw_proficient bool
    #   - passive_investigation, passive_insight int
    # Existing characters will render gracefully via Jinja2 default filters.
    pass


def downgrade() -> None:
    pass
