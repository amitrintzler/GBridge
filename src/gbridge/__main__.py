"""GBridge entry point — python -m gbridge.

Provides a user-friendly CLI with clear feedback at every step.
"""

from __future__ import annotations

import argparse
import contextlib
import platform
import sys
import webbrowser

from gbridge import __version__
from gbridge.config.defaults import GOOGLE_SCOPES
from gbridge.config.settings import Settings
from gbridge.utils.logger import setup_logger

logger = setup_logger(__name__)


def _print(msg: str = "") -> None:
    """Print to stdout (user-facing output, not log)."""
    print(msg)  # noqa: T201


def _client_secrets_instructions(path: str) -> str:
    """Return setup instructions when client_secret.json is missing."""
    return f"""
GBridge needs a Google API credentials file to connect to your account.

How to set it up (one-time, takes ~3 minutes):

  1. Go to https://console.cloud.google.com/
  2. Create a new project (or select an existing one)
  3. Enable these 3 APIs (search for each in the API Library):
       - People API
       - Google Calendar API
       - Tasks API
  4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID
  5. Choose "Desktop application" as the type
  6. Download the JSON file
  7. Rename it to "client_secret.json"
  8. Place it here:
       {path}

Then run 'gbridge' again.

Need help? See: https://github.com/amitrintzler/GBridge#setup
"""


def cmd_setup(args: argparse.Namespace) -> int:
    """Interactive one-click setup wizard — walks through everything."""
    _print(f"GBridge v{__version__} — Setup Wizard\n")
    _print("=" * 56)
    _print("  Welcome! This wizard will set up GBridge for you.")
    _print("  It takes about 5 minutes, and you only do it once.")
    _print("=" * 56)
    _print()
    _print("  SAFETY INFO:")
    _print("  - GBridge only READS from Google (contacts,")
    _print("    calendar, tasks). It CANNOT modify or delete")
    _print("    anything in your Google account.")
    _print("  - All data stays on this computer.")
    _print("  - No data is sent anywhere except to Google's")
    _print("    own servers (to read your data).")
    _print("  - GBridge is open source — anyone can inspect")
    _print("    the code at github.com/amitrintzler/GBridge")

    # Step 1: Python check
    _print("\n[Step 1/5] Checking Python version...")
    py_version = platform.python_version()
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 11):
        _print(f"  Python {py_version} is too old. GBridge needs Python 3.11+.")
        _print("  Download it from: https://www.python.org/downloads/")
        return 1
    _print(f"  Python {py_version} — OK\n")

    settings = Settings()
    secrets_path = settings.client_secrets_path

    # Step 2: Check / guide client_secret.json
    _print("[Step 2/5] Google API credentials")
    if secrets_path.exists():
        _print(f"  Found: {secrets_path} — OK\n")
    else:
        _print("  You need a Google API credentials file.")
        _print("  Follow these steps (I'll open your browser to help):\n")
        _print(_google_console_visual_guide())
        _print(f"  Then save the file as:\n    {secrets_path}\n")

        _print("  Opening Google Cloud Console in your browser...")
        webbrowser.open("https://console.cloud.google.com/apis/dashboard")

        _print("\n  When you're done, press ENTER to continue...")
        with contextlib.suppress(EOFError):
            input()

        if not secrets_path.exists():
            _print(f"  File not found at: {secrets_path}")
            _print("  Please place the file there and run 'gbridge setup' again.")
            return 1
        _print("  Found it — OK\n")

    # Step 3: Authenticate
    _print("[Step 3/5] Signing in to Google...")
    _print("  Your browser will open. Sign in and click 'Allow'.\n")
    try:
        from gbridge.google.auth import GoogleAuthManager

        auth = GoogleAuthManager(secrets_path, GOOGLE_SCOPES)
        auth.get_credentials()
    except Exception as exc:
        _print(f"  Authentication failed: {exc}")
        _print("  Please try again with 'gbridge setup'.")
        return 1
    _print("  Authenticated — OK\n")

    # Step 4: First sync
    _print("[Step 4/5] Running your first sync...")
    try:
        from gbridge.core.engine import SyncEngine
        from gbridge.core.ledger import SyncLedger

        ledger = SyncLedger(settings.db_path)
        try:
            engine = SyncEngine(ledger, auth, settings)
            results = engine.run_sync()
        finally:
            ledger.close()
    except Exception as exc:
        _print(f"  Sync failed: {exc}")
        logger.exception("Sync failed during setup")
        return 1

    _print()
    for rtype, stats in results.items():
        total = stats.new + stats.updated + stats.unchanged
        _print(f"  {rtype.capitalize():12s} {total:>5d} items synced")

    # Step 5: Done
    _print("\n[Step 5/5] Outlook detection...")
    from gbridge.outlook.detect import detect_outlook, paths_read_for_current_os

    _print("  GBridge will READ (never write) these locations to find Outlook:")
    for path in paths_read_for_current_os():
        _print(f"    - {path}")
    _print()
    outlook = detect_outlook()
    if outlook.value == "m365":
        _print("  Microsoft 365 detected — will sync via Graph API (Phase 2)")
    elif outlook.value == "standalone":
        _print("  Standalone Outlook detected — will sync via DAV server (Phase 2)")
    else:
        _print("  No Outlook detected — Outlook sync coming in Phase 2")

    _print("\n" + "=" * 56)
    _print("  Setup complete! GBridge is ready.")
    _print("=" * 56)
    _print("""
  What you can do now:

    gbridge          Run a sync (fetches latest from Google)
    gbridge status   See what's in your local sync ledger
    gbridge auth     Re-authenticate if needed

  Your Google data was NOT modified. GBridge only reads.
""")
    return 0


