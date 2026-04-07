# Testing Guide

This document explains how to run the test suite, what is currently covered, and how to add new tests. It is aimed at anyone who is new to the project.

---

## Prerequisites

The test suite is pure Python and **does not require a running PostgreSQL database or Docker**. All database calls are replaced with in-memory mocks.

You need:

- **Python 3.12+**
- The project dependencies installed in your environment (see [Quick setup](#quick-setup))

---

## Quick Setup

```bash
# 1. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate

# 2. Install all dependencies (including test tools)
pip install -r requirements.txt
```

The test tools (`pytest` and `pytest-asyncio`) are already listed at the bottom of `requirements.txt`, so a single `pip install -r requirements.txt` is enough.

---

## Running the Tests

### Run the full suite

```bash
python -m pytest
```

### Run with verbose output (see individual test names)

```bash
python -m pytest -v
```

### Run a single test file

```bash
python -m pytest tests/test_character_service.py -v
```

### Run a single test class or test function

```bash
# Run one class
python -m pytest tests/test_character_service.py::TestAdjustHp -v

# Run one function
python -m pytest tests/test_character_service.py::TestAdjustHp::test_damage_reduces_current -v
```

### Run tests matching a keyword

```bash
python -m pytest -k "spell_slot" -v
```

### Stop after the first failure

```bash
python -m pytest -x
```

---

## Configuration

Test configuration lives in `pytest.ini` at the project root:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- `asyncio_mode = auto` — every `async def test_*` function is automatically treated as an async test. You do **not** need to add `@pytest.mark.asyncio` decorators.
- `testpaths = tests` — pytest only looks inside the `tests/` directory.

The `tests/conftest.py` file sets the minimal environment variables required by `app.config.Settings` so that importing the application modules works without a real `.env` file:

```python
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-key-for-tests-only")
```

These values are never used to open a real connection; they simply satisfy the Pydantic settings model.

---

## Test Layout

```
tests/
├── __init__.py                 # Package marker
├── conftest.py                 # Shared env setup and helper factory
├── test_auth_service.py        # Auth service pure functions
├── test_character_service.py   # Character business logic
├── test_middleware.py          # Auth middleware helpers
├── test_schemas.py             # Schema validation and Pydantic models
└── test_share_link.py          # ShareLink.is_valid property
```

---

## What Is Covered

### `test_auth_service.py`
Tests pure functions that do **not** need a database:

| Function | What is tested |
|---|---|
| `hash_password` | Returns a non-empty string; does not expose the plaintext; produces unique hashes each call (random salt) |
| `verify_password` | Correct password accepted; wrong password rejected; empty password handled correctly |
| `create_session_token` | Produces a valid JWT |
| `decode_session_token` | Round-trip (encode → decode) preserves all fields; tampered / invalid / empty tokens return `None` |

### `test_character_service.py`
Tests the `CharacterService` class. All repository calls are replaced with `AsyncMock` objects so no database is needed.

| Area | What is tested |
|---|---|
| `_calculate_spell_slots` | Full casters (Wizard, Cleric, Bard, Druid, Sorcerer), half-casters (Paladin, Ranger), third-casters (Artificer), non-casters (Fighter, Barbarian); boundary levels; expended always initialised to 0 |
| `_normalize_sheet` | Adds missing top-level keys (`vitality`, `coins`, `spell_slots`, `languages`, `equipment`); does not overwrite existing values; does not mutate the caller's dict; coerces flat integer skill data to the full dict format; fills in missing keys inside an existing skill dict |
| `adjust_hp` | Healing capped at max; damage floored at 0; temp HP absorbed before current HP; absolute value mode; no-op when both `delta` and `absolute` are `None` |
| `toggle_death_save` | Increments successes/failures; caps at 3; floors at 0; unknown save type is a no-op |
| `adjust_spell_slot` | Expend and recover; cannot exceed `total`; cannot go below 0; corrupted `spell_slots` field is re-initialised |
| `_check_write_permission` | Owner can write; DM can write any character; non-owner non-DM raises `CharacterPermissionError` |
| `create_from_json_string` | Invalid JSON raises `CharacterValidationError`; missing required fields raise `CharacterValidationError`; valid JSON calls the repository |

### `test_middleware.py`
Tests FastAPI dependency functions that inspect the session cookie:

| Function | What is tested |
|---|---|
| `get_current_user` | No cookie → `None`; valid cookie → `UserSession`; garbage token → `None` |
| `require_login` | Logged-in user returned as-is; unauthenticated raises HTTP 307 redirect to `/login` |
| `require_dm` | DM user returned as-is; non-DM raises HTTP 403 |

### `test_schemas.py`
Tests validation helpers and all Pydantic schema models:

| Area | What is tested |
|---|---|
| `validate_non_empty` | Valid string returned; whitespace stripped; blank / whitespace-only strings raise `ValueError` |
| `validate_mandatory_fields` | All required fields present; each missing / invalid field produces the correct error message; level boundary values (1–20); HP boundary values; multiple simultaneous errors |
| `get_skill_bonus` / `is_proficient` / `get_skill_advantage` | Both dict format and legacy flat-int format handled |
| `HPUpdate`, `TempHPUpdate` | Empty string coerced to `None` |
| `SpellSlotUpdate` | Level validated to 1–9 |
| `MaxHPUpdate` | `None` / empty string defaults to `1` |
| `ThrowableCaseQtyUpdate` | Defaults; empty string coerced to `0` |

### `test_share_link.py`
Tests `ShareLink.is_valid`:

| Scenario | Expected result |
|---|---|
| Active, no expiry | `True` |
| Inactive | `False` |
| Active, future expiry | `True` |
| Active, past expiry | `False` |
| Inactive, future expiry | `False` |

---

## What Is Not Covered (Yet)

The areas below are **not** covered by the current unit tests. They would require either a live database (integration tests) or a running FastAPI instance (end-to-end tests):

- **HTTP handler layer** (`app/handlers/`) — route registration, request parsing, HTML responses
- **Repository layer** (`app/repositories/`) — actual SQL queries against PostgreSQL
- **Campaign service** (`CampaignService`) — most methods delegate directly to the repository
- **Player service** (`PlayerService`) — same
- **Share link service** (`ShareLinkService`) — same
- **Alembic migrations** — database schema evolution
- **HTMX partial responses** — template rendering
- **File upload / portrait handling** — binary data paths

If you want to add integration tests, see [Adding New Tests](#adding-new-tests) below.

---

## Adding New Tests

### Unit test (no database)

1. Create a new file in `tests/` named `test_<module>.py`.
2. Import the class or function you want to test.
3. Mock any repository or database call with `unittest.mock.AsyncMock`:

```python
from unittest.mock import AsyncMock, MagicMock
from app.services.campaign_service import CampaignService

def _make_service():
    db = AsyncMock()
    service = CampaignService(db)
    service._repo = AsyncMock()
    return service

async def test_get_campaign_not_found():
    service = _make_service()
    service._repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(CampaignNotFound):
        await service.get_campaign(uuid.uuid4())
```

4. Because `asyncio_mode = auto` is set, async test functions just work:

```python
async def test_something_async():
    result = await some_async_function()
    assert result == expected
```

### Testing a Pydantic schema

```python
from pydantic import ValidationError
from app.schemas.character import SpellSlotUpdate

def test_invalid_level():
    with pytest.raises(ValidationError):
        SpellSlotUpdate(level=0, delta=1)
```

### Useful patterns from existing tests

- **`_make_character(sheet_data, owner_id)`** helper in `tests/test_character_service.py` — creates a lightweight `MagicMock` character with a realistic sheet structure.
- **`_is_valid = ShareLink.is_valid.fget`** pattern in `tests/test_share_link.py` — lets you test a `@property` on a plain `SimpleNamespace` without instantiating the SQLAlchemy model.

---

## Frequently Asked Questions

**Q: Do I need Docker or PostgreSQL to run the tests?**  
No. All database access is mocked. Just install the Python dependencies and run `python -m pytest`.

**Q: I get a `ModuleNotFoundError` when I run the tests.**  
Make sure you have installed requirements: `pip install -r requirements.txt`. Also make sure you are running pytest from the project root, not from inside the `tests/` directory.

**Q: I added an `async def test_*` function but it says it is not being collected as async.**  
Check that `pytest.ini` is present at the project root and contains `asyncio_mode = auto`. With this setting no extra decorator is needed.

**Q: Where do I find sample character JSON data?**  
The project may contain sample JSON in a `test_data/` directory at the project root. You can also build a minimal valid sheet using the structure required by `validate_mandatory_fields`:

```python
{
    "character_identity": {
        "character_name": "Gandalf",
        "class":   {"name": "Wizard"},
        "species": {"name": "Maiar"},
    },
    "character_level": {"level": 20},
    "vitality": {
        "hit_points": {"max": 100, "current": 100},
    },
}
```
