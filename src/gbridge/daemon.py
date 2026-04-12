"""Daemon mode — scheduler + tray icon + toast notifications.

This is what ``gbridge daemon`` runs and what the autostart service
wrappers (Windows Run-key / launchd / systemd-user) launch on login.

Design:
- Runs a sync immediately, then every ``sync_interval_minutes``.
- Shows a tray icon with quick actions (falls back to headless if
  no display or pystray isn't available).
- Posts a toast after every sync summarizing what happened.
- Clean shutdown on Ctrl+C or tray > Quit.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading

from gbridge.config.defaults import GOOGLE_SCOPES
from gbridge.config.settings import Settings
from gbridge.core.engine import SyncEngine
from gbridge.core.ledger import SyncLedger
from gbridge.google.auth import GoogleAuthManager
from gbridge.utils.notify import notify, notify_sync_result
from gbridge.utils.scheduler import make_scheduler
from gbridge.utils.tray import run_tray

logger = logging.getLogger(__name__)


class Daemon:
    """Long-running sync service with optional tray UI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()  # only one sync at a time
        self._scheduler = make_scheduler(
            self._run_sync_safe, self._settings.sync_interval_minutes
        )

    def _run_sync_safe(self) -> None:
        """Run a sync, posting a notification with the result.

        All exceptions are caught and logged — a transient sync failure
        must not kill the daemon loop.
        """
        if not self._lock.acquire(blocking=False):
            logger.info("Previous sync still running; skipping this tick")
            return
        try:
            secrets_path = self._settings.client_secrets_path
            if not secrets_path.exists():
                notify(
                    "GBridge setup needed",
                    "Google credentials not found. Run 'gbridge setup'.",
                )
                return
            auth = GoogleAuthManager(secrets_path, GOOGLE_SCOPES)
            auth.get_credentials()
            ledger = SyncLedger(self._settings.db_path)
            try:
                engine = SyncEngine(ledger, auth, self._settings)
                results = engine.run_sync()
            finally:
                ledger.close()
            notify_sync_result(results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Daemon sync failed")
            notify("GBridge sync failed", str(exc))
        finally:
            self._lock.release()

    def _show_status(self) -> None:
        """Print ledger summary to stdout (tray menu action)."""
        ledger = SyncLedger(self._settings.db_path)
        try:
            counts = {
                "contacts": len(ledger.list_items("contact")),
                "events": len(ledger.list_items("event")),
                "tasks": len(ledger.list_items("task")),
            }
        finally:
            ledger.close()
        body = "  ".join(f"{k}: {v}" for k, v in counts.items())
        notify("GBridge status", body)

    def stop(self) -> None:
        """Signal the daemon to shut down."""
        self._stop_event.set()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def run(self) -> int:
        """Run until stopped.  Returns an exit code for the CLI."""
        # Graceful shutdown on SIGINT / SIGTERM (noop on Windows for SIGTERM)
        def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
            logger.info("Daemon received signal %d; shutting down", signum)
            self.stop()

        signal.signal(signal.SIGINT, _handle_signal)
        if hasattr(signal, "SIGTERM"):
            # May fail when not in the main thread (e.g. test harness)
            with contextlib.suppress(ValueError):
                signal.signal(signal.SIGTERM, _handle_signal)

        logger.info(
            "GBridge daemon starting; sync every %d minute(s)",
            self._settings.sync_interval_minutes,
        )
        notify(
            "GBridge started",
            f"Auto-sync every {self._settings.sync_interval_minutes} min. "
            "Read-only — no changes are sent to Google.",
        )

        # Run an immediate sync in a background thread so the tray
        # comes up straight away.
        threading.Thread(target=self._run_sync_safe, daemon=True).start()
        self._scheduler.start()

        # Try to show the tray; if it fails (headless), block on the
        # stop event instead so the scheduler keeps running.
        tray_ok = run_tray(
            on_sync=self._run_sync_safe,
            on_status=self._show_status,
            on_quit=self.stop,
        )
        if not tray_ok:
            logger.info("Running headless (no tray) — sync will still run on schedule")
            self._stop_event.wait()

        self.stop()
        return 0


def run_daemon() -> int:
    """Entry point used by the CLI."""
    return Daemon().run()
