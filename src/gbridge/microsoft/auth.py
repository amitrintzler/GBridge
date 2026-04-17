"""Microsoft authentication via MSAL, with token cache in the OS keychain.

Design notes:
- Uses `msal.PublicClientApplication` — appropriate for desktop apps, no
  client secret required.
- Primary flow is interactive browser auth; device-code flow is available as
  a headless fallback.
- Token cache is persisted to the OS keychain under
  (KEYRING_SERVICE, KEYRING_MICROSOFT_TOKEN_KEY), parallel to the Google
  token layout. Tokens are never written to disk in plain text.
- Parallel in shape to gbridge.google.auth.GoogleAuthManager so the daemon,
  CLI, and setup wizard can treat the two auth managers symmetrically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import keyring
import msal

from gbridge.config.defaults import (
    KEYRING_MICROSOFT_TOKEN_KEY,
    KEYRING_SERVICE,
    MICROSOFT_AUTHORITY_TEMPLATE,
    MICROSOFT_DEFAULT_TENANT,
    MICROSOFT_SCOPES,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class MicrosoftAuthError(RuntimeError):
    """Base class for Microsoft auth failures surfaced to callers / CLI."""


class MissingClientIdError(MicrosoftAuthError):
    """No Microsoft client_id configured. User must register an Azure app."""

    def __init__(self) -> None:
        super().__init__(
            "Microsoft client_id is not configured.\n\n"
            "To enable Outlook sync you need to register a Microsoft "
            "Azure app (free):\n"
            "  1. Visit https://portal.azure.com/ → Azure Active Directory "
            "→ App registrations\n"
            "  2. Click 'New registration', name it 'GBridge', "
            "supported account types = 'Personal + work/school'\n"
            "  3. Redirect URI: Public client / native, "
            "http://localhost\n"
            "  4. Copy the Application (client) ID, then set it in GBridge:\n"
            "       gbridge outlook auth --client-id <YOUR_GUID>\n"
        )


class MicrosoftAuthManager:
    """Manage Microsoft OAuth 2.0 credentials with keychain persistence.

    The manager holds an MSAL PublicClientApplication and an in-memory
    serializable token cache. After every successful acquire / refresh the
    cache is dumped to the keychain so the next process can reuse silently.
    """

    def __init__(
        self,
        client_id: str | None,
        tenant_id: str = MICROSOFT_DEFAULT_TENANT,
        scopes: list[str] | None = None,
        *,
        _keyring: Any | None = None,
        _msal_module: Any | None = None,
    ) -> None:
        """Create an auth manager.

        Args:
            client_id: Azure app registration id. ``None`` means "not
                configured"; any method that requires auth will raise
                MissingClientIdError.
            tenant_id: 'common' (default), 'consumers', 'organizations',
                or a tenant GUID.
            scopes: Graph scopes. Defaults to MICROSOFT_SCOPES.
            _keyring / _msal_module: test seams.
        """
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = list(scopes) if scopes else list(MICROSOFT_SCOPES)
        self._keyring = _keyring or keyring
        self._msal = _msal_module or msal
        self._cache = self._msal.SerializableTokenCache()
        self._load_cache()
        self._app: Any | None = None

    # ---- public surface ----------------------------------------------------

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id)

    def get_credentials(self) -> dict[str, Any]:
        """Return a valid token dict or re-authenticate.

        The returned dict includes at least ``access_token`` and the scopes
        granted. Callers should pass ``access_token`` as a bearer token in
        the Authorization header when calling Microsoft Graph.
        """
        if not self._client_id:
            raise MissingClientIdError
        app = self._get_app()

        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(self._scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return dict(result)
            logger.info("Silent Microsoft token refresh returned no token")

        # No cached account or silent refresh failed — interactive flow.
        return self.authenticate()

    def authenticate(
        self,
        *,
        device_code_callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        """Interactive authentication.

        Opens the user's browser by default. If browser launch fails, falls
        back to the device-code flow. ``device_code_callback`` is invoked
        with (verification_uri, user_code) during device-code flow so the
        CLI / GUI can display them to the user.
        """
        if not self._client_id:
            raise MissingClientIdError
        app = self._get_app()

        try:
            result = app.acquire_token_interactive(self._scopes)
        except Exception as exc:  # browser flow failed — try device code
            logger.info("Interactive Microsoft auth failed (%s); device code", exc)
            result = self._device_code_flow(device_code_callback)

        if "access_token" not in result:
            err = result.get("error_description", result.get("error", "unknown"))
            raise MicrosoftAuthError(f"Microsoft authentication failed: {err}")

        self._save_cache()
        logger.info("Microsoft authentication completed successfully")
        return dict(result)

    def revoke(self) -> None:
        """Clear the cached Microsoft token from the OS keychain.

        MSAL does not expose a server-side revoke for public clients; this
        only clears the *local* cache. The user can revoke the consent from
        their Microsoft account page if they want to cut server access too.
        """
        try:
            self._keyring.delete_password(
                KEYRING_SERVICE, KEYRING_MICROSOFT_TOKEN_KEY
            )
            logger.info("Microsoft token cache cleared from keychain")
        except Exception:  # keyring.errors.PasswordDeleteError is vendor-specific
            logger.debug("No stored Microsoft credentials to remove")
        # Reset in-memory cache so get_credentials will re-auth.
        self._cache = self._msal.SerializableTokenCache()
        self._app = None

    # ---- internals ---------------------------------------------------------

    def _get_app(self) -> Any:
        if self._app is None:
            authority = MICROSOFT_AUTHORITY_TEMPLATE.format(tenant=self._tenant_id)
            self._app = self._msal.PublicClientApplication(
                self._client_id,
                authority=authority,
                token_cache=self._cache,
            )
        return self._app

    def _device_code_flow(
        self, callback: Callable[[str, str], None] | None
    ) -> dict[str, Any]:
        app = self._get_app()
        flow = app.initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow:
            raise MicrosoftAuthError(
                f"Failed to start device code flow: {flow.get('error')}"
            )
        if callback is not None:
            callback(flow["verification_uri"], flow["user_code"])
        else:
            logger.info(
                "Microsoft device code: visit %s and enter %s",
                flow["verification_uri"],
                flow["user_code"],
            )
        return dict(app.acquire_token_by_device_flow(flow))

    def _load_cache(self) -> None:
        try:
            blob = self._keyring.get_password(
                KEYRING_SERVICE, KEYRING_MICROSOFT_TOKEN_KEY
            )
        except Exception:
            logger.warning("Failed to read Microsoft token from OS keychain")
            return
        if blob:
            try:
                self._cache.deserialize(blob)
            except Exception as exc:
                logger.warning("Stored Microsoft token is invalid: %s", exc)

    def _save_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        try:
            self._keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_MICROSOFT_TOKEN_KEY,
                self._cache.serialize(),
            )
        except Exception:
            logger.exception("Failed to store Microsoft credentials in keychain")
            raise
