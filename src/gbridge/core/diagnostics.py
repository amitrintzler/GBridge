"""Self-check / "doctor" — reports what's wired up and what's missing.

Read-only and side-effect-free: it never triggers interactive auth, never
writes to Google or Outlook, and never mutates the ledger. It only inspects
local state (config file, keychain presence, ledger counts, Outlook
detection) so it is safe to run any time, including from the GUI or tray.

Shared by the CLI (`gbridge doctor`), the Tk setup wizard, and the tray menu
so all three give the same answers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from gbridge.config.settings import Settings

logger = logging.getLogger(__name__)

Status = Literal["ok", "warn", "fail", "info"]

_MARK = {"ok": "[x]", "warn": "[!]", "fail": "[ ]", "info": "[i]"}


@dataclass(frozen=True)
class Check:
    """One diagnostic line."""

    name: str
    status: Status
    detail: str

    def render(self) -> str:
        return f"  {_MARK[self.status]} {self.name}: {self.detail}"


def _google_token_present() -> bool:
    try:
        import keyring

        from gbridge.config.defaults import (
            KEYRING_GOOGLE_TOKEN_KEY,
            KEYRING_SERVICE,
        )

        return keyring.get_password(KEYRING_SERVICE, KEYRING_GOOGLE_TOKEN_KEY) is not None
    except Exception:  # noqa: BLE001 - keychain may be unavailable; treat as absent
        logger.debug("Google token check failed", exc_info=True)
        return False


def _microsoft_token_present() -> bool:
    try:
        import keyring

        from gbridge.config.defaults import (
            KEYRING_MICROSOFT_TOKEN_KEY,
            KEYRING_SERVICE,
        )

        return (
            keyring.get_password(KEYRING_SERVICE, KEYRING_MICROSOFT_TOKEN_KEY)
            is not None
        )
    except Exception:  # noqa: BLE001
        logger.debug("Microsoft token check failed", exc_info=True)
        return False


def run_diagnostics(settings: Settings) -> list[Check]:
    """Inspect local state and return an ordered list of checks."""
    checks: list[Check] = []

    # 1. Google credentials file ------------------------------------------
    secrets = settings.client_secrets_path
    if secrets.exists():
        checks.append(Check("Google credentials", "ok", f"found ({secrets})"))
    else:
        checks.append(
            Check(
                "Google credentials",
                "fail",
                "missing — run 'gbridge setup' to add client_secret.json",
            )
        )

    # 2. Google sign-in ----------------------------------------------------
    if _google_token_present():
        checks.append(Check("Google sign-in", "ok", "signed in (token stored)"))
    else:
        checks.append(
            Check("Google sign-in", "fail", "not signed in — run 'gbridge setup'")
        )

    # 3. Local sync database ----------------------------------------------
    if settings.db_path.exists():
        try:
            from gbridge.core.ledger import SyncLedger

            ledger = SyncLedger(settings.db_path)
            try:
                c = len(ledger.list_items("contact"))
                e = len(ledger.list_items("event"))
                t = len(ledger.list_items("task"))
            finally:
                ledger.close()
            checks.append(
                Check(
                    "Local sync data",
                    "ok",
                    f"{c} contacts, {e} events, {t} tasks",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Local sync data", "warn", f"unreadable: {exc}"))
    else:
        checks.append(
            Check("Local sync data", "info", "none yet — run 'gbridge' to sync")
        )

    # 4. Microsoft client id ----------------------------------------------
    if settings.microsoft_client_id:
        checks.append(Check("Microsoft app ID", "ok", "configured"))
    else:
        checks.append(
            Check(
                "Microsoft app ID",
                "warn",
                "not set — Outlook sync needs "
                "'gbridge outlook auth --client-id <GUID>'",
            )
        )

    # 5. Microsoft sign-in -------------------------------------------------
    if not settings.microsoft_client_id:
        checks.append(
            Check("Microsoft sign-in", "info", "skipped (no app ID yet)")
        )
    elif _microsoft_token_present():
        checks.append(Check("Microsoft sign-in", "ok", "signed in (token stored)"))
    else:
        checks.append(
            Check(
                "Microsoft sign-in",
                "warn",
                "not signed in — run 'gbridge outlook auth'",
            )
        )

    # 6. Outlook detection -------------------------------------------------
    try:
        from gbridge.outlook.detect import detect_outlook

        outlook = detect_outlook().value
    except Exception:  # noqa: BLE001
        outlook = "unknown"
    checks.append(Check("Outlook detected", "info", outlook))

    # 7. Outlook write-back mode ------------------------------------------
    mode = settings.outlook_mode
    if mode == "disabled":
        checks.append(
            Check("Outlook write-back", "info", "disabled (Google-only sync)")
        )
    else:
        checks.append(Check("Outlook write-back", "ok", f"mode = {mode}"))

    # 8. Pending conflicts -------------------------------------------------
    if settings.db_path.exists():
        try:
            from gbridge.core import conflicts as conflicts_module
            from gbridge.core.ledger import SyncLedger

            ledger = SyncLedger(settings.db_path)
            try:
                pending = conflicts_module.count_unresolved(ledger)
            finally:
                ledger.close()
            if pending:
                checks.append(
                    Check(
                        "Conflicts",
                        "warn",
                        f"{pending} need resolution — 'gbridge conflicts list'",
                    )
                )
            else:
                checks.append(Check("Conflicts", "ok", "none pending"))
        except Exception:  # noqa: BLE001
            logger.debug("Conflict count check failed", exc_info=True)

    return checks


def summary_line(checks: list[Check]) -> str:
    """One-line headline, e.g. 'Ready to sync' or 'Setup needed'."""
    if any(c.status == "fail" for c in checks):
        return "Setup needed — see the items marked [ ] below."
    if any(c.status == "warn" for c in checks):
        return "Working, with optional steps remaining ([!] items)."
    return "All set — GBridge is ready."
