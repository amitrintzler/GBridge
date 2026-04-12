"""Windows autostart via HKCU Run key (no admin required).

Writing a value under ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
tells Windows to run that command whenever the current user logs in.
It is the simplest user-level auto-start mechanism on Windows and
requires no privilege elevation.
"""

# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "GBridge"


class WindowsInstaller:
    def install(self, exe_path: str) -> str:
        import winreg

        command = f'"{exe_path}" daemon'
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, command)
        finally:
            winreg.CloseKey(key)
        logger.info("Installed autostart at %s", self.location())
        return self.location()

    def uninstall(self) -> bool:
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, REG_VALUE_NAME)
            finally:
                winreg.CloseKey(key)
            logger.info("Removed autostart from %s", self.location())
            return True
        except FileNotFoundError:
            return False

    def is_installed(self) -> bool:
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, REG_VALUE_NAME)
                return True
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return False

    def location(self) -> str:
        return rf"HKCU\{REG_KEY}\{REG_VALUE_NAME}"
