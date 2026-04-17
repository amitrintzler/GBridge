"""SQLite sync ledger — tracks every synced item, its content hash, and sync state.

The ledger is the single source of truth for what GBridge has seen.
It uses WAL mode for safe concurrent reads and atomic writes via
transactions.  Schema migrations are version-tracked.

Schema history:
- v1: sync_items, sync_state, schema_version
- v2: sync_items gains outlook_hash / outlook_etag / outlook_last_pushed /
      outlook_deleted_tombstone; new conflicts table for manual resolution.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 3

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS sync_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type       TEXT    NOT NULL,   -- 'contact' | 'event' | 'task'
    google_id       TEXT    NOT NULL,   -- resource_name / event_id / task_id
    google_parent_id TEXT   NOT NULL DEFAULT '',  -- calendar_id / tasklist_id
    content_hash    TEXT    NOT NULL,   -- SHA-256 hex digest
    etag            TEXT    NOT NULL DEFAULT '',
    last_synced     TEXT    NOT NULL,   -- ISO 8601 UTC
    outlook_id      TEXT    NOT NULL DEFAULT '',   -- filled in Phase 2
    UNIQUE(item_type, google_id, google_parent_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

_MIGRATE_V1_TO_V2 = """
ALTER TABLE sync_items ADD COLUMN outlook_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE sync_items ADD COLUMN outlook_etag TEXT NOT NULL DEFAULT '';
ALTER TABLE sync_items ADD COLUMN outlook_last_pushed TEXT NOT NULL DEFAULT '';
ALTER TABLE sync_items ADD COLUMN outlook_deleted_tombstone INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS conflicts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type          TEXT    NOT NULL,
    google_id          TEXT    NOT NULL,
    google_parent_id   TEXT    NOT NULL DEFAULT '',
    google_hash        TEXT    NOT NULL,
    outlook_hash       TEXT    NOT NULL,
    detected_at        TEXT    NOT NULL,
    winner             TEXT,
    resolved_at        TEXT,
    UNIQUE(item_type, google_id, google_parent_id)
);

CREATE INDEX IF NOT EXISTS idx_conflicts_unresolved
    ON conflicts(winner) WHERE winner IS NULL;
