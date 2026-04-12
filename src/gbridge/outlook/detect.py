# The winreg module is Windows-only in typeshed, so mypy on non-Windows
# platforms cannot verify attribute access on it.  We silence attr-defined
# errors for this file only — every winreg call is guarded by platform
# checks at runtime, so there is nothing meaningful for mypy to help with
# from a non-Windows host.
# mypy: disable-error-code="attr-defined"
"""Outlook installation and type detection.

Determines whether the user has:
- Microsoft 365 / Exchange Online (→ sync via Microsoft Graph API)
- Standalone classic Outlook without Exchange (→ sync via local DAV server)
- No Outlook detected

This detection runs once at first launch and caches the result.
It only *reads* system state — never modifies any Outlook settings,
profiles, or registry keys.

Transparency: the exact registry keys / file paths that GBridge
inspects on each OS are exposed as module-level constants so the
setup wizard can show users what will be read before detection runs.
"""

from __future__ import annotations

import logging
import platform
import shutil
from enum import Enum

logger = logging.getLogger(__name__)

# Registry paths GBridge reads on Windows.  READ-ONLY — nothing is
# ever written or modified.  Exposed for the setup wizard so the user
# can see exactly what will be inspected.
WINDOWS_REGISTRY_PATHS_READ: tuple[str, ...] = (
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE",
    r"HKCU\SOFTWARE\Microsoft\Office  (enumerates version subkeys)",
    r"HKCU\SOFTWARE\Microsoft\Office\<version>\Outlook\Profiles",
)

# Filesystem / preferences paths GBridge reads on macOS.  READ-ONLY.
MACOS_PATHS_READ: tuple[str, ...] = (
    "/Applications/Microsoft Outlook.app  (existence check only)",
    "defaults read com.microsoft.Outlook Accounts  (user preferences)",
)

# Paths GBridge checks on Linux.  READ-ONLY.
LINUX_PATHS_READ: tuple[str, ...] = (
    "$PATH lookup for 'outlook' command",
)


def paths_read_for_current_os() -> tuple[str, ...]:
    """Return the paths/keys GBridge will read on the current OS.

    Intended for transparency: the setup wizard prints this list so
    users can verify what GBridge inspects before detection runs.
    """
    system = platform.system()
    if system == "Windows":
        return WINDOWS_REGISTRY_PATHS_READ
    if system == "Darwin":
        return MACOS_PATHS_READ
    return LINUX_PATHS_READ


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
    """Detect Outlook on Windows by inspecting the registry (read-only).

    Enumerates all installed Office versions rather than hardcoding
    16.0, so Outlook 2013 (15.0), 2016/2019/2021/365 (16.0), and
    future versions are all detected.  Every registry path that is
    opened is logged for transparency.
    """
    try:
        import winreg  # noqa: F811
    except ImportError:
        # winreg not available (shouldn't happen on Windows)
        logger.warning("winreg module not available on Windows")
        return OutlookType.NOT_FOUND

    # Step 1: is Outlook installed at all?
    app_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE"
    logger.info("Reading registry (read-only): HKLM\\%s", app_path)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, app_path, access=winreg.KEY_READ
        )
        winreg.CloseKey(key)
    except FileNotFoundError:
        logger.info("Outlook not found in Windows registry")
        return OutlookType.NOT_FOUND

    # Step 2: check each installed Office version for an Exchange profile
    office_root = r"SOFTWARE\Microsoft\Office"
    for version in _enumerate_office_versions(office_root):
        profile_key_path = rf"{office_root}\{version}\Outlook\Profiles"
        logger.info("Reading registry (read-only): HKCU\\%s", profile_key_path)
        try:
            profiles_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                profile_key_path,
                access=winreg.KEY_READ,
            )
        except FileNotFoundError:
            continue

        try:
            i = 0
            while True:
                try:
                    profile_name = winreg.EnumKey(profiles_key, i)
                    if _windows_profile_has_exchange(profile_key_path, profile_name):
                        logger.info(
                            "Detected Microsoft 365 / Exchange Outlook (Office %s)",
                            version,
                        )
                        return OutlookType.M365
                    i += 1
                except OSError:
                    break
        finally:
            winreg.CloseKey(profiles_key)

    logger.info("Detected standalone Outlook (no Exchange account)")
    return OutlookType.STANDALONE


def _enumerate_office_versions(office_root: str) -> list[str]:
    """Return installed Office version subkeys (e.g. ['15.0', '16.0']).

    Reads HKCU\\SOFTWARE\\Microsoft\\Office and returns any subkey
    whose name starts with a digit — these are the version folders
    (15.0, 16.0, 17.0 …).  Read-only.
    """
    try:
        import winreg
    except ImportError:
        return []

    logger.info("Reading registry (read-only): HKCU\\%s  (enumerate versions)", office_root)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, office_root, access=winreg.KEY_READ
        )
    except (FileNotFoundError, OSError):
        return []

    versions: list[str] = []
    try:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(key, i)
                if name and name[0].isdigit():
                    versions.append(name)
                i += 1
            except OSError:
                break
    finally:
        winreg.CloseKey(key)
    return versions


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
