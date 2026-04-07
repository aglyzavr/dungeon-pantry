"""Tests for auth_service pure functions (no database required)."""
import time
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.auth_service import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


class TestHashAndVerifyPassword:
    def test_hash_returns_string(self):
        result = hash_password("secret")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_is_not_plaintext(self):
        assert hash_password("secret") != "secret"

    def test_two_hashes_differ(self):
        # bcrypt generates a new salt each call
        assert hash_password("same") != hash_password("same")

    def test_verify_correct_password(self):
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_verify_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("non-empty", hashed) is False


class TestCreateDecodeSessionToken:
    def _make_user(self, is_dm: bool = False, language: str = "en", theme: str = "light"):
        user = MagicMock()
        user.id = uuid.uuid4()
        user.username = "testuser"
        user.is_dm = is_dm
        user.language = language
        user.theme = theme
        return user

    def test_round_trip(self):
        user = self._make_user()
        token = create_session_token(user)
        session = decode_session_token(token)

        assert session is not None
        assert str(session.user_id) == str(user.id)
        assert session.username == user.username
        assert session.is_dm == user.is_dm

    def test_dm_flag_preserved(self):
        user = self._make_user(is_dm=True)
        token = create_session_token(user)
        session = decode_session_token(token)
        assert session.is_dm is True

    def test_language_preserved(self):
        user = self._make_user(language="ru")
        token = create_session_token(user)
        session = decode_session_token(token)
        assert session.language == "ru"

    def test_theme_preserved(self):
        user = self._make_user(theme="dark")
        token = create_session_token(user)
        session = decode_session_token(token)
        assert session.theme == "dark"

    def test_invalid_token_returns_none(self):
        assert decode_session_token("not.a.valid.token") is None

    def test_tampered_token_returns_none(self):
        user = self._make_user()
        token = create_session_token(user)
        tampered = token[:-5] + "XXXXX"
        assert decode_session_token(tampered) is None

    def test_empty_token_returns_none(self):
        assert decode_session_token("") is None
