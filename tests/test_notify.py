"""Tests for the notification helper."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

from gbridge.utils import notify as notify_mod


class _FakeStats:
    """Duck-typed stand-in for SyncStats (avoids pulling in heavy deps)."""

    def __init__(self, new: int = 0, updated: int = 0, unchanged: int = 0) -> None:
        self.new = new
        self.updated = updated
        self.unchanged = unchanged


class TestNotify:
    def test_returns_false_when_plyer_missing(self) -> None:
        # Simulate plyer not being importable.
        with patch.dict(sys.modules, {"plyer": None}):
            assert notify_mod.notify("hello", "world") is False

    def test_delivers_via_plyer(self) -> None:
        fake = types.SimpleNamespace(notify=lambda **kw: None)
        fake_mod = types.SimpleNamespace(notification=fake)
        with patch.dict(sys.modules, {"plyer": fake_mod}):
            assert notify_mod.notify("t", "m") is True

    def test_sync_result_summary_mentions_read_only(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_notify(title: str, message: str, **_kw: object) -> None:
            calls.append((title, message))

        fake_mod = types.SimpleNamespace(
            notification=types.SimpleNamespace(notify=fake_notify)
        )
        with patch.dict(sys.modules, {"plyer": fake_mod}):
            notify_mod.notify_sync_result(
                {"contacts": _FakeStats(new=1, updated=0, unchanged=5)}
            )
        assert calls, "notification should have been delivered"
        _, body = calls[0]
        assert "Read-only" in body
        assert "no changes sent to Google" in body
