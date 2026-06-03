"""Tkinter setup wizard — GUI wrapper over the CLI setup flow.

Keeps the flow identical to ``gbridge setup`` (same backend calls) so
behavior stays consistent.  The GUI simply captures step output into a
scrollable log and runs the work in a background thread so the window
stays responsive.

Transparency: a banner at the top lists every system location GBridge
will read during detection, exactly like the CLI wizard does.
"""

from __future__ import annotations

import logging
import queue
import threading
import webbrowser

from gbridge.config.defaults import GOOGLE_SCOPES
from gbridge.config.settings import Settings
from gbridge.outlook.detect import paths_read_for_current_os

logger = logging.getLogger(__name__)


def _run_setup_steps(
    log: queue.Queue[str], settings: Settings
) -> int:
    """Execute the same steps as cmd_setup, logging progress into ``log``.

    Lives here (not in __main__) so it is independent of Tk and easy
    to unit-test.
    """
    try:
        # Step 1: client_secret present?
        secrets_path = settings.client_secrets_path
        log.put(f"Looking for credentials at: {secrets_path}")
        if not secrets_path.exists():
            log.put(
                "Credentials not found. Opening Google Cloud Console in browser — "
                "download client_secret.json and save it at the path above, "
                "then re-run this wizard."
            )
            webbrowser.open("https://console.cloud.google.com/apis/dashboard")
            return 1

        # Step 2: OAuth
        log.put("Authenticating with Google (browser will open)...")
        from gbridge.google.auth import GoogleAuthManager

        auth = GoogleAuthManager(secrets_path, GOOGLE_SCOPES)
        auth.get_credentials()
        log.put("Authenticated.")

        # Step 3: first sync
        log.put("Running first sync (read-only)...")
        from gbridge.core.engine import SyncEngine
        from gbridge.core.ledger import SyncLedger

        ledger = SyncLedger(settings.db_path)
        try:
            engine = SyncEngine(ledger, auth, settings)
            results = engine.run_sync()
        finally:
            ledger.close()

        for rtype, stats in results.items():
            total = stats.new + stats.updated + stats.unchanged
            log.put(f"  {rtype}: {total} items ({stats.new} new)")

        # Step 4 (optional): Microsoft sign-in if a client_id is configured.
        if settings.microsoft_client_id:
            log.put("Microsoft client_id present — starting Microsoft sign-in...")
            try:
                from gbridge.microsoft.auth import (
                    MicrosoftAuthError,
                    MicrosoftAuthManager,
                )

                mgr = MicrosoftAuthManager(
                    client_id=settings.microsoft_client_id,
                    tenant_id=settings.microsoft_tenant_id,
                )
                mgr.authenticate()
                log.put("Microsoft sign-in complete.")
            except MicrosoftAuthError as exc:
                log.put(f"Microsoft sign-in skipped: {exc}")
        else:
            log.put(
                "Microsoft: not configured yet. To enable Outlook write-back "
                "later, run `gbridge outlook auth --client-id <YOUR_GUID>`."
            )

        log.put("Setup complete.  Nothing was sent to Google.")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.put(f"Setup failed: {exc}")
        logger.exception("GUI setup failed")
        return 1


def run_gui() -> int:
    """Launch the Tk wizard.  Returns 0 on success, 1 on failure.

    Tk is imported lazily so headless CI never triggers a display
    connection just by importing this module.
    """
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        logger.error("Tkinter not available — install python3-tk on Linux")
        return 1

    settings = Settings()
    log_queue: queue.Queue[str] = queue.Queue()

    root = tk.Tk()
    root.title("GBridge Setup")
    root.geometry("640x480")

    banner = tk.Label(
        root,
        text=(
            "GBridge only READS from Google (contacts, calendar, tasks).\n"
            "It CANNOT modify or delete anything in your Google account."
        ),
        justify="left",
        anchor="w",
        fg="#0b5d45",
        pady=6,
    )
    banner.pack(fill="x", padx=10)

    reads_label = tk.Label(
        root,
        text="GBridge will read these locations on this machine (read-only):",
        justify="left",
        anchor="w",
        pady=2,
    )
    reads_label.pack(fill="x", padx=10)

    reads_body = tk.Label(
        root,
        text="\n".join(f"  • {p}" for p in paths_read_for_current_os()),
        justify="left",
        anchor="w",
        font=("TkFixedFont",),
    )
    reads_body.pack(fill="x", padx=10)

    log_widget = scrolledtext.ScrolledText(root, height=16, state="disabled")
    log_widget.pack(fill="both", expand=True, padx=10, pady=10)

    def _append(msg: str) -> None:
        log_widget.configure(state="normal")
        log_widget.insert("end", msg + "\n")
        log_widget.configure(state="disabled")
        log_widget.see("end")

    def _poll_queue() -> None:
        try:
            while True:
                _append(log_queue.get_nowait())
        except queue.Empty:
            pass
        root.after(100, _poll_queue)

    exit_code = {"value": 0}

    def _start() -> None:
        start_btn.configure(state="disabled")

        def _worker() -> None:
            exit_code["value"] = _run_setup_steps(log_queue, settings)
            log_queue.put("--- Done.  You can close this window. ---")

        threading.Thread(target=_worker, daemon=True).start()

    def _check() -> None:
        """Run the read-only self-check and dump it into the log pane."""
        from gbridge.core.diagnostics import run_diagnostics, summary_line

        def _worker() -> None:
            checks = run_diagnostics(settings)
            log_queue.put("")
            log_queue.put("Setup check:")
            for c in checks:
                log_queue.put(c.render())
            log_queue.put("")
            log_queue.put(summary_line(checks))

        threading.Thread(target=_worker, daemon=True).start()

    button_row = tk.Frame(root)
    button_row.pack(pady=5)
    start_btn = tk.Button(button_row, text="Start setup", command=_start)
    start_btn.pack(side="left", padx=4)
    tk.Button(button_row, text="Check setup", command=_check).pack(
        side="left", padx=4
    )

    _poll_queue()
    root.mainloop()
    return exit_code["value"]