def _google_console_visual_guide() -> str:
    """Return an ASCII visual guide for Google Cloud Console setup."""
    return """
  +----------------------------------------------------------+
  |  STEP A: Create a Google Cloud Project                   |
  +----------------------------------------------------------+
  |                                                          |
  |  1. Go to: https://console.cloud.google.com              |
  |                                                          |
  |  2. Click the project dropdown at the top:               |
  |     +---------------------------------------------+      |
  |     | [v] Select a project          [NEW PROJECT] |      |
  |     +---------------------------------------------+      |
  |                                        ^^^^^^^^^^^       |
  |                                    Click "NEW PROJECT"   |
  |                                                          |
  |  3. Name it "GBridge" and click CREATE                   |
  +----------------------------------------------------------+

  +----------------------------------------------------------+
  |  STEP B: Enable the 3 APIs                               |
  +----------------------------------------------------------+
  |                                                          |
  |  In the search bar at the top, search for each API       |
  |  and click ENABLE:                                       |
  |                                                          |
  |  +----------------------------------------------------+  |
  |  | [Search] People API                                |  |
  |  +----------------------------------------------------+  |
  |     -> Click the result -> Click [ENABLE]                |
  |                                                          |
  |  Repeat for:                                             |
  |     [x] People API                                       |
  |     [x] Google Calendar API                              |
  |     [x] Tasks API                                        |
  +----------------------------------------------------------+

  +----------------------------------------------------------+
  |  STEP C: Create OAuth Credentials                        |
  +----------------------------------------------------------+
  |                                                          |
  |  1. In the left sidebar, click:                          |
  |     APIs & Services > Credentials                        |
  |                                                          |
  |  2. Click:  [+ CREATE CREDENTIALS]                       |
  |             > OAuth client ID                            |
  |                                                          |
  |  3. If asked for consent screen:                         |
  |     - Choose "External"                                  |
  |     - App name: "GBridge"                                |
  |     - Fill your email, click Save                        |
  |                                                          |
  |  4. Application type: [Desktop application]              |
  |     Name: "GBridge"                                      |
  |     Click [CREATE]                                       |
  |                                                          |
  |  5. On the popup, click:                                 |
  |     +----------------------------------+                 |
  |     |  [DOWNLOAD JSON]                 |                 |
  |     +----------------------------------+                 |
  |                                                          |
  |  6. Rename the downloaded file to:                       |
  |     client_secret.json                                   |
  +----------------------------------------------------------+
"""


