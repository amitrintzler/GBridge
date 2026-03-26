"""User configuration management — JSON-based, platform-aware."""

from __future__ import annotations

import json
import logging
import os
import platform
import stat
from pathlib import Path

from gbridge.config.defaults import APP_NAME, DEFAULT_DB_NAME, DEFAULT_SYNC_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: dict[str, object] = {
    "sync_interval_minutes": DEFAULT_SYNC_INTERVAL_MINUTES,
    "db_name": DEFAULT_DB_NAME,
    "google_client_secrets_file": "client_secret.json",
    "enabled_calendars": [],
    "enabled_tasklists": [],
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
            # Restrict permissions: owner read/write only (not world-readable)
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
        return int(self._data.get("sync_interval_minutes", DEFAULT_SYNC_INTERVAL_MINUTES))  # type: ignore[arg-type]
