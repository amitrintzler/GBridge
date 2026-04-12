"""Google OAuth 2.0 authentication with OS keychain token storage.

Security design:
- Tokens are stored in the OS keychain (Windows Credential Locker,
  macOS Keychain, Linux Secret Service) via the ``keyring`` library —
  never written to plain-text files.
- Only READ-ONLY scopes are requested — GBridge cannot modify, delete,
  or corrupt any Google data.
- The OAuth flow uses a local redirect URI (localhost) with an
  ephemeral port — no external server is involved.
- Credentials are refreshed automatically; if refresh fails the user
  is prompted to re-authenticate interactively.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, cast

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gbridge.config.defaults import KEYRING_GOOGLE_TOKEN_KEY, KEYRING_SERVICE

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class GoogleAuthManager:
    """Manage Google OAuth 2.0 credentials with keychain persistence."""

    def __init__(self, client_secrets_path: Path, scopes: list[str]) -> None:
        self._client_secrets_path = client_secrets_path
        self._scopes = scopes

    def get_credentials(self) -> Credentials:
        """Return valid credentials, refreshing or re-authenticating as needed."""
        creds = self._load_token()

        if creds is not None and creds.valid:
            return creds

        if creds is not None and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(creds)
                logger.info("Google token refreshed successfully")
                return creds
            except Exception:
                logger.warning("Token refresh failed — re-authentication required")

        return self.authenticate()

    def authenticate(self) -> Credentials:
        """Run the interactive browser-based OAuth flow.

        Opens the user's default browser to the Google consent screen.
        A local HTTP server on an ephemeral port receives the callback.
        """
        if not self._client_secrets_path.exists():
            msg = (
                f"Google client secrets file not found at {self._client_secrets_path}. "
                "Download it from the Google Cloud Console and place it there."
            )
            raise FileNotFoundError(msg)

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._client_secrets_path),
            scopes=self._scopes,
        )
        # port=0 picks an available ephemeral port — no fixed port conflicts
        creds = cast(
            "Credentials", flow.run_local_server(port=0, open_browser=True)
        )
        self._save_token(creds)
        logger.info("Google authentication completed successfully")
        return creds

    def _load_token(self) -> Credentials | None:
        """Load credentials from the OS keychain."""
        try:
            token_json = keyring.get_password(KEYRING_SERVICE, KEYRING_GOOGLE_TOKEN_KEY)
        except Exception:
            logger.warning("Failed to read from OS keychain")
            return None

        if token_json is None:
            return None

        try:
            data = json.loads(token_json)
            return cast(
                "Credentials",
                Credentials.from_authorized_user_info(data, self._scopes),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Stored token is invalid, will re-authenticate: %s", exc)
            return None

    def _save_token(self, creds: Credentials) -> None:
        """Persist credentials to the OS keychain."""
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else self._scopes,
        }
        try:
            keyring.set_password(
                KEYRING_SERVICE, KEYRING_GOOGLE_TOKEN_KEY, json.dumps(token_data)
            )
        except Exception:
            logger.error("Failed to store credentials in OS keychain")
            raise

    def revoke(self) -> None:
        """Remove stored credentials from the OS keychain."""
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_GOOGLE_TOKEN_KEY)
            logger.info("Google credentials removed from keychain")
        except keyring.errors.PasswordDeleteError:
            logger.debug("No stored credentials to remove")
