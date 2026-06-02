"""Tests for `gbridge calendars` / `gbridge tasklists` selection commands."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gbridge.__main__ import build_parser, main

if TYPE_CHECKING:
    from pathlib import Path


def _run(argv: list[str]) -> int:
    backup = sys.argv
    sys.argv = ["gbridge", *argv]
    try:
        return main()
    finally:
        sys.argv = backup


class TestParser:
    def test_calendars_select(self) -> None:
        args = build_parser().parse_args(["calendars", "--select", "a,b"])
        assert args.command == "calendars"
        assert args.select == "a,b"

    def test_tasklists_all(self) -> None:
        args = build_parser().parse_args(["tasklists", "--all"])
        assert args.command == "tasklists"
        assert args.all is True

    def test_select_and_all_mutually_exclusive(self) -> None:
        import pytest

        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["calendars", "--select", "a", "--all"]
            )


class TestSelectionMutations:
    def test_select_writes_setting(self, tmp_path: Path) -> None:
        saved: dict[str, object] = {}
        fake_settings = MagicMock()
        fake_settings.set.side_effect = lambda k, v: saved.__setitem__(k, v)

        with patch("gbridge.__main__.Settings", return_value=fake_settings):
            rc = _run(["calendars", "--select", "cal1, cal2 ,cal3"])

        assert rc == 0
        fake_settings.save.assert_called_once()
        assert saved["enabled_calendars"] == ["cal1", "cal2", "cal3"]

    def test_all_clears_setting(self, tmp_path: Path) -> None:
        saved: dict[str, object] = {}
        fake_settings = MagicMock()
        fake_settings.set.side_effect = lambda k, v: saved.__setitem__(k, v)

        with patch("gbridge.__main__.Settings", return_value=fake_settings):
            rc = _run(["tasklists", "--all"])

        assert rc == 0
        assert saved["enabled_tasklists"] == []


class TestSelectionListing:
    def test_lists_calendars_with_marks(self, tmp_path: Path, capsys) -> None:
        fake_settings = MagicMock()
        fake_settings.client_secrets_path = tmp_path / "client_secret.json"
        fake_settings.client_secrets_path.write_text("{}", encoding="utf-8")
        # Only cal1 is enabled.
        fake_settings.get.return_value = ["cal1"]

        fake_auth = MagicMock()
        fake_auth.get_credentials.return_value = object()
        fake_cal_svc = MagicMock()
        fake_cal_svc.list_calendars.return_value = [
            {"id": "cal1", "summary": "Personal"},
            {"id": "cal2", "summary": "Work"},
        ]

        with patch("gbridge.__main__.Settings", return_value=fake_settings), \
             patch("gbridge.google.auth.GoogleAuthManager", return_value=fake_auth), \
             patch("gbridge.google.calendar.CalendarService", return_value=fake_cal_svc):
            rc = _run(["calendars"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "[x] Personal" in out
        assert "[ ] Work" in out

    def test_lists_all_enabled_when_no_filter(self, tmp_path: Path, capsys) -> None:
        fake_settings = MagicMock()
        fake_settings.client_secrets_path = tmp_path / "client_secret.json"
        fake_settings.client_secrets_path.write_text("{}", encoding="utf-8")
        fake_settings.get.return_value = []  # no filter

        fake_auth = MagicMock()
        fake_auth.get_credentials.return_value = object()
        fake_tasks_svc = MagicMock()
        fake_tasks_svc.list_tasklists.return_value = [
            {"id": "l1", "title": "Inbox"},
        ]

        with patch("gbridge.__main__.Settings", return_value=fake_settings), \
             patch("gbridge.google.auth.GoogleAuthManager", return_value=fake_auth), \
             patch("gbridge.google.tasks.TasksService", return_value=fake_tasks_svc):
            rc = _run(["tasklists"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "ALL tasklists are synced" in out
        assert "[x] Inbox" in out

    def test_missing_secrets_returns_error(self, tmp_path: Path) -> None:
        fake_settings = MagicMock()
        fake_settings.client_secrets_path = tmp_path / "nope.json"
        fake_settings.get.return_value = []
        with patch("gbridge.__main__.Settings", return_value=fake_settings):
            rc = _run(["calendars"])
        assert rc == 1
