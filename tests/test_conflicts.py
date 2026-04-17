"""Tests for the conflicts module (Phase 2 manual resolution)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gbridge.core import conflicts as cmod
from gbridge.core.ledger import SyncLedger

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    db = tmp_path / "c.db"
    lg = SyncLedger(db)
    yield lg
    lg.close()


class TestConflicts:
    def test_record_returns_id(self, ledger: SyncLedger) -> None:
        cid = cmod.record_conflict(
            ledger,
            item_type="contact",
            google_id="people/c1",
            google_hash="gh1",
            outlook_hash="oh1",
        )
        assert isinstance(cid, int) and cid > 0

    def test_record_idempotent_on_same_key(self, ledger: SyncLedger) -> None:
        id1 = cmod.record_conflict(
            ledger,
            item_type="event",
            google_id="e1",
            google_parent_id="cal1",
            google_hash="g1",
            outlook_hash="o1",
        )
        id2 = cmod.record_conflict(
            ledger,
            item_type="event",
            google_id="e1",
            google_parent_id="cal1",
            google_hash="g2",  # hashes updated
            outlook_hash="o2",
        )
        assert id1 == id2
        row = cmod.get_conflict(ledger, id1)
        assert row is not None
        assert row.google_hash == "g2"
        assert row.outlook_hash == "o2"
        assert row.winner is None

    def test_record_after_resolution_reopens(self, ledger: SyncLedger) -> None:
        cid = cmod.record_conflict(
            ledger,
            item_type="task",
            google_id="t1",
            google_hash="g",
            outlook_hash="o",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        # New detection clears winner/resolved_at
        cmod.record_conflict(
            ledger,
            item_type="task",
            google_id="t1",
            google_hash="gX",
            outlook_hash="oX",
        )
        row = cmod.get_conflict(ledger, cid)
        assert row is not None
        assert row.winner is None
        assert row.resolved_at is None

    def test_count_unresolved(self, ledger: SyncLedger) -> None:
        assert cmod.count_unresolved(ledger) == 0
        c1 = cmod.record_conflict(
            ledger, item_type="contact", google_id="a", google_hash="g",
            outlook_hash="o",
        )
        cmod.record_conflict(
            ledger, item_type="contact", google_id="b", google_hash="g",
            outlook_hash="o",
        )
        assert cmod.count_unresolved(ledger) == 2
        cmod.resolve_conflict(ledger, c1, "google")
        assert cmod.count_unresolved(ledger) == 1

    def test_list_conflicts_unresolved_only(self, ledger: SyncLedger) -> None:
        c1 = cmod.record_conflict(
            ledger, item_type="contact", google_id="a", google_hash="g",
            outlook_hash="o",
        )
        cmod.record_conflict(
            ledger, item_type="contact", google_id="b", google_hash="g",
            outlook_hash="o",
        )
        cmod.resolve_conflict(ledger, c1, "outlook")

        unresolved = cmod.list_conflicts(ledger, unresolved_only=True)
        assert len(unresolved) == 1
        assert unresolved[0].google_id == "b"

        all_rows = cmod.list_conflicts(ledger, unresolved_only=False)
        assert len(all_rows) == 2

    def test_resolve_requires_valid_winner(self, ledger: SyncLedger) -> None:
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="a", google_hash="g",
            outlook_hash="o",
        )
        with pytest.raises(ValueError):
            cmod.resolve_conflict(ledger, cid, "bogus")  # type: ignore[arg-type]

    def test_resolve_already_resolved_noop(self, ledger: SyncLedger) -> None:
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="a", google_hash="g",
            outlook_hash="o",
        )
        assert cmod.resolve_conflict(ledger, cid, "google") is True
        # Second resolve is a no-op
        assert cmod.resolve_conflict(ledger, cid, "outlook") is False
        row = cmod.get_conflict(ledger, cid)
        assert row is not None
        assert row.winner == "google"

    def test_clear_resolved(self, ledger: SyncLedger) -> None:
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="a", google_hash="g",
            outlook_hash="o",
        )
        # Cannot clear unresolved
        assert cmod.clear_resolved(ledger, cid) is False
        cmod.resolve_conflict(ledger, cid, "google")
        assert cmod.clear_resolved(ledger, cid) is True
        assert cmod.get_conflict(ledger, cid) is None