"""

_MIGRATE_V2_TO_V3 = """
CREATE TABLE IF NOT EXISTS pending_deletions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type           TEXT    NOT NULL,
    google_id           TEXT    NOT NULL,
    google_parent_id    TEXT    NOT NULL DEFAULT '',
    outlook_id          TEXT    NOT NULL DEFAULT '',
    queued_at           TEXT    NOT NULL,
    UNIQUE(item_type, google_id, google_parent_id)
);
"""

# Fresh-database schema is v1 followed by all migrations applied in order.
_SCHEMA_V2_EXTRA = _MIGRATE_V1_TO_V2
_SCHEMA_V3_EXTRA = _MIGRATE_V2_TO_V3


class SyncItem(NamedTuple):
    """A row from the sync_items table (v2 columns)."""

    id: int
    item_type: str
    google_id: str
    google_parent_id: str
    content_hash: str
    etag: str
    last_synced: str
    outlook_id: str
    outlook_hash: str
    outlook_etag: str
    outlook_last_pushed: str
    outlook_deleted_tombstone: int


_ITEM_COLUMNS = (
    "id, item_type, google_id, google_parent_id, content_hash, "
    "etag, last_synced, outlook_id, outlook_hash, outlook_etag, "
    "outlook_last_pushed, outlook_deleted_tombstone"
)


class SyncLedger:
    """CRUD interface for the sync ledger database."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level="DEFERRED")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if cur.fetchone() is None:
            # Fresh database — apply full schema up to current version
            logger.info("Initializing sync ledger at %s", self._db_path)
            self._conn.executescript(_SCHEMA_V1)
            self._conn.executescript(_SCHEMA_V2_EXTRA)
            self._conn.executescript(_SCHEMA_V3_EXTRA)
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,),
            )
            self._conn.commit()
            return

        row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] if row and row[0] else 0

        if current >= CURRENT_SCHEMA_VERSION:
            return

        logger.info(
            "Migrating ledger from v%d to v%d", current, CURRENT_SCHEMA_VERSION
        )
        if current < 2:
            self._conn.executescript(_MIGRATE_V1_TO_V2)
        if current < 3:
            self._conn.executescript(_MIGRATE_V2_TO_V3)
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (CURRENT_SCHEMA_VERSION,),
        )
        self._conn.commit()

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def upsert_item(
        self,
        item_type: str,
        google_id: str,
        content_hash: str,
        etag: str = "",
        google_parent_id: str = "",
    ) -> bool:
        """Insert or update a sync item. Returns True if the content changed."""
        existing = self.get_item(item_type, google_id, google_parent_id)
        if existing is not None and existing.content_hash == content_hash:
            # Content unchanged — just update last_synced timestamp
            self._conn.execute(
                "UPDATE sync_items SET last_synced = ?, etag = ? "
                "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
                (self._now_iso(), etag, item_type, google_id, google_parent_id),
            )
            self._conn.commit()
            return False

        self._conn.execute(
            "INSERT INTO sync_items (item_type, google_id, google_parent_id, "
            "content_hash, etag, last_synced) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_type, google_id, google_parent_id) DO UPDATE SET "
            "content_hash = excluded.content_hash, "
            "etag = excluded.etag, "
            "last_synced = excluded.last_synced",
            (item_type, google_id, google_parent_id, content_hash, etag, self._now_iso()),
        )
        self._conn.commit()
        return True

    def get_item(
        self, item_type: str, google_id: str, google_parent_id: str = ""
    ) -> SyncItem | None:
        cur = self._conn.execute(
            f"SELECT {_ITEM_COLUMNS} "  # noqa: S608
            "FROM sync_items "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (item_type, google_id, google_parent_id),
        )
        row = cur.fetchone()
        return SyncItem(*row) if row else None

    def remove_item(
        self, item_type: str, google_id: str, google_parent_id: str = ""
    ) -> bool:
        """Delete a sync item.

        If the item had been pushed to Outlook (has a non-empty outlook_id),
        we first record a pending deletion so the next push cycle can delete
        the Outlook-side counterpart before the ledger forgets it exists.
        """
        existing = self.get_item(item_type, google_id, google_parent_id)
        if existing is not None and existing.outlook_id:
            self._conn.execute(
                "INSERT INTO pending_deletions "
                "(item_type, google_id, google_parent_id, outlook_id, queued_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(item_type, google_id, google_parent_id) DO UPDATE SET "
                "outlook_id = excluded.outlook_id, queued_at = excluded.queued_at",
                (
                    item_type,
                    google_id,
                    google_parent_id,
                    existing.outlook_id,
                    self._now_iso(),
                ),
            )
        cur = self._conn.execute(
            "DELETE FROM sync_items "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (item_type, google_id, google_parent_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ---- pending-deletion queue (Phase 2 deletion propagation) -------------

    def list_pending_deletions(self) -> list[tuple[int, str, str, str, str]]:
        """Return (id, item_type, google_id, google_parent_id, outlook_id)."""
        cur = self._conn.execute(
            "SELECT id, item_type, google_id, google_parent_id, outlook_id "
            "FROM pending_deletions ORDER BY queued_at ASC"
        )
        return [tuple(row) for row in cur.fetchall()]  # type: ignore[misc]

    def clear_pending_deletion(self, deletion_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM pending_deletions WHERE id = ?", (deletion_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_items(
        self, item_type: str, google_parent_id: str = ""
    ) -> list[SyncItem]:
        if google_parent_id:
            cur = self._conn.execute(
                f"SELECT {_ITEM_COLUMNS} "  # noqa: S608
                "FROM sync_items WHERE item_type = ? AND google_parent_id = ?",
                (item_type, google_parent_id),
            )
        else:
            cur = self._conn.execute(
                f"SELECT {_ITEM_COLUMNS} "  # noqa: S608
                "FROM sync_items WHERE item_type = ?",
                (item_type,),
            )
        return [SyncItem(*row) for row in cur.fetchall()]

    def get_sync_state(self, key: str) -> str | None:
        cur = self._conn.execute(
            "SELECT value FROM sync_state WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_sync_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    # ---- Phase 2: Outlook state on sync_items ------------------------------

    def set_outlook_state(
        self,
        item_type: str,
        google_id: str,
        outlook_id: str,
        outlook_hash: str,
        outlook_etag: str = "",
        google_parent_id: str = "",
    ) -> None:
        """Record that an item has been pushed to Outlook.

        Called by the pusher after a successful create/update on the Outlook side.
        """
        self._conn.execute(
            "UPDATE sync_items SET outlook_id = ?, outlook_hash = ?, "
            "outlook_etag = ?, outlook_last_pushed = ? "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (
                outlook_id,
                outlook_hash,
                outlook_etag,
                self._now_iso(),
                item_type,
                google_id,
                google_parent_id,
            ),
        )
        self._conn.commit()

    def clear_outlook_state(
        self,
        item_type: str,
        google_id: str,
        google_parent_id: str = "",
    ) -> None:
        """Reset Outlook-side tracking for an item (e.g., after a failed push)."""
        self._conn.execute(
            "UPDATE sync_items SET outlook_id = '', outlook_hash = '', "
            "outlook_etag = '', outlook_last_pushed = '' "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (item_type, google_id, google_parent_id),
        )
        self._conn.commit()

    # ---- Low-level access for the pusher / conflict modules ----------------

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the underlying connection for modules that extend the schema."""
        return self._conn
