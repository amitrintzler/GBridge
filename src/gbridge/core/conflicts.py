"""Conflict detection and manual resolution records.

A conflict is recorded when the pusher observes that BOTH sides changed since
the last successful push:
    - Google-side content_hash differs from the last Google hash we pushed.
    - Outlook-side content_hash differs from outlook_hash we stored on last push.

Conflicts are stored in the `conflicts` table (created in ledger v2). The user
resolves them one at a time via the tray dialog or the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from gbridge.core.ledger import SyncLedger


Winner = Literal["google", "outlook"]


@dataclass(frozen=True)
class Conflict:
    """A pending or resolved conflict between Google and Outlook sides."""

    id: int
    item_type: str
    google_id: str
    google_parent_id: str
    google_hash: str
    outlook_hash: str
    detected_at: str
    winner: str | None
    resolved_at: str | None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def record_conflict(
    ledger: SyncLedger,
    *,
    item_type: str,
    google_id: str,
    google_hash: str,
    outlook_hash: str,
    google_parent_id: str = "",
) -> int:
    """Insert (or refresh) a conflict row. Returns the conflict id.

    If a conflict already exists for the same (item_type, google_id, parent),
    the row is updated: detected_at refreshed, winner/resolved_at cleared so
    the user sees it again.
    """
    conn = ledger.connection
    now = _now_iso()
    conn.execute(
        "INSERT INTO conflicts (item_type, google_id, google_parent_id, "
        "google_hash, outlook_hash, detected_at, winner, resolved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL) "
        "ON CONFLICT(item_type, google_id, google_parent_id) DO UPDATE SET "
        "google_hash = excluded.google_hash, "
        "outlook_hash = excluded.outlook_hash, "
        "detected_at = excluded.detected_at, "
        "winner = NULL, "
        "resolved_at = NULL",
        (item_type, google_id, google_parent_id, google_hash, outlook_hash, now),
    )
    conn.commit()

    cur = conn.execute(
        "SELECT id FROM conflicts "
        "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
        (item_type, google_id, google_parent_id),
    )
    row = cur.fetchone()
    return int(row[0])


def list_conflicts(
    ledger: SyncLedger, *, unresolved_only: bool = True
) -> list[Conflict]:
    """Return conflicts, newest first."""
    sql = (
        "SELECT id, item_type, google_id, google_parent_id, "
        "google_hash, outlook_hash, detected_at, winner, resolved_at "
        "FROM conflicts"
    )
    if unresolved_only:
        sql += " WHERE winner IS NULL"
    sql += " ORDER BY detected_at DESC"

    cur = ledger.connection.execute(sql)
    return [Conflict(*row) for row in cur.fetchall()]


def count_unresolved(ledger: SyncLedger) -> int:
    cur = ledger.connection.execute(
        "SELECT COUNT(*) FROM conflicts WHERE winner IS NULL"
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_conflict(ledger: SyncLedger, conflict_id: int) -> Conflict | None:
    cur = ledger.connection.execute(
        "SELECT id, item_type, google_id, google_parent_id, "
        "google_hash, outlook_hash, detected_at, winner, resolved_at "
        "FROM conflicts WHERE id = ?",
        (conflict_id,),
    )
    row = cur.fetchone()
    return Conflict(*row) if row else None


def resolve_conflict(
    ledger: SyncLedger, conflict_id: int, winner: Winner
) -> bool:
    """Mark a conflict resolved.  Returns True if a row was updated.

    The pusher reads the `winner` column on the next cycle to decide whether
    to (a) overwrite Outlook with Google content ('google') or
    (b) leave Outlook alone and update our stored hashes to match ('outlook').
    """
    if winner not in ("google", "outlook"):
        raise ValueError(f"winner must be 'google' or 'outlook', got {winner!r}")

    conn = ledger.connection
    cur = conn.execute(
        "UPDATE conflicts SET winner = ?, resolved_at = ? "
        "WHERE id = ? AND winner IS NULL",
        (winner, _now_iso(), conflict_id),
    )
    conn.commit()
    return cur.rowcount > 0


def clear_resolved(ledger: SyncLedger, conflict_id: int) -> bool:
    """Remove a conflict row (used after the pusher acts on the resolution)."""
    conn = ledger.connection
    cur = conn.execute(
        "DELETE FROM conflicts WHERE id = ? AND winner IS NOT NULL",
        (conflict_id,),
    )
    conn.commit()
    return cur.rowcount > 0