def cmd_sync(args: argparse.Namespace) -> int:
    """Run a sync cycle: fetch from Google, compute diffs, update ledger."""
    _print(f"GBridge v{__version__}\n")

    settings = Settings()

    # Step 1: Check for client secrets
    secrets_path = settings.client_secrets_path
    if not secrets_path.exists():
        _print(_client_secrets_instructions(str(secrets_path)))
        return 1

    # Step 2: Authenticate
    _print("Connecting to Google...")
    try:
        from gbridge.google.auth import GoogleAuthManager

        auth = GoogleAuthManager(secrets_path, GOOGLE_SCOPES)
        auth.get_credentials()
    except FileNotFoundError:
        _print(f"\nError: Could not read {secrets_path}")
        _print("Make sure the file is a valid Google OAuth client secrets JSON.")
        return 1
    except Exception as exc:
        _print(f"\nAuthentication failed: {exc}")
        _print("Try running 'gbridge auth' to re-authenticate.")
        return 1

    _print("Authenticated with Google.\n")

    # Step 3: Run sync
    _print("Syncing...")
    try:
        from gbridge.core.engine import SyncEngine
        from gbridge.core.ledger import SyncLedger

        ledger = SyncLedger(settings.db_path)
        try:
            engine = SyncEngine(ledger, auth, settings)
            results = engine.run_sync()
        finally:
            ledger.close()
    except Exception as exc:
        _print(f"\nSync failed: {exc}")
        logger.exception("Sync failed")
        return 1

    # Step 4: Print human-readable summary
    _print("\nSync complete:")
    for rtype, stats in results.items():
        total = stats.new + stats.updated + stats.unchanged
        _print(
            f"  {rtype.capitalize():12s} {total:>5d} found"
            f"  ({stats.new} new, {stats.updated} updated, {stats.unchanged} unchanged)"
        )

    # Step 5: Outlook detection info (read-only inspection of the system)
    from gbridge.outlook.detect import detect_outlook

    outlook = detect_outlook()
    _print(f"\n  Outlook: {outlook.value}  (detected via read-only system lookup)")
    if outlook.value == "not_found":
        _print("  (Outlook write-back will be available in Phase 2)")

    _print("\nAll data saved locally. No changes were made to your Google account.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current sync status from the ledger."""
    _print(f"GBridge v{__version__} — Status\n")

    settings = Settings()
    db_path = settings.db_path

    if not db_path.exists():
        _print("No sync data yet. Run 'gbridge' to perform your first sync.")
        return 0

    from gbridge.core.ledger import SyncLedger

    ledger = SyncLedger(db_path)
    try:
        contacts = ledger.list_items("contact")
        events = ledger.list_items("event")
        tasks = ledger.list_items("task")

        _print(f"  Contacts in ledger:  {len(contacts)}")
        _print(f"  Events in ledger:    {len(events)}")
        _print(f"  Tasks in ledger:     {len(tasks)}")

        # Show last sync time from the most recent item
        all_items = contacts + events + tasks
        if all_items:
            latest = max(item.last_synced for item in all_items)
            _print(f"\n  Last synced: {latest}")
        else:
            _print("\n  No items synced yet.")

        _print(f"\n  Database: {db_path}")
        _print(f"  Config:   {settings.client_secrets_path}")
    finally:
        ledger.close()

    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    """Force re-authentication with Google."""
    _print(f"GBridge v{__version__} — Re-authenticate\n")

    settings = Settings()
    secrets_path = settings.client_secrets_path

    if not secrets_path.exists():
        _print(_client_secrets_instructions(str(secrets_path)))
        return 1

    from gbridge.google.auth import GoogleAuthManager

    auth = GoogleAuthManager(secrets_path, GOOGLE_SCOPES)
    auth.revoke()
    _print("Previous credentials removed.")
    _print("Opening browser for Google sign-in...\n")

    try:
        auth.authenticate()
        _print("Authentication successful!")
    except Exception as exc:
        _print(f"Authentication failed: {exc}")
        return 1

    return 0


def cmd_version(args: argparse.Namespace) -> int:
    """Print version info."""
    _print(f"GBridge v{__version__}")
    _print(f"Python {platform.python_version()} on {platform.system()}")
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run GBridge as a background service (scheduler + tray + notifications)."""
    _print(f"GBridge v{__version__} — daemon")
    _print("Running in the background.  Ctrl+C to stop.")
    from gbridge.daemon import run_daemon

    return run_daemon()


def cmd_autostart(args: argparse.Namespace) -> int:
    """Install / remove / check OS-level auto-start on login."""
    from gbridge.service import get_installer

    installer = get_installer()
    action = getattr(args, "autostart_action", "status")

    if action == "install":
        exe_path = sys.executable
        if not getattr(sys, "frozen", False):
            # Source install — prefer the 'gbridge' console script
            import shutil

            found = shutil.which("gbridge")
            if found:
                exe_path = found
        _print("GBridge autostart — installing")
        _print(f"  Writing: {installer.location()}")
        _print(f"  Command: {exe_path} daemon")
        _print("  This will run GBridge on login.  You can remove it with")
        _print("  'gbridge autostart remove' at any time.")
        installer.install(exe_path)
        _print("  Installed.")
        return 0

    if action == "remove":
        if installer.uninstall():
            _print(f"Removed autostart entry: {installer.location()}")
            return 0
        _print("Autostart was not installed — nothing to remove.")
        return 0

    # status (default)
    state = "installed" if installer.is_installed() else "not installed"
    _print(f"GBridge autostart: {state}")
    _print(f"  Location: {installer.location()}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the Tkinter setup wizard."""
    from gbridge.gui.wizard import run_gui

    return run_gui()


# ---------------------------------------------------------------------------
# Phase 2: Outlook + conflicts subcommands
# ---------------------------------------------------------------------------


def cmd_outlook(args: argparse.Namespace) -> int:
    """Dispatch for ``gbridge outlook <auth|push|status>``."""
    action = getattr(args, "outlook_action", None)
    if action == "auth":
        return cmd_outlook_auth(args)
    if action == "push":
        return cmd_outlook_push(args)
    if action == "status":
        return cmd_outlook_status(args)
    _print("Usage: gbridge outlook {auth|push|status}")
    return 2


def cmd_outlook_auth(args: argparse.Namespace) -> int:
    """Sign in (or re-sign-in) with Microsoft."""
    from gbridge.microsoft.auth import MicrosoftAuthError, MicrosoftAuthManager

    settings = Settings()
    client_id = getattr(args, "client_id", None) or settings.microsoft_client_id
    if not client_id:
        _print(
            "No Microsoft client_id configured.\n"
            "Register an Azure app at https://portal.azure.com and run:\n"
            "  gbridge outlook auth --client-id <YOUR_APP_GUID>"
        )
        return 1
    if getattr(args, "client_id", None):
        settings.set("microsoft_client_id", args.client_id)
        settings.save()

    _print(f"GBridge v{__version__} — Microsoft sign-in\n")
    mgr = MicrosoftAuthManager(
        client_id=client_id,
        tenant_id=settings.microsoft_tenant_id,
    )
    try:
        mgr.authenticate()
    except MicrosoftAuthError as exc:
        _print(f"Authentication failed: {exc}")
        return 1
    _print("Signed in to Microsoft — token cached in OS keychain.")
    return 0


def cmd_outlook_push(args: argparse.Namespace) -> int:
    """Run a single push cycle (ledger -> Outlook)."""
    from gbridge.core.ledger import SyncLedger

    settings = Settings()
    mode = settings.outlook_mode
    if mode == "disabled":
        _print("outlook_mode is 'disabled'. Set it to 'graph' or 'dav' in config.")
        return 1

    ledger = SyncLedger(settings.db_path)
    try:
        pusher = _build_cli_pusher(settings, ledger, mode, dry_run=getattr(args, "dry", False))
        if pusher is None:
            return 1
        results = pusher.run_push()
    finally:
        ledger.close()

    for rtype, stats in results.items():
        _print(
            f"  {rtype:10s} created={stats.created} updated={stats.updated} "
            f"unchanged={stats.unchanged} conflicts={stats.conflicts} "
            f"failed={stats.failed}"
        )
    return 0


def _build_cli_pusher(settings, ledger, mode, *, dry_run):
    from gbridge.core.pusher import Pusher

    if dry_run:
        return Pusher(ledger, settings, mode="dry")
    if mode == "graph":
        from gbridge.microsoft.auth import (
            MicrosoftAuthError,
            MicrosoftAuthManager,
        )
        from gbridge.microsoft.graph_calendar import GraphCalendarService
        from gbridge.microsoft.graph_people import GraphPeopleService
        from gbridge.microsoft.graph_tasks import GraphTasksService

        try:
            ms_auth = MicrosoftAuthManager(
                client_id=settings.microsoft_client_id,
                tenant_id=settings.microsoft_tenant_id,
            )
            ms_auth.get_credentials()
        except MicrosoftAuthError as exc:
            _print(f"Microsoft sign-in needed: {exc}")
            return None
        return Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(ms_auth),
            calendar_svc=GraphCalendarService(ms_auth),
            tasks_svc=GraphTasksService(ms_auth),
        )
    if mode == "dav":
        from gbridge.config.settings import get_data_dir
        from gbridge.dav.server import make_config
        from gbridge.dav.storage import DavProjector

        cfg = make_config(
            host=settings.dav_host, port=settings.dav_port,
            data_dir=get_data_dir(),
        )
        return Pusher(ledger, settings, mode="dav", projector=DavProjector(cfg.storage_dir))
    return None


