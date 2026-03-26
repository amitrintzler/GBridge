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
    from gbridge.outlook.detect import detect_outlook

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

    # Step 5: Outlook detection info
    from gbridge.outlook.detect import detect_outlook

    outlook = detect_outlook()
    _print(f"\n  Outlook: {outlook.value}")
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

    subparsers.add_parser("setup", help="one-click setup wizard (start here!)")
    subparsers.add_parser("sync", help="run a sync cycle (default)")
    subparsers.add_parser("status", help="show current sync status")
    subparsers.add_parser("auth", help="re-authenticate with Google")
    subparsers.add_parser("version", help="show version info")

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
    }

    command = args.command or "sync"
    handler = commands.get(command, cmd_sync)
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
