"""Auto-start installers — run GBridge daemon on login.

Each platform uses user-level mechanisms (no admin / sudo required):
- Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
- macOS:   ~/Library/LaunchAgents/io.gbridge.autosync.plist
- Linux:   ~/.config/systemd/user/gbridge.service

Transparency: every installer's ``location()`` returns the exact
path / registry key it writes, and ``install`` prints that path
back to the user before committing changes.
"""

from __future__ import annotations

import platform
from typing import Protocol


class ServiceInstaller(Protocol):
    """Common interface for platform autostart installers."""

    def install(self, exe_path: str) -> str: ...
    def uninstall(self) -> bool: ...
    def is_installed(self) -> bool: ...
    def location(self) -> str: ...


def get_installer() -> ServiceInstaller:
    """Return the installer implementation for the current OS."""
    system = platform.system()
    if system == "Windows":
        from gbridge.service.windows import WindowsInstaller

        return WindowsInstaller()
    if system == "Darwin":
        from gbridge.service.macos import MacOSInstaller

        return MacOSInstaller()
    from gbridge.service.linux import LinuxInstaller

    return LinuxInstaller()
