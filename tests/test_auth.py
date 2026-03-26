"""Tests for Google OAuth authentication manager."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gbridge.google.auth import GoogleAuthManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def auth_manager(tmp_path: Path) -> GoogleAuthManager:
    secrets_path = tmp_path / "client_secret.json"
    secrets_path.write_text(json.dumps({
        "installed": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }))
    return GoogleAuthManager(
        client_secrets_path=secrets_path,
        scopes=["https://www.googleapis.com/auth/contacts.readonly"],
    )


class TestGoogleAuthManager:
    def test_missing_client_secrets_raises(self, tmp_path: Path) -> None:
        mgr = GoogleAuthManager(
            client_secrets_path=tmp_path / "nonexistent.json",
            scopes=["https://www.googleapis.com/auth/contacts.readonly"],
        )
        with pytest.raises(FileNotFoundError, match="client secrets file not found"):
            mgr.authenticate()

    @patch("gbridge.google.auth.keyring")
    def test_load_token_returns_none_when_empty(
        self, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        mock_keyring.get_password.return_value = None
        assert auth_manager._load_token() is None

    @patch("gbridge.google.auth.keyring")
    def test_load_token_returns_none_on_invalid_json(
        self, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        mock_keyring.get_password.return_value = "not valid json"
        assert auth_manager._load_token() is None

    @patch("gbridge.google.auth.keyring")
    def test_save_and_load_token(
        self, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        stored: dict[str, str] = {}

        def fake_set(service: str, key: str, value: str) -> None:
            stored[f"{service}:{key}"] = value

        def fake_get(service: str, key: str) -> str | None:
            return stored.get(f"{service}:{key}")

        mock_keyring.set_password.side_effect = fake_set
        mock_keyring.get_password.side_effect = fake_get

        # Create a mock credentials object
        mock_creds = MagicMock()
        mock_creds.token = "access_token_123"
        mock_creds.refresh_token = "refresh_token_456"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "test_client_id"
        mock_creds.client_secret = "test_client_secret"
        mock_creds.scopes = {"https://www.googleapis.com/auth/contacts.readonly"}

        auth_manager._save_token(mock_creds)
        assert "gbridge:google_credentials" in stored

        # Verify the stored JSON is valid
        token_data = json.loads(stored["gbridge:google_credentials"])
        assert token_data["token"] == "access_token_123"
        assert token_data["refresh_token"] == "refresh_token_456"

    @patch("gbridge.google.auth.keyring")
    def test_get_credentials_returns_valid_cached(
        self, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch.object(auth_manager, "_load_token", return_value=mock_creds):
            result = auth_manager.get_credentials()
            assert result is mock_creds

    @patch("gbridge.google.auth.keyring")
    @patch("gbridge.google.auth.Request")
    def test_get_credentials_refreshes_expired(
        self, mock_request: MagicMock, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"

        with (
            patch.object(auth_manager, "_load_token", return_value=mock_creds),
            patch.object(auth_manager, "_save_token"),
        ):
                result = auth_manager.get_credentials()
                mock_creds.refresh.assert_called_once()
                assert result is mock_creds

    @patch("gbridge.google.auth.keyring")
    def test_revoke_deletes_from_keyring(
        self, mock_keyring: MagicMock, auth_manager: GoogleAuthManager
    ) -> None:
        auth_manager.revoke()
        mock_keyring.delete_password.assert_called_once_with("gbridge", "google_credentials")
