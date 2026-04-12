"""Runtime lookup for bundled resource files (currently: the app icon).

Works in two modes:

- Source / development: resolves relative to the repository layout.
- Frozen (PyInstaller one-file exe): resolves to the unpacked temp
  directory at ``sys._MEIPASS``.

Exposed so Phase 3 notification code (``plyer`` toasts, ``pystray``
system tray) can find the icon without duplicating path logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

ICON_FILENAME = "gbridge.ico"


def _base_dir() -> Path:
    """Return the directory that holds bundled resources at runtime."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # PyInstaller one-file bundle — resources are extracted here.
        return Path(meipass)
    # Source tree — the icon lives in installer/windows/
    return Path(__file__).resolve().parent.parent.parent.parent / "installer" / "windows"


def get_icon_path() -> Path | None:
    """Return the path to the GBridge icon, or None if it cannot be found.

    Callers should treat a ``None`` return as "run without an icon" —
    never crash the app just because the icon is missing.
    """
    path = _base_dir() / ICON_FILENAME
    return path if path.exists() else None
