"""Linux autostart via a user-level systemd unit.

Creates ``~/.config/systemd/user/gbridge.service``.  The user still
has to run ``systemctl --user enable --now gbridge.service`` to
activate it — we deliberately do NOT run systemctl ourselves because
invoking systemd from our installer is a non-trivial side effect.
Install prints the exact command so the user can see and run it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

UNIT_NAME = "gbridge.service"

_UNIT_TEMPLATE = """[Unit]
Description=GBridge — Google to Outlook sync (read-only)
After=network-online.target

[Service]
Type=simple
ExecStart={exe} daemon
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


class LinuxInstaller:
    def _unit_path(self) -> Path:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / "systemd" / "user" / UNIT_NAME

    def install(self, exe_path: str) -> str:
        path = self._unit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_UNIT_TEMPLATE.format(exe=exe_path), encoding="utf-8")
        logger.info("Installed systemd user unit at %s", path)
        return str(path)

    def uninstall(self) -> bool:
        path = self._unit_path()
        if path.exists():
            path.unlink()
            logger.info("Removed systemd user unit %s", path)
            return True
        return False

    def is_installed(self) -> bool:
        return self._unit_path().exists()

    def location(self) -> str:
        return str(self._unit_path())
