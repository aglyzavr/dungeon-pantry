"""Regression tests for the campaign detail view."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.handlers.campaign_handler import _service as _svc_dep
from app.handlers.campaign_handler import router
from app.middleware.auth import require_login
from app.schemas.auth import UserSession


def _make_campaign_client(mock_service):
    """Return a TestClient with campaign dependencies overridden."""
    user = UserSession(
        user_id=uuid.uuid4(),
        username="player1",
        is_dm=False,
        language="en",
        theme="light",
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_login] = lambda: user
    app.dependency_overrides[_svc_dep] = lambda: mock_service
    return TestClient(app, raise_server_exceptions=True, follow_redirects=False), user


def test_campaign_detail_uses_campaign_portrait_route_for_campaign_avatar():
    """Campaign-specific portraits must load from the campaign portrait endpoint."""
    campaign_id = uuid.uuid4()
    character_id = uuid.uuid4()

    association = SimpleNamespace(
        character=SimpleNamespace(id=character_id, owner=None, portrait_data=None),
        sheet_data={
            "character_identity": {
                "character_name": "Agly",
                "class": {"name": "Wizard"},
                "species": {"name": "Lizardfolk", "subtype": ""},
            },
            "character_level": {"level": 4},
            "vitality": {"hit_points": {"current": 22, "max": 28}},
        },
        portrait_data=b"campaign-portrait-bytes",
    )
    campaign = SimpleNamespace(
        id=campaign_id,
        name="Dungeon Pantry",
        description="",
        character_associations=[association],
    )

    mock_service = AsyncMock()
    mock_service.get_campaign.return_value = campaign
    mock_service.get_available_characters_for_campaign.return_value = []

    client, _ = _make_campaign_client(mock_service)
    response = client.get(f"/campaigns/{campaign_id}")

    assert response.status_code == 200
    assert (
        f'/campaigns/{campaign_id}/characters/{character_id}/portrait' in response.text
    )


def test_campaign_detail_shows_base_character_portrait_for_assigned_character():
    """Assigned characters with a normal portrait should still show an avatar on the campaign page."""
    campaign_id = uuid.uuid4()
    character_id = uuid.uuid4()

    association = SimpleNamespace(
        character=SimpleNamespace(id=character_id, owner=None, portrait_data=b"base-portrait-bytes"),
        sheet_data={
            "character_identity": {
                "character_name": "Barya",
                "class": {"name": "Cleric"},
                "species": {"name": "Dwarf", "subtype": ""},
            },
            "character_level": {"level": 5},
            "vitality": {"hit_points": {"current": 30, "max": 35}},
        },
        portrait_data=None,
    )
    campaign = SimpleNamespace(
        id=campaign_id,
        name="Dungeon Pantry",
        description="",
        character_associations=[association],
    )

    mock_service = AsyncMock()
    mock_service.get_campaign.return_value = campaign
    mock_service.get_available_characters_for_campaign.return_value = []

    client, _ = _make_campaign_client(mock_service)
    response = client.get(f"/campaigns/{campaign_id}")

    assert response.status_code == 200
    assert 'class="portrait-image"' in response.text
    assert (
        f'/campaigns/{campaign_id}/characters/{character_id}/portrait' in response.text
    )
