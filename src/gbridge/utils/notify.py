"""Desktop toast notifications — cross-platform via plyer.

Every notification is transparent: it tells the user exactly what
happened (counts, not data) and confirms read-only semantics.
Falls back silently if plyer / the platform toast stack is missing,
so the rest of GBridge always works.

The plyer / platform imports are performed lazily inside the
notify function so that merely importing this module is safe in
headless test environments that have no notification backend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gbridge.utils.resources import get_icon_path

if TYPE_CHECKING:
    from gbridge.core.engine import SyncStats

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECS = 10
_APP_NAME = "GBridge"


def notify(title: str, message: str, timeout: int = DEFAULT_TIMEOUT_SECS) -> bool:
    """Show a desktop toast.  Returns True on delivery, False otherwise.

    Never raises — a missing notification backend is not a reason to
    break the sync pipeline.
    """
    try:
        from plyer import notification  # lazy — headless-safe
    except ImportError:
        logger.debug("plyer not installed; notification skipped")
        return False

    icon = get_icon_path()
    try:
        notification.notify(
            title=title,
            message=message,
            app_name=_APP_NAME,
            app_icon=str(icon) if icon else "",
            timeout=timeout,
        )
        return True
    except (NotImplementedError, Exception) as exc:  # noqa: BLE001
        logger.warning("Notification delivery failed: %s", exc)
        return False


def notify_sync_result(results: dict[str, SyncStats]) -> bool:
    """Summarize a sync run and explicitly restate read-only semantics."""
    lines = []
    for rtype, stats in results.items():
        total = stats.new + stats.updated + stats.unchanged
        lines.append(
            f"{rtype.capitalize()}: {total} "
            f"({stats.new} new, {stats.updated} updated)"
        )
    body = "\n".join(lines) + "\n\nRead-only: no changes sent to Google."
    return notify("GBridge sync complete", body)