def cmd_outlook_status(args: argparse.Namespace) -> int:
    """Report Outlook sync state: mode, conflicts, ledger pushed counts."""
    from gbridge.core import conflicts as conflicts_module
    from gbridge.core.ledger import SyncLedger

    settings = Settings()
    _print(f"GBridge v{__version__} — Outlook status\n")
    _print(f"  Mode: {settings.outlook_mode}")
    _print(f"  Push interval: {settings.push_interval_minutes} min")
    if settings.outlook_mode == "dav":
        _print(f"  DAV server: http://{settings.dav_host}:{settings.dav_port}/")

    if not settings.db_path.exists():
        _print("  No ledger yet — run 'gbridge sync' first.")
        return 0

    ledger = SyncLedger(settings.db_path)
    try:
        pushed = {
            "contacts": sum(1 for r in ledger.list_items("contact") if r.outlook_id),
            "events": sum(1 for r in ledger.list_items("event") if r.outlook_id),
            "tasks": sum(1 for r in ledger.list_items("task") if r.outlook_id),
        }
        pending = conflicts_module.count_unresolved(ledger)
    finally:
        ledger.close()

    _print("\n  Pushed to Outlook:")
    for k, v in pushed.items():
        _print(f"    {k:10s} {v}")
    _print(f"\n  Pending conflicts: {pending}")
    return 0


