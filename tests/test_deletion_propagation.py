"""Tests for Google→Outlook deletion propagation.

When Google drops an item, the engine removes the ledger row. If that
row had been pushed to Outlook (has a non-empty outlook_id) we must
delete the counterpart in Outlook too. The ledger queues that work in
`pending_deletions`; the pusher drains it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import responses

from gbridge.config.defaults import MICROSOFT_GRAPH_BASE
from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "del.db")
    yield lg
    lg.close()


@pytest.fixture
def fake_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = {"access_token": "AT"}
    return auth


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.outlook_mode = "graph"
    return s


class TestLedgerQueue:
    def test_remove_queues_when_outlook_id_present(
        self, ledger: SyncLedger
    ) -> None:
        ledger.upsert_item("contact", "people/c1", "H1")
        ledger.set_outlook_state(
            item_type="contact",
            google_id="people/c1",
            outlook_id="MSID1",
            outlook_hash="H1",
            outlook_etag='W/"1"',
        )
        ledger.remove_item("contact", "people/c1")
        pending = ledger.list_pending_deletions()
        assert len(pending) == 1
        _, kind, gid, parent, outlook_id = pending[0]
        assert kind == "contact"
        assert gid == "people/c1"
        assert outlook_id == "MSID1"

    def test_remove_without_outlook_id_does_not_queue(
        self, ledger: SyncLedger
    ) -> None:
        ledger.upsert_item("contact", "people/c1", "H1")
        ledger.remove_item("contact", "people/c1")
        assert ledger.list_pending_deletions() == []

    def test_clear_deletion(self, ledger: SyncLedger) -> None:
        ledger.upsert_item("event", "E1", "H", google_parent_id="primary")
        ledger.set_outlook_state(
            item_type="event",
            google_id="E1",
            google_parent_id="primary",
            outlook_id="MSE1",
            outlook_hash="H",
        )
        ledger.remove_item("event", "E1", "primary")
        pending = ledger.list_pending_deletions()
        assert len(pending) == 1
        assert ledger.clear_pending_deletion(pending[0][0]) is True
        assert ledger.list_pending_deletions() == []


class TestGraphPusherDrainsQueue:
    @responses.activate
    def test_deletes_contact(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        # Seed: a contact that was pushed, then google-side deleted.
        ledger.upsert_item("contact", "people/c1", "H")
        ledger.set_outlook_state(
            item_type="contact",
            google_id="people/c1",
            outlook_id="MSID1",
            outlook_hash="H",
        )
        ledger.remove_item("contact", "people/c1")
        assert ledger.list_pending_deletions()

        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            status=204,
        )

        p = Pusher(
            ledger, settings, mode="graph",
            people_svc=GraphPeopleService(fake_auth),
            calendar_svc=GraphCalendarService(fake_auth),
            tasks_svc=GraphTasksService(fake_auth),
        )
        p.run_push()
        assert ledger.list_pending_deletions() == []
        assert any(
            call.request.method == "DELETE"
            for call in responses.calls
        )

    @responses.activate
    def test_deletes_task_uses_list_and_id(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        ledger.upsert_item("task", "T1", "H", google_parent_id="L1")
        ledger.set_outlook_state(
            item_type="task",
            google_id="T1",
            google_parent_id="L1",
            outlook_id="MST1",
            outlook_hash="H",
        )
        ledger.remove_item("task", "T1", "L1")

        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks/MST1",
            status=204,
        )

        p = Pusher(
            ledger, settings, mode="graph",
            people_svc=GraphPeopleService(fake_auth),
            calendar_svc=GraphCalendarService(fake_auth),
            tasks_svc=GraphTasksService(fake_auth),
        )
        p.run_push()
        assert ledger.list_pending_deletions() == []

    @responses.activate
    def test_delete_failure_keeps_row_and_counts_failure(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        ledger.upsert_item("contact", "people/c1", "H")
        ledger.set_outlook_state(
            item_type="contact",
            google_id="people/c1",
            outlook_id="MSID1",
            outlook_hash="H",
        )
        ledger.remove_item("contact", "people/c1")

        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            status=500,
            json={"error": {"code": "serverError"}},
        )

        p = Pusher(
            ledger, settings, mode="graph",
            people_svc=GraphPeopleService(fake_auth),
            calendar_svc=GraphCalendarService(fake_auth),
            tasks_svc=GraphTasksService(fake_auth),
        )
        results = p.run_push()
        # Queue row still present — will retry next cycle.
        assert ledger.list_pending_deletions()
        assert results["contacts"].failed >= 1


class TestDavPusherDrainsQueue:
    def test_dav_mode_clears_queue_after_projection(
        self, ledger: SyncLedger, tmp_path: Path
    ) -> None:
        from gbridge.dav.storage import DavProjector

        # Seed: deleted contact that had been pushed via DAV.
        ledger.upsert_item("contact", "people/c1", "H")
        ledger.set_outlook_state(
            item_type="contact",
            google_id="people/c1",
            outlook_id="dav:people/c1",
            outlook_hash="H",
        )
        ledger.remove_item("contact", "people/c1")
        assert ledger.list_pending_deletions()

        proj = DavProjector(tmp_path / "coll")
        s = MagicMock()
        s.outlook_mode = "dav"
        p = Pusher(ledger, s, mode="dav", projector=proj)
        p.run_push(contacts=[], events=[], tasks=[])
        assert ledger.list_pending_deletions() == []
