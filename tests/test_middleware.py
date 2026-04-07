"""Tests for auth middleware helpers."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from starlette.exceptions import HTTPException

from app.middleware.auth import get_current_user, require_dm, require_login
from app.schemas.auth import UserSession


def _make_session(is_dm: bool = False) -> UserSession:
    return UserSession(
        user_id=uuid.uuid4(),
        username="testuser",
        is_dm=is_dm,
        language="en",
        theme="light",
    )


def _make_request() -> Request:
    return MagicMock(spec=Request)


class TestGetCurrentUser:
    def test_no_cookie_returns_none(self):
        request = _make_request()
        result = get_current_user(request, dnd_session=None)
        assert result is None

    def test_valid_cookie_returns_session(self):
        from app.services.auth_service import create_session_token

        user = MagicMock()
        user.id = uuid.uuid4()
        user.username = "alice"
        user.is_dm = False
        user.language = "en"
        user.theme = "light"

        token = create_session_token(user)
        request = _make_request()
        result = get_current_user(request, dnd_session=token)

        assert result is not None
        assert result.username == "alice"

    def test_invalid_cookie_returns_none(self):
        request = _make_request()
        result = get_current_user(request, dnd_session="garbage")
        assert result is None


class TestRequireLogin:
    def test_logged_in_user_returned(self):
        session = _make_session()
        request = _make_request()
        result = require_login(request, user=session)
        assert result is session

    def test_unauthenticated_raises_307(self):
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            require_login(request, user=None)
        assert exc_info.value.status_code == 307
        assert "/login" in exc_info.value.headers["Location"]


class TestRequireDm:
    def test_dm_user_returned(self):
        session = _make_session(is_dm=True)
        request = _make_request()
        result = require_dm(request, user=session)
        assert result is session

    def test_non_dm_raises_403(self):
        session = _make_session(is_dm=False)
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            require_dm(request, user=session)
        assert exc_info.value.status_code == 403
