"""Tests for the Pusher — Phase 2 write-back decision layer."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher, PushStats

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "pusher.db")
    yield lg
    lg.close()


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.outlook_mode = "dry"
    return s


def _seed(ledger: SyncLedger, *, item_type: str, google_id: str,
          content_hash: str, outlook_id: str = "", outlook_hash: str = "") -> None:
    ledger.upsert_item(item_type, google_id, content_hash)
    if outlook_id:
        ledger.set_outlook_state(
            item_type, google_id, outlook_id, outlook_hash,
        )


class TestPlan:
    def test_empty_ledger_returns_nothing(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        p = Pusher(ledger, settings, mode="dry")
        assert p.plan("contact") == []

    def test_create_when_no_outlook_id(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        _seed(ledger, item_type="contact", google_id="people/c1", content_hash="H1")
        p = Pusher(ledger, settings, mode="dry")
        actions = p.plan("contact")
        assert len(actions) == 1
        assert actions[0].action == "create"

    def test_noop_when_hashes_match(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        _seed(
            ledger,
            item_type="contact",
            google_id="people/c1",
            content_hash="H1",
            outlook_id="OUT1",
            outlook_hash="H1",
        )
        p = Pusher(ledger, settings, mode="dry")
        actions = p.plan("contact")
        assert actions[0].action == "noop"

    def test_update_when_content_hash_differs(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        _seed(
            ledger,
            item_type="contact",
            google_id="people/c1",
            content_hash="H2",
            outlook_id="OUT1",
            outlook_hash="H1",
        )
        p = Pusher(ledger, settings, mode="dry")
        actions = p.plan("contact")
        assert actions[0].action == "update"


class TestDryRun:
    def test_stats_classify_across_types(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        # Contact: needs create.
        _seed(ledger, item_type="contact", google_id="people/c1", content_hash="H")
        # Event: needs update (existing outlook_id, hash drift).
        _seed(
            ledger,
            item_type="event",
            google_id="E1",
            content_hash="Hnew",
            outlook_id="O1",
            outlook_hash="Hold",
        )
        # Task: already in sync.
        _seed(
            ledger,
            item_type="task",
            google_id="T1",
            content_hash="H",
            outlook_id="O2",
            outlook_hash="H",
        )

        p = Pusher(ledger, settings, mode="dry")
        results = p.run_push()

        assert results["contacts"].created == 1
        assert results["contacts"].updated == 0
        assert results["contacts"].unchanged == 0

        assert results["events"].updated == 1
        assert results["events"].created == 0

        assert results["tasks"].unchanged == 1

    def test_dry_run_never_touches_network(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        people = MagicMock()
        calendar = MagicMock()
        tasks = MagicMock()
        _seed(ledger, item_type="contact", google_id="people/c1", content_hash="H")

        p = Pusher(
            ledger,
            settings,
            mode="dry",
            people_svc=people,
            calendar_svc=calendar,
            tasks_svc=tasks,
        )
        p.run_push()

        people.create.assert_not_called()
        people.update.assert_not_called()
        people.delete.assert_not_called()
        calendar.create.assert_not_called()
        tasks.create.assert_not_called()


class TestStats:
    def test_total(self) -> None:
        s = PushStats(created=1, updated=2, unchanged=3, conflicts=4, failed=5)
        assert s.total == 15


class TestLiveModeRequiresItems:
    def test_graph_mode_without_items_fails_cleanly(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        _seed(ledger, item_type="contact", google_id="people/c1", content_hash="H")
        p = Pusher(ledger, settings, mode="graph")
        results = p.run_push()  # no items provided
        assert results["contacts"].failed == 1
        assert results["contacts"].created == 0
