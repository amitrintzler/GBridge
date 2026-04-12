"""macOS autostart via a user-level launchd LaunchAgent.

Creates ``~/Library/LaunchAgents/io.gbridge.autosync.plist`` which
launchd loads automatically for the logged-in user.  No root required.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PLIST_LABEL = "io.gbridge.autosync"

_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
        <string>daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""


class MacOSInstaller:
    def _plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

    def install(self, exe_path: str) -> str:
        path = self._plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _PLIST_TEMPLATE.format(label=PLIST_LABEL, exe=exe_path),
            encoding="utf-8",
        )
        logger.info("Installed LaunchAgent at %s", path)
        return str(path)

    def uninstall(self) -> bool:
        path = self._plist_path()
        if path.exists():
            path.unlink()
            logger.info("Removed LaunchAgent %s", path)
            return True
        return False

    def is_installed(self) -> bool:
        return self._plist_path().exists()

    def location(self) -> str:
        return str(self._plist_path())
