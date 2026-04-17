"""Tests for MicrosoftAuthManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gbridge.microsoft.auth import (
    MicrosoftAuthError,
    MicrosoftAuthManager,
    MissingClientIdError,
)


class _FakeKeyring:
    """In-memory stand-in for the `keyring` module."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self.store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        if (service, key) not in self.store:
            raise RuntimeError("no password")
        del self.store[(service, key)]


class _FakeCache:
    """Minimal SerializableTokenCache stand-in."""

    def __init__(self) -> None:
        self._data = ""
        self.has_state_changed = False

    def serialize(self) -> str:
        return self._data or "{}"

    def deserialize(self, blob: str) -> None:
        self._data = blob


def _fake_msal(app: MagicMock | None = None) -> MagicMock:
    module = MagicMock()
    module.SerializableTokenCache = _FakeCache
    module.PublicClientApplication = MagicMock(return_value=app or MagicMock())
    return module


class TestMicrosoftAuthManager:
    def test_is_configured_false_when_no_client_id(self) -> None:
        mgr = MicrosoftAuthManager(
            client_id=None, _keyring=_FakeKeyring(), _msal_module=_fake_msal()
        )
        assert mgr.is_configured is False

    def test_is_configured_true(self) -> None:
        mgr = MicrosoftAuthManager(
            client_id="GUID", _keyring=_FakeKeyring(), _msal_module=_fake_msal()
        )
        assert mgr.is_configured is True

    def test_get_credentials_without_client_id_raises(self) -> None:
        mgr = MicrosoftAuthManager(
            client_id=None, _keyring=_FakeKeyring(), _msal_module=_fake_msal()
        )
        with pytest.raises(MissingClientIdError):
            mgr.get_credentials()

    def test_get_credentials_uses_silent_token(self) -> None:
        app = MagicMock()
        app.get_accounts.return_value = [{"username": "me@x.com"}]
        app.acquire_token_silent.return_value = {"access_token": "AT1"}
        mgr = MicrosoftAuthManager(
            client_id="GUID",
            _keyring=_FakeKeyring(),
            _msal_module=_fake_msal(app),
        )
        token = mgr.get_credentials()
        assert token["access_token"] == "AT1"
        app.acquire_token_silent.assert_called_once()
        app.acquire_token_interactive.assert_not_called()

    def test_get_credentials_falls_back_to_interactive(self) -> None:
        app = MagicMock()
        app.get_accounts.return_value = []
        app.acquire_token_interactive.return_value = {"access_token": "AT2"}
        mgr = MicrosoftAuthManager(
            client_id="GUID",
            _keyring=_FakeKeyring(),
            _msal_module=_fake_msal(app),
        )
        token = mgr.get_credentials()
        assert token["access_token"] == "AT2"
        app.acquire_token_interactive.assert_called_once()

    def test_authenticate_raises_on_empty_result(self) -> None:
        app = MagicMock()
        app.acquire_token_interactive.return_value = {
            "error": "auth_denied",
            "error_description": "user cancelled",
        }
        mgr = MicrosoftAuthManager(
            client_id="GUID",
            _keyring=_FakeKeyring(),
            _msal_module=_fake_msal(app),
        )
        with pytest.raises(MicrosoftAuthError, match="user cancelled"):
            mgr.authenticate()

    def test_device_code_flow_invokes_callback(self) -> None:
        app = MagicMock()
        # Interactive fails -> device code fallback
        app.acquire_token_interactive.side_effect = RuntimeError("no browser")
        app.initiate_device_flow.return_value = {
            "verification_uri": "https://microsoft.com/devicelogin",
            "user_code": "ABCD-1234",
        }
        app.acquire_token_by_device_flow.return_value = {"access_token": "AT3"}

        mgr = MicrosoftAuthManager(
            client_id="GUID",
            _keyring=_FakeKeyring(),
            _msal_module=_fake_msal(app),
        )
        seen: list[tuple[str, str]] = []
        token = mgr.authenticate(
            device_code_callback=lambda uri, code: seen.append((uri, code))
        )
        assert token["access_token"] == "AT3"
        assert seen == [("https://microsoft.com/devicelogin", "ABCD-1234")]

    def test_revoke_clears_cache_and_keyring(self) -> None:
        kr = _FakeKeyring()
        kr.set_password("gbridge", "microsoft_credentials", "{}")
        mgr = MicrosoftAuthManager(
            client_id="GUID", _keyring=kr, _msal_module=_fake_msal()
        )
        mgr.revoke()
        assert ("gbridge", "microsoft_credentials") not in kr.store

    def test_revoke_when_nothing_stored_is_quiet(self) -> None:
        mgr = MicrosoftAuthManager(
            client_id="GUID", _keyring=_FakeKeyring(), _msal_module=_fake_msal()
        )
        mgr.revoke()  # no exception

    def test_cache_loaded_from_keyring_on_init(self) -> None:
        kr = _FakeKeyring()
        kr.store[("gbridge", "microsoft_credentials")] = '{"fake": "cache"}'
        mgr = MicrosoftAuthManager(
            client_id="GUID", _keyring=kr, _msal_module=_fake_msal()
        )
        # Internal cache should have the blob we planted.
        assert mgr._cache._data == '{"fake": "cache"}'  # type: ignore[attr-defined]  # noqa: SLF001

    def test_cache_load_survives_deserialize_failure(self) -> None:
        kr = _FakeKeyring()
        kr.store[("gbridge", "microsoft_credentials")] = "garbage"
        fake_msal = _fake_msal()

        class BadCache(_FakeCache):
            def deserialize(self, blob: str) -> None:
                raise ValueError("bad blob")

        fake_msal.SerializableTokenCache = BadCache
        mgr = MicrosoftAuthManager(
            client_id="GUID", _keyring=kr, _msal_module=fake_msal
        )
        # Failure is swallowed — mgr is still usable.
        assert mgr.is_configured is True

    def test_device_code_flow_failure_raises(self) -> None:
        app = MagicMock()
        app.acquire_token_interactive.side_effect = RuntimeError("no browser")
        app.initiate_device_flow.return_value = {"error": "bad_client"}  # no user_code
        mgr = MicrosoftAuthManager(
            client_id="GUID",
            _keyring=_FakeKeyring(),
            _msal_module=_fake_msal(app),
        )
        with pytest.raises(Exception, match="device code"):
            mgr.authenticate()
