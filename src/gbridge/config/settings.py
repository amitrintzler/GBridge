"""User configuration management — JSON-based, platform-aware."""

from __future__ import annotations

import json
import logging
import os
import platform
import stat
from pathlib import Path

from gbridge.config.defaults import (
    APP_NAME,
    DAV_HOST,
    DAV_PORT,
    DEFAULT_DB_NAME,
    DEFAULT_OUTLOOK_MODE,
    DEFAULT_PUSH_INTERVAL_MINUTES,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    MICROSOFT_DEFAULT_TENANT,
    MICROSOFT_PUBLIC_CLIENT_ID,
)

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: dict[str, object] = {
    "sync_interval_minutes": DEFAULT_SYNC_INTERVAL_MINUTES,
    "db_name": DEFAULT_DB_NAME,
    "google_client_secrets_file": "client_secret.json",
    "enabled_calendars": [],
    "enabled_tasklists": [],
    # Phase 2 — Microsoft / Outlook write-back.
    "microsoft_client_id": MICROSOFT_PUBLIC_CLIENT_ID or "",
    "microsoft_tenant_id": MICROSOFT_DEFAULT_TENANT,
    "outlook_mode": DEFAULT_OUTLOOK_MODE,
    "push_interval_minutes": DEFAULT_PUSH_INTERVAL_MINUTES,
    "dav_host": DAV_HOST,
    "dav_port": DAV_PORT,
}


def get_data_dir() -> Path:
    """Return the platform-appropriate application data directory.

    - Windows: %APPDATA%/GBridge
    - macOS:   ~/Library/Application Support/GBridge
    - Linux:   ~/.config/gbridge
    """
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        data_dir = base / APP_NAME
    elif system == "Darwin":
        data_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".config"
        data_dir = base / APP_NAME.lower()

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _config_path() -> Path:
    return get_data_dir() / "config.json"


class Settings:
    """Load and save user configuration from a JSON file."""

    def __init__(self) -> None:
        self._path = _config_path()
        self._data: dict[str, object] = {}
        self.load()

    def load(self) -> None:
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
                self._data = json.loads(text)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load config from %s: %s", self._path, exc)
                self._data = {}

        # Fill in any missing keys from defaults
        for key, default_value in _DEFAULT_CONFIG.items():
            if key not in self._data:
                self._data[key] = default_value

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # Restrict permissions: owner read/write only (not world-readable).
            # On Windows, chmod only controls the read-only flag and cannot
            # restrict access to the owner, so we skip it there.  The file
            # lives inside %APPDATA% which is already per-user.
            if platform.system() != "Windows":
                tmp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            tmp_path.replace(self._path)
        except OSError as exc:
            logger.error("Failed to save config to %s: %s", self._path, exc)
            raise

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)

    def set(self, key: str, value: object) -> None:
        self._data[key] = value

    @property
    def db_path(self) -> Path:
        name = str(self._data.get("db_name", DEFAULT_DB_NAME))
        return get_data_dir() / name

    @property
    def client_secrets_path(self) -> Path:
        name = str(self._data.get("google_client_secrets_file", "client_secret.json"))
        return get_data_dir() / name

    @property
    def sync_interval_minutes(self) -> int:
        value = self._data.get("sync_interval_minutes", DEFAULT_SYNC_INTERVAL_MINUTES)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return DEFAULT_SYNC_INTERVAL_MINUTES

    # ---- Phase 2 accessors -------------------------------------------------

    @property
    def microsoft_client_id(self) -> str | None:
        """Resolve Microsoft public client id: setting override > shipped default."""
        override = str(self._data.get("microsoft_client_id", "")).strip()
        if override:
            return override
        return MICROSOFT_PUBLIC_CLIENT_ID

    @property
    def microsoft_tenant_id(self) -> str:
        value = self._data.get("microsoft_tenant_id", MICROSOFT_DEFAULT_TENANT)
        return str(value) if value else MICROSOFT_DEFAULT_TENANT

    @property
    def outlook_mode(self) -> str:
        """One of 'disabled' | 'graph' | 'dav'."""
        value = str(self._data.get("outlook_mode", DEFAULT_OUTLOOK_MODE))
        if value not in {"disabled", "graph", "dav"}:
            logger.warning("Invalid outlook_mode %r — defaulting to 'disabled'", value)
            return "disabled"
        return value

    @property
    def push_interval_minutes(self) -> int:
        value = self._data.get("push_interval_minutes", DEFAULT_PUSH_INTERVAL_MINUTES)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return DEFAULT_PUSH_INTERVAL_MINUTES

    @property
    def dav_host(self) -> str:
        return str(self._data.get("dav_host", DAV_HOST))

    @property
    def dav_port(self) -> int:
        value = self._data.get("dav_port", DAV_PORT)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return DAV_PORT
