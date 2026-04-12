"""System tray icon — quick actions while the daemon runs.

Menu items:
  - Sync now              run a sync immediately (background thread)
  - Show status           print ledger state to stdout / log
  - What GBridge reads    open a small banner listing the system paths
                          GBridge inspects (transparency)
  - Quit                  stop the daemon cleanly

All heavy imports (pystray, PIL) are performed lazily inside
``run_tray`` so merely importing this module is safe in headless
test environments without X / display.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from gbridge.outlook.detect import paths_read_for_current_os
from gbridge.utils.resources import get_icon_path

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def run_tray(
    on_sync: Callable[[], None],
    on_status: Callable[[], None],
    on_quit: Callable[[], None],
) -> bool:
    """Run the tray icon in the current thread.

    Returns False immediately if the tray stack isn't available
    (no pystray installed, no display, etc.) so the daemon can
    fall back to headless mode without crashing.
    """
    try:
        import pystray  # lazy — may fail on headless systems
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tray icon unavailable: %s", exc)
        return False

    icon_path = get_icon_path()
    if icon_path is None:
        logger.warning("Tray icon unavailable: icon file not found")
        return False

    image = Image.open(icon_path)

    def _spawn(fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _on_sync(icon: Any, item: Any) -> None:  # noqa: ARG001
        _spawn(on_sync)

    def _on_status(icon: Any, item: Any) -> None:  # noqa: ARG001
        _spawn(on_status)

    def _on_what_we_read(icon: Any, item: Any) -> None:  # noqa: ARG001
        lines = ["GBridge reads the following locations (read-only):"]
        lines.extend(f"  - {p}" for p in paths_read_for_current_os())
        logger.info("\n".join(lines))
        # Also print so the user sees it immediately in the console.
        print("\n".join(lines))  # noqa: T201

    def _on_quit(icon: Any, item: Any) -> None:  # noqa: ARG001
        icon.stop()
        on_quit()

    menu = pystray.Menu(
        pystray.MenuItem("Sync now", _on_sync),
        pystray.MenuItem("Show status", _on_status),
        pystray.MenuItem("What GBridge reads", _on_what_we_read),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )

    icon = pystray.Icon("gbridge", image, "GBridge", menu)
    try:
        icon.run()  # blocks until Quit
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tray icon runtime error: %s", exc)
        return False
    return True