def cmd_conflicts(args: argparse.Namespace) -> int:
    """Dispatch for ``gbridge conflicts <list|resolve>``."""
    action = getattr(args, "conflicts_action", None)
    if action == "list":
        return cmd_conflicts_list(args)
    if action == "resolve":
        return cmd_conflicts_resolve(args)
    _print("Usage: gbridge conflicts {list|resolve}")
    return 2


def cmd_conflicts_list(args: argparse.Namespace) -> int:
    from gbridge.core import conflicts as conflicts_module
    from gbridge.core.ledger import SyncLedger

    settings = Settings()
    ledger = SyncLedger(settings.db_path)
    try:
        rows = conflicts_module.list_conflicts(ledger, unresolved_only=True)
    finally:
        ledger.close()
    if not rows:
        _print("No pending conflicts.")
        return 0
    _print(f"{len(rows)} pending conflict(s):\n")
    for row in rows:
        _print(f"  #{row.id:>4d}  {row.item_type:>8s}  {row.google_id}")
        _print(
            f"         detected {row.detected_at}  "
            f"google_hash={row.google_hash[:8]}…  "
            f"outlook_hash={row.outlook_hash[:8]}…"
        )
    _print("\nResolve with: gbridge conflicts resolve <id> --winner google|outlook")
    return 0


