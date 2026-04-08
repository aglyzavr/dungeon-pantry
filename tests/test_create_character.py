"""Tests for the Create Character feature.

Written TDD-style: all tests are written BEFORE the implementation so that
the test suite is red first, then the implementation makes it green.

Coverage:
  - CharacterService._blank_sheet()
  - build_sheet_from_form() starting from a blank sheet
  - CharacterService.create() happy/sad paths
  - GET  /characters/new  (DM-only form)
  - POST /characters/new  (valid data → redirect; invalid → re-render form)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.character import validate_mandatory_fields
from app.services.character_service import CharacterService, CharacterValidationError


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _make_service() -> CharacterService:
    db = AsyncMock()
    service = CharacterService(db)
    service._repo = AsyncMock()
    service._campaign_repo = AsyncMock()
    return service


def _valid_form_data(**overrides) -> dict:
    """Minimal form data that satisfies validate_mandatory_fields."""
    base = {
        "character_name": "Aria",
        "class_name": "Rogue",
        "species_name": "Elf",
        "level": "3",
        "hp_max": "24",
        "hp_current": "20",
    }
    base.update(overrides)
    return base


def _make_test_client(mock_service):
    """Return a (TestClient, DM UserSession) pair with all DB/auth deps mocked."""
    import uuid as _uuid

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.handlers.character_handler import _player_service
    from app.handlers.character_handler import _service as _svc_dep
    from app.middleware.auth import require_dm, require_login
    from app.middleware.csrf import CSRFMiddleware
    from app.schemas.auth import UserSession

    dm_user = UserSession(
        user_id=_uuid.uuid4(),
        username="dm_test",
        is_dm=True,
        language="en",
        theme="light",
    )

    mock_player_svc = MagicMock()
    mock_player_svc.list_players = AsyncMock(return_value=[])

    from app.handlers.character_handler import router

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)
    app.include_router(router)

    app.dependency_overrides[require_dm] = lambda: dm_user
    app.dependency_overrides[require_login] = lambda: dm_user
    app.dependency_overrides[_svc_dep] = lambda: mock_service
    app.dependency_overrides[_player_service] = lambda: mock_player_svc

    return TestClient(app, raise_server_exceptions=True, follow_redirects=False), dm_user


# ---------------------------------------------------------------------------
# 1. CharacterService._blank_sheet()
# ---------------------------------------------------------------------------


class TestBlankSheet:
    def test_returns_dict(self):
        result = CharacterService._blank_sheet()
        assert isinstance(result, dict)

    def test_has_character_identity(self):
        result = CharacterService._blank_sheet()
        assert "character_identity" in result
        assert "character_name" in result["character_identity"]
        assert "class" in result["character_identity"]
        assert "species" in result["character_identity"]

    def test_character_identity_name_is_empty_string(self):
        result = CharacterService._blank_sheet()
        assert result["character_identity"]["character_name"] == ""

    def test_has_character_level(self):
        result = CharacterService._blank_sheet()
        assert "character_level" in result
        assert "level" in result["character_level"]

    def test_has_vitality_with_hit_points(self):
        result = CharacterService._blank_sheet()
        assert "vitality" in result
        assert "hit_points" in result["vitality"]

    def test_fails_mandatory_validation_on_empty_values(self):
        """A blank sheet must NOT pass mandatory validation (no name, no HP, etc.)."""
        result = CharacterService._blank_sheet()
        errors = validate_mandatory_fields(result)
        assert len(errors) > 0

    def test_survives_normalize_without_error(self):
        """_normalize_sheet on a blank sheet must not raise."""
        service = _make_service()
        result = CharacterService._blank_sheet()
        normalized = service._normalize_sheet(result)
        assert isinstance(normalized, dict)

    def test_repeated_calls_return_independent_dicts(self):
        """Mutating one returned blank sheet must not affect the next call."""
        a = CharacterService._blank_sheet()
        b = CharacterService._blank_sheet()
        a["character_identity"]["character_name"] = "Modified"
        assert b["character_identity"]["character_name"] == ""

    def test_has_ability_scores_keys(self):
        result = CharacterService._blank_sheet()
        for ability in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
            assert ability in result

    def test_has_equipment(self):
        result = CharacterService._blank_sheet()
        assert "equipment" in result
        assert isinstance(result["equipment"].get("throwable_cases"), list)

    def test_has_spell_slots(self):
        result = CharacterService._blank_sheet()
        assert "spell_slots" in result

    def test_has_coins(self):
        result = CharacterService._blank_sheet()
        assert "coins" in result


# ---------------------------------------------------------------------------
# 2. build_sheet_from_form starting from a blank sheet
# ---------------------------------------------------------------------------


class TestBuildSheetFromFormBlankStart:
    def setup_method(self):
        self.service = _make_service()

    @pytest.mark.asyncio
    async def test_builds_character_identity(self):
        blank = CharacterService._blank_sheet()
        result = await self.service.build_sheet_from_form(blank, _valid_form_data())
        identity = result["character_identity"]
        assert identity["character_name"] == "Aria"
        assert identity["class"]["name"] == "Rogue"
        assert identity["species"]["name"] == "Elf"

    @pytest.mark.asyncio
    async def test_builds_character_level(self):
        blank = CharacterService._blank_sheet()
        result = await self.service.build_sheet_from_form(blank, _valid_form_data())
        assert result["character_level"]["level"] == 3

    @pytest.mark.asyncio
    async def test_builds_vitality(self):
        blank = CharacterService._blank_sheet()
        result = await self.service.build_sheet_from_form(blank, _valid_form_data())
        hp = result["vitality"]["hit_points"]
        assert hp["max"] == 24
        assert hp["current"] == 20

    @pytest.mark.asyncio
    async def test_result_passes_mandatory_validation(self):
        """A form submission with required fields must pass validation."""
        blank = CharacterService._blank_sheet()
        result = await self.service.build_sheet_from_form(blank, _valid_form_data())
        errors = validate_mandatory_fields(result)
        assert errors == []

    @pytest.mark.asyncio
    async def test_result_still_fails_with_missing_name(self):
        blank = CharacterService._blank_sheet()
        form = _valid_form_data(character_name="")
        result = await self.service.build_sheet_from_form(blank, form)
        errors = validate_mandatory_fields(result)
        assert any("character_name" in e for e in errors)


# ---------------------------------------------------------------------------
# 3. CharacterService.create() — round-trip through blank → form → create
# ---------------------------------------------------------------------------


class TestCreateCharacterService:
    def setup_method(self):
        self.service = _make_service()
        self.owner_id = uuid.uuid4()

    @pytest.mark.asyncio
    async def test_create_with_valid_sheet_calls_repo(self):
        valid_sheet = {
            "character_identity": {
                "character_name": "Aria",
                "class": {"name": "Rogue"},
                "species": {"name": "Elf"},
            },
            "character_level": {"level": 3},
            "vitality": {"hit_points": {"max": 24, "current": 20}},
        }
        mock_char = MagicMock()
        mock_char.id = uuid.uuid4()
        self.service._repo.create = AsyncMock(return_value=mock_char)

        result = await self.service.create(sheet_data=valid_sheet, owner_id=self.owner_id)

        assert result is mock_char
        self.service._repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_blank_sheet_raises_validation_error(self):
        blank = CharacterService._blank_sheet()
        with pytest.raises(CharacterValidationError):
            await self.service.create(sheet_data=blank, owner_id=self.owner_id)

    @pytest.mark.asyncio
    async def test_full_round_trip_blank_to_create(self):
        """_blank_sheet → build_sheet_from_form → create succeeds end-to-end."""
        blank = CharacterService._blank_sheet()
        built = await self.service.build_sheet_from_form(blank, _valid_form_data())

        mock_char = MagicMock()
        mock_char.id = uuid.uuid4()
        self.service._repo.create = AsyncMock(return_value=mock_char)

        result = await self.service.create(sheet_data=built, owner_id=self.owner_id)
        assert result is mock_char


# ---------------------------------------------------------------------------
# 4. Handler — GET /characters/new
# ---------------------------------------------------------------------------


class TestGetCreateCharacterForm:
    def setup_method(self):
        self.service = _make_service()
        self.client, self.dm_user = _make_test_client(self.service)

    def test_returns_200(self):
        resp = self.client.get("/characters/new")
        assert resp.status_code == 200

    def test_response_is_html(self):
        resp = self.client.get("/characters/new")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_form_action_points_to_new_route(self):
        resp = self.client.get("/characters/new")
        assert "/characters/new" in resp.text

    def test_page_contains_create_heading(self):
        resp = self.client.get("/characters/new")
        assert "Create Character" in resp.text

    def test_cancel_link_points_to_list(self):
        resp = self.client.get("/characters/new")
        # Cancel should go back to /characters (not to a specific character)
        assert 'href="/characters"' in resp.text


# ---------------------------------------------------------------------------
# 5. Handler — POST /characters/new
# ---------------------------------------------------------------------------


class TestPostCreateCharacterHandler:
    def setup_method(self):
        self.service = _make_service()
        self.client, self.dm_user = _make_test_client(self.service)
        self.char_id = uuid.uuid4()

        mock_char = MagicMock()
        mock_char.id = self.char_id
        self.service.build_sheet_from_form = AsyncMock(return_value={
            "character_identity": {
                "character_name": "Aria",
                "class": {"name": "Rogue"},
                "species": {"name": "Elf"},
            },
            "character_level": {"level": 3},
            "vitality": {"hit_points": {"max": 24, "current": 20}},
        })
        self.service.create = AsyncMock(return_value=mock_char)

    def _post(self, data: dict | None = None):
        """POST to /characters/new, injecting a valid CSRF token."""
        # GET first to acquire the CSRF cookie
        get_resp = self.client.get("/characters/new")
        csrf = get_resp.cookies.get("csrf_token", "test-csrf-token")

        form = dict(_valid_form_data(), csrf_token=csrf)
        if data:
            form.update(data)

        self.client.cookies.set("csrf_token", csrf)
        return self.client.post(
            "/characters/new",
            data=form,
        )

    def test_valid_submission_redirects_to_character(self):
        resp = self._post()
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/characters/{self.char_id}"

    def test_valid_submission_calls_service_create(self):
        self._post()
        self.service.create.assert_called_once()

    def test_validation_error_returns_422(self):
        self.service.create = AsyncMock(
            side_effect=CharacterValidationError(["character_identity.character_name is required"])
        )
        resp = self._post()
        assert resp.status_code == 422

    def test_validation_error_re_renders_form(self):
        self.service.create = AsyncMock(
            side_effect=CharacterValidationError(["character_identity.character_name is required"])
        )
        resp = self._post()
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Validation failed" in resp.text


# ---------------------------------------------------------------------------
# 6. List page — choice modal is present
# ---------------------------------------------------------------------------


class TestListPageChoiceModal:
    def setup_method(self):
        self.service = _make_service()
        self.service.list_all = AsyncMock(return_value=[])
        self.client, _ = _make_test_client(self.service)

    def test_list_page_loads(self):
        resp = self.client.get("/characters")
        assert resp.status_code == 200

    def test_list_page_has_add_character_button(self):
        resp = self.client.get("/characters")
        # The page should have a button/trigger for adding characters
        assert "Add Character" in resp.text or "add-character" in resp.text

    def test_list_page_has_modal_with_upload_option(self):
        resp = self.client.get("/characters")
        assert "/characters/upload" in resp.text

    def test_list_page_has_modal_with_create_option(self):
        resp = self.client.get("/characters")
        assert "/characters/new" in resp.text
