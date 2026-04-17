"""Tests for the SQLite sync ledger (v2 schema)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from gbridge.core.ledger import CURRENT_SCHEMA_VERSION, SyncLedger

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    db = tmp_path / "test.db"
    lg = SyncLedger(db)
    yield lg
    lg.close()


class TestSyncLedger:
    def test_upsert_new_item(self, ledger: SyncLedger) -> None:
        changed = ledger.upsert_item("contact", "people/c1", "hash_abc")
        assert changed is True

    def test_upsert_same_hash_returns_false(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc")
        changed = ledger.upsert_item("contact", "people/c1", "hash_abc")
        assert changed is False

    def test_upsert_different_hash_returns_true(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc")
        changed = ledger.upsert_item("contact", "people/c1", "hash_def")
        assert changed is True

    def test_get_item(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc", etag="v1")
        item = ledger.get_item("contact", "people/c1")
        assert item is not None
        assert item.google_id == "people/c1"
        assert item.content_hash == "hash_abc"
        assert item.etag == "v1"
        # v2 columns default to empty / 0
        assert item.outlook_id == ""
        assert item.outlook_hash == ""
        assert item.outlook_etag == ""
        assert item.outlook_last_pushed == ""
        assert item.outlook_deleted_tombstone == 0

    def test_get_item_not_found(self, ledger: SyncLedger) -> None:
        assert ledger.get_item("contact", "people/c_nonexistent") is None

    def test_remove_item(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc")
        assert ledger.remove_item("contact", "people/c1") is True
        assert ledger.get_item("contact", "people/c1") is None

    def test_remove_nonexistent(self, ledger: SyncLedger) -> None:
        assert ledger.remove_item("contact", "people/c_nope") is False

    def test_list_items(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "h1")
        ledger.upsert_item("contact", "people/c2", "h2")
        ledger.upsert_item("event", "evt1", "h3", google_parent_id="cal1")
        items = ledger.list_items("contact")
        assert len(items) == 2

    def test_list_items_with_parent(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("event", "e1", "h1", google_parent_id="cal1")
        ledger.upsert_item("event", "e2", "h2", google_parent_id="cal2")
        items = ledger.list_items("event", google_parent_id="cal1")
        assert len(items) == 1
        assert items[0].google_id == "e1"

    def test_sync_state(self, ledger: SyncLedger) -> None:
        assert ledger.get_sync_state("people_sync_token") is None
        ledger.set_sync_state("people_sync_token", "token_123")
        assert ledger.get_sync_state("people_sync_token") == "token_123"
        ledger.set_sync_state("people_sync_token", "token_456")
        assert ledger.get_sync_state("people_sync_token") == "token_456"

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """Opening the same DB twice should not fail or duplicate schema."""
        db = tmp_path / "test2.db"
        lg1 = SyncLedger(db)
        lg1.upsert_item("contact", "people/c1", "hash_abc")
        lg1.close()

        lg2 = SyncLedger(db)
        item = lg2.get_item("contact", "people/c1")
        assert item is not None
        assert item.content_hash == "hash_abc"
        lg2.close()

    def test_parent_id_isolation(self, ledger: SyncLedger) -> None:
        """Same google_id in different parents are separate items."""
        ledger.upsert_item("event", "e1", "h1", google_parent_id="cal_a")
        ledger.upsert_item("event", "e1", "h2", google_parent_id="cal_b")
        item_a = ledger.get_item("event", "e1", "cal_a")
        item_b = ledger.get_item("event", "e1", "cal_b")
        assert item_a is not None
        assert item_b is not None
        assert item_a.content_hash == "h1"
        assert item_b.content_hash == "h2"

    # ---- v2 Outlook state ------------------------------------------------

    def test_set_outlook_state(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc")
        ledger.set_outlook_state(
            "contact",
            "people/c1",
            outlook_id="AAMkADRfMDk=",
            outlook_hash="out_hash_1",
            outlook_etag='W/"123"',
        )
        item = ledger.get_item("contact", "people/c1")
        assert item is not None
        assert item.outlook_id == "AAMkADRfMDk="
        assert item.outlook_hash == "out_hash_1"
        assert item.outlook_etag == 'W/"123"'
        assert item.outlook_last_pushed != ""

    def test_clear_outlook_state(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("contact", "people/c1", "hash_abc")
        ledger.set_outlook_state(
            "contact", "people/c1", "AAMkADRfMDk=", "out_hash_1", 'W/"123"'
        )
        ledger.clear_outlook_state("contact", "people/c1")
        item = ledger.get_item("contact", "people/c1")
        assert item is not None
        assert item.outlook_id == ""
        assert item.outlook_hash == ""
        assert item.outlook_etag == ""
        assert item.outlook_last_pushed == ""


class TestLedgerMigration:
    """Verify a v1 database upgrades cleanly to v2."""

    def _make_v1_db(self, db_path: Path) -> None:
        """Hand-rolled v1 database (pre-Phase-2)."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE sync_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type       TEXT    NOT NULL,
                google_id       TEXT    NOT NULL,
                google_parent_id TEXT   NOT NULL DEFAULT '',
                content_hash    TEXT    NOT NULL,
                etag            TEXT    NOT NULL DEFAULT '',
                last_synced     TEXT    NOT NULL,
                outlook_id      TEXT    NOT NULL DEFAULT '',
                UNIQUE(item_type, google_id, google_parent_id)
            );
            CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
            INSERT INTO schema_version (version) VALUES (1);
            INSERT INTO sync_items
                (item_type, google_id, google_parent_id, content_hash,
                 etag, last_synced, outlook_id)
            VALUES ('contact', 'people/c1', '', 'h1', 'e1', '2025-01-01T00:00:00Z', '');
            """
        )
        conn.commit()
        conn.close()

    def test_v1_to_v2_migration(self, tmp_path: Path) -> None:
        db = tmp_path / "v1.db"
        self._make_v1_db(db)

        lg = SyncLedger(db)
        try:
            row = lg.connection.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            assert row[0] == CURRENT_SCHEMA_VERSION

            # v1 row is still there
            item = lg.get_item("contact", "people/c1")
            assert item is not None
            assert item.content_hash == "h1"
            # And the new v2 columns exist and default correctly
            assert item.outlook_hash == ""
            assert item.outlook_deleted_tombstone == 0

            # conflicts table exists
            cur = lg.connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conflicts'"
            )
            assert cur.fetchone() is not None
        finally:
            lg.close()

    def test_v2_fresh_db_has_conflicts_table(self, tmp_path: Path) -> None:
        db = tmp_path / "fresh.db"
        lg = SyncLedger(db)
        try:
            cur = lg.connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conflicts'"
            )
            assert cur.fetchone() is not None
        finally:
            lg.close()
