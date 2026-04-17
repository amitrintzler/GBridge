"""Tests for Pusher graph mode — actual Graph writes + conflict handling."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import responses

from gbridge.config.defaults import MICROSOFT_GRAPH_BASE
from gbridge.core import conflicts as conflicts_module
from gbridge.core.hasher import content_hash
from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def fake_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = {"access_token": "AT"}
    return auth


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "pg.db")
    yield lg
    lg.close()


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.outlook_mode = "graph"
    return s


def _seed_contact_new(ledger: SyncLedger, c: GoogleContact) -> None:
    ledger.upsert_item("contact", c.resource_name, content_hash(c))


def _seed_contact_drift(
    ledger: SyncLedger, c: GoogleContact, *, old_outlook_id: str
) -> None:
    """Ledger shows a pushed item, but content has changed since last push."""
    ledger.upsert_item("contact", c.resource_name, content_hash(c))
    ledger.set_outlook_state(
        item_type="contact",
        google_id=c.resource_name,
        outlook_id=old_outlook_id,
        outlook_hash="OLD_HASH",
        outlook_etag='W/"1"',
    )


class TestGraphContactPush:
    @responses.activate
    def test_creates_new_contact(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Alice",
            given_name="Alice",
            family_name="Example",
        )
        _seed_contact_new(ledger, c)

        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            json={
                "id": "MSID1",
                "@odata.etag": 'W/"1"',
                "displayName": "Alice",
                "givenName": "Alice",
                "surname": "Example",
            },
            status=201,
        )

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].created == 1
        row = ledger.get_item("contact", "people/c1")
        assert row is not None
        assert row.outlook_id == "MSID1"
        assert row.outlook_etag == 'W/"1"'
        assert row.outlook_hash == row.content_hash

    @responses.activate
    def test_updates_existing_with_if_match(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Alice Prime",
            given_name="Alice",
            family_name="Prime",
        )
        _seed_contact_drift(ledger, c, old_outlook_id="MSID1")

        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={
                "id": "MSID1",
                "@odata.etag": 'W/"2"',
                "displayName": "Alice Prime",
            },
            status=200,
        )

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].updated == 1
        assert responses.calls[0].request.headers["If-Match"] == 'W/"1"'
        row = ledger.get_item("contact", "people/c1")
        assert row is not None
        assert row.outlook_etag == 'W/"2"'

    @responses.activate
    def test_412_records_conflict(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Alice v2",
        )
        _seed_contact_drift(ledger, c, old_outlook_id="MSID1")

        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"error": {"code": "preconditionFailed"}},
            status=412,
        )

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].conflicts == 1
        assert stats["contacts"].updated == 0

        pending = conflicts_module.list_conflicts(ledger)
        assert len(pending) == 1
        assert pending[0].google_id == "people/c1"

    @responses.activate
    def test_non_retryable_failure_counts_as_failed(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="A")
        _seed_contact_new(ledger, c)
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            status=403,
            json={"error": {"code": "accessDenied"}},
        )
        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].failed == 1
        assert stats["contacts"].created == 0


class TestGraphEventPush:
    @responses.activate
    def test_creates_new_event(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        e = GoogleEvent(
            event_id="E1",
            calendar_id="CAL1",
            etag="",
            summary="Standup",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        ledger.upsert_item("event", "E1", content_hash(e), google_parent_id="CAL1")

        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/calendars/CAL1/events",
            json={
                "id": "MSE1",
                "@odata.etag": 'W/"1"',
                "subject": "Standup",
                "body": {"contentType": "text", "content": ""},
                "start": {"dateTime": "2026-05-01T09:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2026-05-01T09:30:00", "timeZone": "UTC"},
            },
            status=201,
        )

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            calendar_svc=GraphCalendarService(fake_auth),
        )
        stats = p.run_push(events=[e])
        assert stats["events"].created == 1
        row = ledger.get_item("event", "E1", "CAL1")
        assert row is not None
        assert row.outlook_id == "MSE1"


class TestGraphTaskPush:
    @responses.activate
    def test_creates_new_task(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        t = GoogleTask(
            task_id="T1",
            tasklist_id="L1",
            title="Write tests",
            status="needsAction",
        )
        ledger.upsert_item("task", "T1", content_hash(t), google_parent_id="L1")

        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks",
            json={
                "id": "MST1",
                "@odata.etag": 'W/"1"',
                "title": "Write tests",
                "body": {"contentType": "text", "content": ""},
                "status": "notStarted",
            },
            status=201,
        )

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            tasks_svc=GraphTasksService(fake_auth),
        )
        stats = p.run_push(tasks=[t])
        assert stats["tasks"].created == 1
        row = ledger.get_item("task", "T1", "L1")
        assert row is not None
        assert row.outlook_id == "MST1"


class TestGraphMissingService:
    def test_contact_push_without_people_svc_raises(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="X")
        ledger.upsert_item("contact", "people/c1", content_hash(c))
        # Graph mode but no people_svc provided — pusher should flag failures.
        p = Pusher(ledger, settings, mode="graph")
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].failed == 1

    def test_event_push_without_calendar_svc(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
    ) -> None:
        e = GoogleEvent(
            event_id="E1", calendar_id="CAL", etag="",
            summary="X",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        ledger.upsert_item("event", "E1", content_hash(e), google_parent_id="CAL")
        p = Pusher(ledger, settings, mode="graph")
        stats = p.run_push(events=[e])
        assert stats["events"].failed == 1

    def test_task_push_without_tasks_svc(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
    ) -> None:
        t = GoogleTask(task_id="T1", tasklist_id="L1", title="X")
        ledger.upsert_item("task", "T1", content_hash(t), google_parent_id="L1")
        p = Pusher(ledger, settings, mode="graph")
        stats = p.run_push(tasks=[t])
        assert stats["tasks"].failed == 1


class TestGraphOrphanPlans:
    """Plan includes an item but caller's model list doesn't — treat as failed."""

    def test_ledger_row_without_matching_model(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        # Seed a ledger row but DON'T pass the corresponding model.
        c = GoogleContact(resource_name="people/c-missing", etag="", display_name="X")
        ledger.upsert_item("contact", "people/c-missing", content_hash(c))

        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push(contacts=[])  # empty list
        assert stats["contacts"].failed == 1


class TestGraphWithoutItems:
    def test_graph_mode_without_items_marks_failed(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        fake_auth: MagicMock,
    ) -> None:
        # Row in ledger but no model supplied — graph mode can't send it.
        c = GoogleContact(resource_name="people/c1", etag="", display_name="X")
        ledger.upsert_item("contact", "people/c1", content_hash(c))
        p = Pusher(
            ledger,
            settings,
            mode="graph",
            people_svc=GraphPeopleService(fake_auth),
        )
        stats = p.run_push()  # no contacts argument
        assert stats["contacts"].failed == 1
