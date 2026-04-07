"""Shared fixtures and configuration for the test suite."""
import os
import uuid

import pytest

# Provide minimal env vars so Settings can be instantiated without a real .env file
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-key-for-tests-only")


def make_character(sheet_data: dict | None = None, owner_id: uuid.UUID | None = None):
    """Create a lightweight Character-like object for tests that don't need a DB."""
    from unittest.mock import MagicMock

    char = MagicMock()
    char.id = uuid.uuid4()
    char.owner_id = owner_id or uuid.uuid4()
    char.sheet_data = sheet_data or {
        "character_identity": {
            "character_name": "Test Hero",
            "class": {"name": "Fighter"},
            "species": {"name": "Human"},
        },
        "character_level": {"level": 5},
        "vitality": {
            "hit_points": {"current": 30, "max": 40, "temp": 0},
            "death_saves": {"successes": 0, "failures": 0},
        },
        "heroic_inspiration": False,
        "spell_slots": {},
    }
    return char
