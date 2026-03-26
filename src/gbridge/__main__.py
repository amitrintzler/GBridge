"""GBridge entry point — python -m gbridge.

Provides a user-friendly CLI with clear feedback at every step.
"""

from __future__ import annotations

import argparse
import platform
import sys

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
