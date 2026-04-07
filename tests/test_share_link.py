"""Tests for the ShareLink.is_valid property.

ShareLink is a SQLAlchemy model, so we use a lightweight stand-in that
exposes only the attributes the ``is_valid`` property reads.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def _make_link(*, is_active: bool = True, expires_at=None) -> SimpleNamespace:
    """Return a plain object that mimics the ShareLink.is_valid contract."""
    return SimpleNamespace(is_active=is_active, expires_at=expires_at)


# Bind the property function so it works on the stand-in objects.
from app.models.share_link import ShareLink as _ShareLink

_is_valid = _ShareLink.is_valid.fget  # type: ignore[attr-defined]


class TestShareLinkIsValid:
    def test_active_no_expiry_is_valid(self):
        assert _is_valid(_make_link()) is True

    def test_inactive_is_not_valid(self):
        assert _is_valid(_make_link(is_active=False)) is False

    def test_future_expiry_is_valid(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert _is_valid(_make_link(expires_at=future)) is True

    def test_past_expiry_is_not_valid(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert _is_valid(_make_link(expires_at=past)) is False

    def test_inactive_with_future_expiry_is_not_valid(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert _is_valid(_make_link(is_active=False, expires_at=future)) is False
