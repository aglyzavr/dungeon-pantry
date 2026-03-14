"""Migrate bonus_action boolean to action_type enum in character sheet JSON data

Revision ID: 011
Revises: 010
Create Date: 2026-03-14 12:00:00.000000

"""
from alembic import op
from sqlalchemy import text
import json


# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        text("SELECT id, sheet_data FROM characters WHERE sheet_data IS NOT NULL")
    ).fetchall()

    for row in rows:
        char_id = row[0]
        data = row[1]
        if not isinstance(data, dict):
            continue

        changed = False

        # Migrate weapons_damage_cantrips entries
        for entry in data.get("weapons_damage_cantrips", []):
            if isinstance(entry, dict) and "bonus_action" in entry:
                entry["action_type"] = "bonus_action" if entry.pop("bonus_action") else "action"
                entry.setdefault("range", "")
                entry.setdefault("source_type", "manual")
                entry.setdefault("source_name", "")
                changed = True
            elif isinstance(entry, dict) and "action_type" not in entry:
                entry["action_type"] = "action"
                entry.setdefault("range", "")
                entry.setdefault("source_type", "manual")
                entry.setdefault("source_name", "")
                changed = True

        # Migrate cantrips_and_prepared_spells entries
        for entry in data.get("cantrips_and_prepared_spells", []):
            if isinstance(entry, dict) and "bonus_action" in entry:
                entry["action_type"] = "bonus_action" if entry.pop("bonus_action") else "none"
                changed = True
            elif isinstance(entry, dict) and "action_type" not in entry:
                entry["action_type"] = "none"
                changed = True

        # Ensure equipment.weapons array exists and entries have action_type
        equipment = data.get("equipment")
        if isinstance(equipment, dict):
            if "weapons" not in equipment:
                equipment["weapons"] = []
                changed = True
            for wpn in equipment.get("weapons", []):
                if isinstance(wpn, dict) and "action_type" not in wpn:
                    wpn["action_type"] = "none"
                    changed = True

        if changed:
            conn.execute(
                text("UPDATE characters SET sheet_data = CAST(:data AS jsonb) WHERE id = :id"),
                {"data": json.dumps(data), "id": char_id},
            )


def downgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        text("SELECT id, sheet_data FROM characters WHERE sheet_data IS NOT NULL")
    ).fetchall()

    for row in rows:
        char_id = row[0]
        data = row[1]
        if not isinstance(data, dict):
            continue

        changed = False

        for entry in data.get("weapons_damage_cantrips", []):
            if isinstance(entry, dict) and "action_type" in entry:
                entry["bonus_action"] = entry.pop("action_type") == "bonus_action"
                entry.pop("range", None)
                entry.pop("source_type", None)
                entry.pop("source_name", None)
                changed = True

        for entry in data.get("cantrips_and_prepared_spells", []):
            if isinstance(entry, dict) and "action_type" in entry:
                entry["bonus_action"] = entry.pop("action_type") == "bonus_action"
                changed = True

        if changed:
            conn.execute(
                text("UPDATE characters SET sheet_data = CAST(:data AS jsonb) WHERE id = :id"),
                {"data": json.dumps(data), "id": char_id},
            )
