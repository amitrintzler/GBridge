"""SQLite sync ledger — tracks every synced item, its content hash, and sync state.

The ledger is the single source of truth for what GBridge has seen.
It uses WAL mode for safe concurrent reads and atomic writes via
transactions.  Schema migrations are version-tracked.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

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


class SyncItem(NamedTuple):
    """A row from the sync_items table."""

    id: int
    item_type: str
    google_id: str
    google_parent_id: str
    content_hash: str
    etag: str
    last_synced: str
    outlook_id: str


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
            # Fresh database — apply full schema
            logger.info("Initializing sync ledger at %s", self._db_path)
            self._conn.executescript(_SCHEMA_V1)
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,)
            )
            self._conn.commit()
            return

        row = self._conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        current = row[0] if row and row[0] else 0

        if current < CURRENT_SCHEMA_VERSION:
            logger.info(
                "Migrating ledger from v%d to v%d", current, CURRENT_SCHEMA_VERSION
            )
            # Future migrations go here as elif blocks
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
            "SELECT id, item_type, google_id, google_parent_id, content_hash, "
            "etag, last_synced, outlook_id "
            "FROM sync_items "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (item_type, google_id, google_parent_id),
        )
        row = cur.fetchone()
        return SyncItem(*row) if row else None

    def remove_item(
        self, item_type: str, google_id: str, google_parent_id: str = ""
    ) -> bool:
        """Delete a sync item. Returns True if a row was actually deleted."""
        cur = self._conn.execute(
            "DELETE FROM sync_items "
            "WHERE item_type = ? AND google_id = ? AND google_parent_id = ?",
            (item_type, google_id, google_parent_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_items(
        self, item_type: str, google_parent_id: str = ""
    ) -> list[SyncItem]:
        if google_parent_id:
            cur = self._conn.execute(
                "SELECT id, item_type, google_id, google_parent_id, content_hash, "
                "etag, last_synced, outlook_id "
                "FROM sync_items WHERE item_type = ? AND google_parent_id = ?",
                (item_type, google_parent_id),
            )
        else:
            cur = self._conn.execute(
                "SELECT id, item_type, google_id, google_parent_id, content_hash, "
                "etag, last_synced, outlook_id "
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
