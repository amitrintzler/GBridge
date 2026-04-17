"""Smoke tests for Phase 2 CLI subcommands (outlook + conflicts)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from gbridge.__main__ import build_parser, main
from gbridge.core import conflicts as conflicts_module
from gbridge.core.ledger import SyncLedger

if TYPE_CHECKING:
    from pathlib import Path


class TestParser:
    def test_outlook_subparsers(self) -> None:
        p = build_parser()
        args = p.parse_args(["outlook", "auth", "--client-id", "GUID"])
        assert args.command == "outlook"
        assert args.outlook_action == "auth"
        assert args.client_id == "GUID"

    def test_outlook_push_dry(self) -> None:
        p = build_parser()
        args = p.parse_args(["outlook", "push", "--dry"])
        assert args.outlook_action == "push"
        assert args.dry is True

    def test_conflicts_resolve_requires_winner(self) -> None:
        p = build_parser()
        args = p.parse_args(
            ["conflicts", "resolve", "5", "--winner", "google"]
        )
        assert args.conflict_id == 5
        assert args.winner == "google"


class TestConflictCLI:
    def test_list_empty(self, tmp_path: Path, capsys) -> None:
        db = tmp_path / "c.db"
        with patch("gbridge.__main__.Settings") as settings_cls:
            settings = settings_cls.return_value
            settings.db_path = db
            rc = main_with_args(["conflicts", "list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No pending conflicts" in out

    def test_list_and_resolve_roundtrip(self, tmp_path: Path, capsys) -> None:
        db = tmp_path / "c.db"
        lg = SyncLedger(db)
        try:
            cid = conflicts_module.record_conflict(
                lg,
                item_type="contact",
                google_id="people/c1",
                google_hash="gg",
                outlook_hash="oo",
            )
        finally:
            lg.close()

        with patch("gbridge.__main__.Settings") as settings_cls:
            settings_cls.return_value.db_path = db
            rc_list = main_with_args(["conflicts", "list"])
            rc_resolve = main_with_args(
                ["conflicts", "resolve", str(cid), "--winner", "google"]
            )

        assert rc_list == 0
        assert rc_resolve == 0
        out = capsys.readouterr().out
        assert f"#{cid:>4d}" in out or f"#{cid}" in out
        assert "resolved; winner=google" in out


class TestOutlookStatus:
    def test_status_without_db(self, tmp_path: Path, capsys) -> None:
        with patch("gbridge.__main__.Settings") as settings_cls:
            s = settings_cls.return_value
            s.outlook_mode = "disabled"
            s.push_interval_minutes = 15
            s.db_path = tmp_path / "no.db"
            rc = main_with_args(["outlook", "status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Mode: disabled" in out


def main_with_args(argv: list[str]) -> int:
    """Call main() with a synthetic argv."""
    import sys
    backup = sys.argv
    sys.argv = ["gbridge", *argv]
    try:
        return main()
    finally:
        sys.argv = backup
