import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.handlers.campaign_handler import _character_service as _char_svc_dep
from app.handlers.campaign_handler import _service as _svc_dep
from app.handlers.campaign_handler import router
from app.middleware.auth import require_login
from app.schemas.auth import UserSession
from app.services.character_service import CharacterService


def _make_client(current_user: UserSession, mock_service, mock_character_service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_login] = lambda: current_user
    app.dependency_overrides[_svc_dep] = lambda: mock_service
    app.dependency_overrides[_char_svc_dep] = lambda: mock_character_service
    return TestClient(app, raise_server_exceptions=True, follow_redirects=False)


def test_campaign_character_edit_form_allows_owner_player():
    campaign_id = uuid.uuid4()
    character_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    current_user = UserSession(
        user_id=owner_id,
        username="player_owner",
        is_dm=False,
        language="en",
        theme="light",
    )

    campaign = SimpleNamespace(id=campaign_id, name="Dungeon Pantry")
    character = SimpleNamespace(id=character_id, owner_id=owner_id)
    campaign_char = SimpleNamespace(
        character=character,
        sheet_data=CharacterService._blank_sheet(),
    )

    mock_service = AsyncMock()
    mock_service.get_campaign.return_value = campaign
    mock_service._repo = AsyncMock()
    mock_service._repo.get_campaign_character_with_association.return_value = campaign_char

    mock_character_service = Mock()
    mock_character_service._normalize_sheet.return_value = CharacterService._blank_sheet()

    client = _make_client(current_user, mock_service, mock_character_service)

    response = client.get(f"/campaigns/{campaign_id}/characters/{character_id}/edit")

    assert response.status_code == 200
    assert "Edit Character" in response.text


def test_campaign_character_edit_form_redirects_non_owner_player():
    campaign_id = uuid.uuid4()
    character_id = uuid.uuid4()

    current_user = UserSession(
        user_id=uuid.uuid4(),
        username="other_player",
        is_dm=False,
        language="en",
        theme="light",
    )

    campaign = SimpleNamespace(id=campaign_id, name="Dungeon Pantry")
    character = SimpleNamespace(id=character_id, owner_id=uuid.uuid4())
    campaign_char = SimpleNamespace(
        character=character,
        sheet_data=CharacterService._blank_sheet(),
    )

    mock_service = AsyncMock()
    mock_service.get_campaign.return_value = campaign
    mock_service._repo = AsyncMock()
    mock_service._repo.get_campaign_character_with_association.return_value = campaign_char

    mock_character_service = Mock()
    mock_character_service._normalize_sheet.return_value = CharacterService._blank_sheet()

    client = _make_client(current_user, mock_service, mock_character_service)

    response = client.get(f"/campaigns/{campaign_id}/characters/{character_id}/edit")

    assert response.status_code == 303
    assert response.headers["location"] == f"/campaigns/{campaign_id}/characters/{character_id}"
