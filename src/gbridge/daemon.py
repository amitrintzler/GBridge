"""Daemon mode — scheduler + tray icon + toast notifications + push.

This is what ``gbridge daemon`` runs and what the autostart service
wrappers (Windows Run-key / launchd / systemd-user) launch on login.

Design:
- Runs a sync immediately, then every ``sync_interval_minutes``.
- If Outlook write-back is enabled (``outlook_mode`` in graph|dav):
  - Second scheduler job runs a push every ``push_interval_minutes``.
  - In dav mode, a Radicale subprocess is supervised for the lifetime
    of the daemon.
- Shows a tray icon with quick actions (falls back to headless if
  no display or pystray isn't available). Tray exposes a "Resolve
  conflicts (N)" item when conflicts accumulate.
- Posts a toast after every sync / push summarising what happened.
- Clean shutdown on Ctrl+C or tray > Quit.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading

from gbridge.config.defaults import GOOGLE_SCOPES
from gbridge.config.settings import Settings, get_data_dir
from gbridge.core import conflicts as conflicts_module
from gbridge.core.engine import SyncEngine
from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher, PushStats
from gbridge.dav.server import RadicaleSupervisor
from gbridge.dav.server import make_config as make_radicale_config
from gbridge.dav.storage import DavProjector
from gbridge.google.auth import GoogleAuthManager
from gbridge.microsoft.auth import MicrosoftAuthError, MicrosoftAuthManager
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService
from gbridge.utils.notify import notify, notify_sync_result
from gbridge.utils.scheduler import make_scheduler
from gbridge.utils.tray import run_tray

logger = logging.getLogger(__name__)


class Daemon:
    """Long-running sync + push service with optional tray UI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()  # serialises sync AND push
        # Cached cross-cycle state populated during sync, consumed by push.
        self._last_sync_items: dict[str, list[object]] = {
            "contacts": [],
            "events": [],
            "tasks": [],
        }
        self._radicale: RadicaleSupervisor | None = None
        self._scheduler = make_scheduler(
            self._run_sync_safe,
            self._settings.sync_interval_minutes,
            push_fn=(
                self._run_push_safe
                if self._settings.outlook_mode != "disabled"
                else None
            ),
            push_interval_minutes=self._settings.push_interval_minutes,
        )

    # ---- sync ------------------------------------------------------------

    def _run_sync_safe(self) -> None:
        """Run a sync, posting a notification with the result."""
        if not self._lock.acquire(blocking=False):
            logger.info("Previous sync/push still running; skipping this tick")
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
                self._last_sync_items = {
                    "contacts": list(engine.last_contacts),
                    "events": list(engine.last_events),
                    "tasks": list(engine.last_tasks),
                }
            finally:
                ledger.close()
            notify_sync_result(results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Daemon sync failed")
            notify("GBridge sync failed", str(exc))
        finally:
            self._lock.release()

    # ---- push ------------------------------------------------------------

    def _run_push_safe(self) -> None:
        """Run a push cycle behind the same lock as sync."""
        if not self._lock.acquire(blocking=False):
            logger.info("Previous sync/push still running; skipping push tick")
            return
        try:
            mode = self._settings.outlook_mode
            if mode == "disabled":
                return
            ledger = SyncLedger(self._settings.db_path)
            try:
                pusher = self._build_pusher(ledger, mode)
                if pusher is None:
                    return
                results = pusher.run_push(
                    contacts=self._last_sync_items.get("contacts"),  # type: ignore[arg-type]
                    events=self._last_sync_items.get("events"),  # type: ignore[arg-type]
                    tasks=self._last_sync_items.get("tasks"),  # type: ignore[arg-type]
                )
            finally:
                ledger.close()
            self._notify_push(results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Daemon push failed")
            notify("GBridge push failed", str(exc))
        finally:
            self._lock.release()

    def _build_pusher(
        self, ledger: SyncLedger, mode: str
    ) -> Pusher | None:
        """Construct a Pusher appropriate for the configured outlook_mode."""
        if mode == "graph":
            try:
                ms_auth = MicrosoftAuthManager(
                    client_id=self._settings.microsoft_client_id,
                    tenant_id=self._settings.microsoft_tenant_id,
                )
                ms_auth.get_credentials()
            except MicrosoftAuthError as exc:
                notify("GBridge Outlook auth needed", str(exc))
                return None
            return Pusher(
                ledger,
                self._settings,
                mode="graph",
                people_svc=GraphPeopleService(ms_auth),
                calendar_svc=GraphCalendarService(ms_auth),
                tasks_svc=GraphTasksService(ms_auth),
            )
        if mode == "dav":
            cfg = make_radicale_config(
                host=self._settings.dav_host,
                port=self._settings.dav_port,
                data_dir=get_data_dir(),
            )
            projector = DavProjector(cfg.storage_dir)
            return Pusher(
                ledger, self._settings, mode="dav", projector=projector
            )
        return None

    @staticmethod
    def _notify_push(results: dict[str, PushStats]) -> None:
        bits = []
        for rtype, s in results.items():
            parts = []
            if s.created:
                parts.append(f"{s.created} new")
            if s.updated:
                parts.append(f"{s.updated} updated")
            if s.conflicts:
                parts.append(f"{s.conflicts} conflicts")
            if s.failed:
                parts.append(f"{s.failed} failed")
            if parts:
                bits.append(f"{rtype}: " + ", ".join(parts))
        if bits:
            notify("GBridge push complete", "; ".join(bits))

    # ---- tray helpers ----------------------------------------------------

    def _show_status(self) -> None:
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

    def _count_conflicts(self) -> int:
        ledger = SyncLedger(self._settings.db_path)
        try:
            return conflicts_module.count_unresolved(ledger)
        finally:
            ledger.close()

    def _run_check(self) -> None:
        """Run the read-only self-check; post the headline as a toast + log."""
        from gbridge.core.diagnostics import run_diagnostics, summary_line

        checks = run_diagnostics(self._settings)
        for c in checks:
            logger.info("doctor %s", c.render().strip())
        notify("GBridge setup check", summary_line(checks))

    def _open_conflicts(self) -> None:
        try:
            from gbridge.gui.conflicts import run_conflicts_dialog
        except Exception:  # noqa: BLE001
            logger.exception("Conflict dialog unavailable")
            notify("GBridge conflicts", "Dialog unavailable; use 'gbridge conflicts list'.")
            return
        run_conflicts_dialog(self._settings)

    # ---- lifecycle -------------------------------------------------------

    def _start_radicale_if_needed(self) -> None:
        if self._settings.outlook_mode != "dav":
            return
        cfg = make_radicale_config(
            host=self._settings.dav_host,
            port=self._settings.dav_port,
            data_dir=get_data_dir(),
        )
        self._radicale = RadicaleSupervisor(cfg)
        self._radicale.start()
        if not self._radicale.is_healthy(timeout=5.0):
            logger.error("Radicale failed to come up on %s:%d",
                         cfg.host, cfg.port)
            notify(
                "GBridge DAV warning",
                f"Radicale didn't start on port {cfg.port}",
            )
        else:
            logger.info("Radicale healthy on %s:%d", cfg.host, cfg.port)

    def _stop_radicale(self) -> None:
        if self._radicale is not None:
            self._radicale.stop()
            self._radicale = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._stop_radicale()

    def run(self) -> int:
        def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
            logger.info("Daemon received signal %d; shutting down", signum)
            self.stop()

        signal.signal(signal.SIGINT, _handle_signal)
        if hasattr(signal, "SIGTERM"):
            with contextlib.suppress(ValueError):
                signal.signal(signal.SIGTERM, _handle_signal)

        logger.info(
            "GBridge daemon starting; sync every %d min, push every %d min (mode=%s)",
            self._settings.sync_interval_minutes,
            self._settings.push_interval_minutes,
            self._settings.outlook_mode,
        )
        notify(
            "GBridge started",
            f"Auto-sync every {self._settings.sync_interval_minutes} min. "
            "Read-only — no changes are sent to Google.",
        )

        self._start_radicale_if_needed()

        # Kick an immediate sync on startup.
        threading.Thread(target=self._run_sync_safe, daemon=True).start()
        self._scheduler.start()

        tray_ok = run_tray(
            on_sync=self._run_sync_safe,
            on_status=self._show_status,
            on_quit=self.stop,
            on_push=(
                self._run_push_safe
                if self._settings.outlook_mode != "disabled"
                else None
            ),
            on_conflicts=self._open_conflicts,
            conflicts_count_fn=self._count_conflicts,
            on_check=self._run_check,
        )
        if not tray_ok:
            logger.info("Running headless (no tray) — sync will still run on schedule")
            self._stop_event.wait()

        self.stop()
        return 0


def run_daemon() -> int:
    return Daemon().run()