def cmd_conflicts_resolve(args: argparse.Namespace) -> int:
    from gbridge.core import conflicts as conflicts_module
    from gbridge.core.ledger import SyncLedger

    settings = Settings()
    ledger = SyncLedger(settings.db_path)
    try:
        ok = conflicts_module.resolve_conflict(
            ledger, args.conflict_id, args.winner
        )
    finally:
        ledger.close()
    if ok:
        _print(f"Conflict #{args.conflict_id} resolved; winner={args.winner}")
        return 0
    _print(
        f"No unresolved conflict with id {args.conflict_id} "
        "(may be already resolved or not found)."
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="gbridge",
        description="GBridge — Sync Google Contacts, Calendar, and Tasks with Microsoft Outlook",
    )
    parser.add_argument(
        "--version", "-V", action="store_true", help="show version and exit"
    )

    subparsers = parser.add_subparsers(dest="command")

    setup_p = subparsers.add_parser(
        "setup", help="one-click setup wizard (start here!)"
    )
    setup_p.add_argument(
        "--gui", action="store_true", help="launch the Tkinter GUI wizard"
    )
    subparsers.add_parser("sync", help="run a sync cycle (default)")
    subparsers.add_parser("status", help="show current sync status")
    subparsers.add_parser("auth", help="re-authenticate with Google")
    subparsers.add_parser("version", help="show version info")
    subparsers.add_parser(
        "daemon",
        help="run GBridge in the background (scheduler + tray + notifications)",
    )
    autostart_p = subparsers.add_parser(
        "autostart", help="install / remove auto-start on login"
    )
    autostart_p.add_argument(
        "autostart_action",
        choices=["install", "remove", "status"],
        nargs="?",
        default="status",
        help="'install', 'remove', or 'status' (default: status)",
    )
    subparsers.add_parser("gui", help="launch the Tkinter GUI wizard")

    # Phase 2 — Outlook + conflicts
    outlook_p = subparsers.add_parser(
        "outlook", help="manage Outlook write-back (Phase 2)"
    )
    outlook_sub = outlook_p.add_subparsers(dest="outlook_action")
    out_auth = outlook_sub.add_parser(
        "auth", help="sign in to Microsoft (MSAL)"
    )
    out_auth.add_argument(
        "--client-id",
        help="Azure public-client ID; saved to settings when provided",
    )
    out_push_p = outlook_sub.add_parser(
        "push", help="run a push cycle (ledger -> Outlook)"
    )
    out_push_p.add_argument(
        "--dry", action="store_true",
        help="classify but do not write",
    )
    outlook_sub.add_parser("status", help="show current Outlook state")

    conflicts_p = subparsers.add_parser(
        "conflicts", help="manage pending Outlook conflicts"
    )
    conflicts_sub = conflicts_p.add_subparsers(dest="conflicts_action")
    conflicts_sub.add_parser("list", help="list unresolved conflicts")
    resolve_p = conflicts_sub.add_parser(
        "resolve", help="resolve a conflict by id"
    )
    resolve_p.add_argument("conflict_id", type=int, help="conflict id from 'conflicts list'")
    resolve_p.add_argument(
        "--winner",
        required=True,
        choices=["google", "outlook"],
        help="which side wins",
    )

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        return cmd_version(args)

    commands = {
        "setup": cmd_setup,
        "sync": cmd_sync,
        "status": cmd_status,
        "auth": cmd_auth,
        "version": cmd_version,
        "daemon": cmd_daemon,
        "autostart": cmd_autostart,
        "gui": cmd_gui,
        "outlook": cmd_outlook,
        "conflicts": cmd_conflicts,
    }

    # --gui on the setup command redirects to the Tk wizard
    if args.command == "setup" and getattr(args, "gui", False):
        return cmd_gui(args)

    command = args.command or "sync"
    handler = commands.get(command, cmd_sync)
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
