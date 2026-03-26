"""Tests for the CLI entry point."""

from __future__ import annotations

from unittest.mock import patch

from gbridge.__main__ import build_parser, cmd_status, cmd_sync, cmd_version


class TestCLI:
    def test_version_flag(self, capsys: object) -> None:
        args = build_parser().parse_args(["version"])
        rc = cmd_version(args)
        assert rc == 0
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "GBridge v" in captured.out
        assert "Python" in captured.out

    def test_version_short_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--version"])
        assert args.version is True

    def test_sync_missing_client_secrets(self, capsys: object, tmp_path: object) -> None:
        """When client_secret.json is missing, show clear instructions."""
        with patch("gbridge.__main__.Settings") as mock_settings_cls:
            mock_settings = mock_settings_cls.return_value
            # Point to a nonexistent path
            mock_settings.client_secrets_path = tmp_path / "nonexistent.json"  # type: ignore[operator]

            args = build_parser().parse_args(["sync"])
            rc = cmd_sync(args)

        assert rc == 1
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "client_secret.json" in captured.out.lower() or "credentials" in captured.out.lower()
        assert "console.cloud.google.com" in captured.out

    def test_status_no_db(self, capsys: object, tmp_path: object) -> None:
        """Status with no database shows friendly message."""
        with patch("gbridge.__main__.Settings") as mock_settings_cls:
            mock_settings = mock_settings_cls.return_value
            mock_settings.db_path = tmp_path / "nonexistent.db"  # type: ignore[operator]

            args = build_parser().parse_args(["status"])
            rc = cmd_status(args)

        assert rc == 0
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "no sync data yet" in captured.out.lower()

    def test_default_command_is_sync(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None  # defaults to sync in main()

    def test_status_with_ledger(self, capsys: object, tmp_path: object) -> None:
        """Status with existing ledger shows item counts."""
        from gbridge.core.ledger import SyncLedger

        db = tmp_path / "test.db"  # type: ignore[operator]
        ledger = SyncLedger(db)
        ledger.upsert_item("contact", "people/c1", "hash1")
        ledger.upsert_item("contact", "people/c2", "hash2")
        ledger.upsert_item("event", "e1", "hash3", google_parent_id="cal1")
        ledger.close()

        with patch("gbridge.__main__.Settings") as mock_settings_cls:
            mock_settings = mock_settings_cls.return_value
            mock_settings.db_path = db
            mock_settings.client_secrets_path = tmp_path / "client_secret.json"  # type: ignore[operator]

            args = build_parser().parse_args(["status"])
            rc = cmd_status(args)

        assert rc == 0
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "2" in captured.out  # 2 contacts
        assert "1" in captured.out  # 1 event
