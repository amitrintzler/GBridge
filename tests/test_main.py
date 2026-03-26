"""Tests for the CLI entry point."""

from __future__ import annotations

from unittest.mock import patch

from gbridge.__main__ import (
    _google_console_visual_guide,
    build_parser,
    cmd_setup,
    cmd_status,
    cmd_sync,
    cmd_version,
)


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

    def test_setup_command_exists(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.command == "setup"

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


class TestSetupWizard:
    def test_setup_checks_python_version(self, capsys: object, tmp_path: object) -> None:
        """Setup wizard prints Python version check."""
        with (
            patch("gbridge.__main__.Settings") as mock_settings_cls,
            patch("gbridge.__main__.webbrowser"),
            patch("builtins.input", return_value=""),
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.client_secrets_path = tmp_path / "client_secret.json"  # type: ignore[operator]

            args = build_parser().parse_args(["setup"])
            # Will fail at Step 2 (no client_secret.json + no browser),
            # but Step 1 (Python check) should succeed
            cmd_setup(args)

        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "Checking Python version" in captured.out
        assert "OK" in captured.out

    def test_setup_missing_credentials_shows_guide(
        self, capsys: object, tmp_path: object
    ) -> None:
        """Setup wizard shows visual guide when credentials are missing."""
        with (
            patch("gbridge.__main__.Settings") as mock_settings_cls,
            patch("gbridge.__main__.webbrowser") as mock_browser,
            patch("builtins.input", return_value=""),
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.client_secrets_path = tmp_path / "client_secret.json"  # type: ignore[operator]
            mock_browser.open.return_value = True

            args = build_parser().parse_args(["setup"])
            rc = cmd_setup(args)

        assert rc == 1  # Fails because file still not there after pressing ENTER
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        # Should show the visual guide
        assert "STEP A" in captured.out
        assert "STEP B" in captured.out
        assert "STEP C" in captured.out
        assert "DOWNLOAD JSON" in captured.out
        # Should open browser
        mock_browser.open.assert_called_once()

    def test_setup_with_existing_credentials_skips_guide(
        self, capsys: object, tmp_path: object
    ) -> None:
        """If credentials already exist, skip the guide and go to auth."""
        import json

        secrets = tmp_path / "client_secret.json"  # type: ignore[operator]
        secrets.write_text(json.dumps({  # type: ignore[attr-defined]
            "installed": {
                "client_id": "test", "client_secret": "test",
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }))

        with (
            patch("gbridge.__main__.Settings") as mock_settings_cls,
            patch("gbridge.google.auth.keyring"),
            patch("gbridge.google.auth.InstalledAppFlow") as mock_flow_cls,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.client_secrets_path = secrets
            mock_settings.db_path = tmp_path / "test.db"  # type: ignore[operator]

            # Mock the auth flow to return valid credentials
            from unittest.mock import MagicMock

            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds.expired = False
            mock_creds.token = "test_token"
            mock_creds.refresh_token = "test_refresh"
            mock_creds.token_uri = "https://oauth2.googleapis.com/token"
            mock_creds.client_id = "test"
            mock_creds.client_secret = "test"
            mock_creds.scopes = set()

            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = mock_creds
            mock_flow_cls.from_client_secrets_file.return_value = mock_flow

            args = build_parser().parse_args(["setup"])
            cmd_setup(args)

        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "Found:" in captured.out  # Shows "Found: ... — OK"
        assert "STEP A" not in captured.out  # Skips the visual guide

    def test_visual_guide_content(self) -> None:
        """Visual guide contains all required sections."""
        guide = _google_console_visual_guide()
        assert "STEP A" in guide
        assert "STEP B" in guide
        assert "STEP C" in guide
        assert "NEW PROJECT" in guide
        assert "People API" in guide
        assert "Google Calendar API" in guide
        assert "Tasks API" in guide
        assert "DOWNLOAD JSON" in guide
        assert "Desktop application" in guide
        assert "client_secret.json" in guide
