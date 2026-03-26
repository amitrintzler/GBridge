"""Tests for the SQLite sync ledger."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gbridge.core.ledger import SyncLedger

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
