"""Outlook installation and type detection.

Determines whether the user has:
- Microsoft 365 / Exchange Online (→ sync via Microsoft Graph API)
- Standalone classic Outlook without Exchange (→ sync via local DAV server)
- No Outlook detected

This detection runs once at first launch and caches the result.
It only *reads* system state — never modifies any Outlook settings,
profiles, or registry keys.
"""

from __future__ import annotations

import logging
import platform
import shutil
from enum import Enum

logger = logging.getLogger(__name__)


class OutlookType(Enum):
    """The type of Outlook installation detected."""

    M365 = "m365"  # Microsoft 365 / Exchange Online
    STANDALONE = "standalone"  # Classic Outlook without Exchange
    NOT_FOUND = "not_found"  # No Outlook detected


def detect_outlook() -> OutlookType:
    """Detect which type of Outlook is installed on this system.

    This function is read-only — it inspects registry keys, file paths,
    and plists but never writes anything.
    """
    system = platform.system()

    if system == "Windows":
        return _detect_windows()
    elif system == "Darwin":
        return _detect_macos()
    else:
        return _detect_linux()


def _detect_windows() -> OutlookType:
    """Detect Outlook on Windows by inspecting the registry (read-only)."""
    try:
        import winreg  # noqa: F811

        # Check if Outlook is installed by looking for the application path
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE",
                access=winreg.KEY_READ,
            )
            winreg.CloseKey(key)
        except FileNotFoundError:
            logger.info("Outlook not found in Windows registry")
            return OutlookType.NOT_FOUND

        # Check for Exchange/M365 account in Outlook profiles
        # Look under the default profile for Exchange account entries
        profile_key_path = r"SOFTWARE\Microsoft\Office\16.0\Outlook\Profiles"
        try:
            profiles_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                profile_key_path,
                access=winreg.KEY_READ,
            )
            # Enumerate profile subkeys
            i = 0
            while True:
                try:
                    profile_name = winreg.EnumKey(profiles_key, i)
                    if _windows_profile_has_exchange(profile_key_path, profile_name):
                        winreg.CloseKey(profiles_key)
                        logger.info("Detected Microsoft 365 / Exchange Outlook")
                        return OutlookType.M365
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(profiles_key)
        except FileNotFoundError:
            pass

        logger.info("Detected standalone Outlook (no Exchange account)")
        return OutlookType.STANDALONE

    except ImportError:
        # winreg not available (shouldn't happen on Windows)
        logger.warning("winreg module not available on Windows")
        return OutlookType.NOT_FOUND


def _windows_profile_has_exchange(profiles_path: str, profile_name: str) -> bool:
    """Check if an Outlook profile contains an Exchange account (read-only)."""
    try:
        import winreg

        # Exchange accounts store configuration under specific GUIDs
        # Look for the "001f6641" property (Exchange account marker)
        profile_path = rf"{profiles_path}\{profile_name}"
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, profile_path, access=winreg.KEY_READ
        )
        # Enumerate subkeys looking for Exchange service entries
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name, access=winreg.KEY_READ)
                try:
                    # Exchange accounts have a "001f6641" value (account type)
                    winreg.QueryValueEx(subkey, "001f6641")
                    winreg.CloseKey(subkey)
                    winreg.CloseKey(key)
                    return True
                except FileNotFoundError:
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except (ImportError, OSError):
        pass
    return False


def _detect_macos() -> OutlookType:
    """Detect Outlook on macOS by checking app bundle and preferences (read-only)."""
    import subprocess
    from pathlib import Path

    outlook_app = Path("/Applications/Microsoft Outlook.app")
    if not outlook_app.exists():
        logger.info("Microsoft Outlook.app not found in /Applications")
        return OutlookType.NOT_FOUND

    # Check for Exchange accounts in Outlook's preferences via defaults read
    try:
        result = subprocess.run(
            ["defaults", "read", "com.microsoft.Outlook", "Accounts"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "Exchange" in result.stdout:
            logger.info("Detected Microsoft 365 / Exchange Outlook on macOS")
            return OutlookType.M365
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.debug("Could not read Outlook preferences on macOS")

    logger.info("Detected standalone Outlook on macOS (no Exchange account)")
    return OutlookType.STANDALONE


def _detect_linux() -> OutlookType:
    """Detect Outlook on Linux.

    Native Outlook is not available on Linux. Check for the new
    Outlook PWA or Flatpak, but default to NOT_FOUND since most
    Linux users will use PATH B (local DAV server + Thunderbird/GNOME).
    """
    # Check for the new Outlook (PWA) via msedge or similar
    if shutil.which("outlook"):
        logger.info("Found 'outlook' command on Linux — assuming standalone")
        return OutlookType.STANDALONE

    logger.info("No Outlook detected on Linux — will use DAV path")
    return OutlookType.NOT_FOUND
