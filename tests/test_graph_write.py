"""Tests for Graph write paths: create / update / delete + 429 / 412 handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import responses

from gbridge.config.defaults import MICROSOFT_GRAPH_BASE
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.microsoft._http import GraphClient, PreconditionFailedError
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService


@pytest.fixture
def fake_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = {"access_token": "FAKE_AT"}
    return auth


class TestContactsWrite:
    @responses.activate
    def test_create(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            json={
                "id": "NEWID",
                "@odata.etag": 'W/"1"',
                "displayName": "Alice",
                "givenName": "Alice",
                "surname": "Example",
            },
            status=201,
        )
        g = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Alice",
            given_name="Alice",
            family_name="Example",
        )
        svc = GraphPeopleService(fake_auth)
        ms = svc.create(g)
        assert ms.contact_id == "NEWID"
        assert ms.etag == 'W/"1"'

    @responses.activate
    def test_update_sends_if_match(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/CID",
            json={
                "id": "CID",
                "@odata.etag": 'W/"2"',
                "displayName": "Alice P",
            },
            status=200,
        )
        g = GoogleContact(
            resource_name="people/c1", etag="", display_name="Alice P"
        )
        svc = GraphPeopleService(fake_auth)
        svc.update("CID", g, if_match='W/"1"')
        req = responses.calls[0].request
        assert req.headers.get("If-Match") == 'W/"1"'

    @responses.activate
    def test_update_412_raises_precondition(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/CID",
            json={"error": {"code": "preconditionFailed"}},
            status=412,
        )
        g = GoogleContact(
            resource_name="people/c1", etag="", display_name="Alice"
        )
        svc = GraphPeopleService(fake_auth)
        with pytest.raises(PreconditionFailedError):
            svc.update("CID", g, if_match='W/"stale"')

    @responses.activate
    def test_delete(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/CID",
            status=204,
        )
        svc = GraphPeopleService(fake_auth)
        svc.delete("CID")  # no exception

    @responses.activate
    def test_429_retry_after(self, fake_auth: MagicMock) -> None:
        # First POST → 429 with Retry-After, then success.
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            status=429,
            headers={"Retry-After": "0"},
        )
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            json={
                "id": "NEWID",
                "@odata.etag": 'W/"1"',
                "displayName": "Alice",
            },
            status=201,
        )
        client = GraphClient(fake_auth, base_delay=0)
        svc = GraphPeopleService(fake_auth, client=client)
        ms = svc.create(
            GoogleContact(resource_name="people/c1", etag="", display_name="Alice")
        )
        assert ms.contact_id == "NEWID"
        assert len(responses.calls) == 2


class TestEventsWrite:
    @responses.activate
    def test_create_on_calendar(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/calendars/CAL1/events",
            json={
                "id": "E1",
                "@odata.etag": 'W/"1"',
                "subject": "Standup",
                "body": {"contentType": "text", "content": ""},
                "start": {
                    "dateTime": "2026-05-01T09:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2026-05-01T09:30:00",
                    "timeZone": "UTC",
                },
            },
            status=201,
        )
        ev = GoogleEvent(
            event_id="e1",
            calendar_id="primary",
            etag="",
            summary="Standup",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        svc = GraphCalendarService(fake_auth)
        ms = svc.create("CAL1", ev)
        assert ms.event_id == "E1"
        assert ms.calendar_id == "CAL1"

    @responses.activate
    def test_update_if_match(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/events/E1",
            json={
                "id": "E1",
                "@odata.etag": 'W/"2"',
                "subject": "Standup v2",
                "body": {"contentType": "text", "content": ""},
                "start": {
                    "dateTime": "2026-05-01T09:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2026-05-01T09:30:00",
                    "timeZone": "UTC",
                },
            },
            status=200,
        )
        ev = GoogleEvent(
            event_id="e1",
            calendar_id="primary",
            etag="",
            summary="Standup v2",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        svc = GraphCalendarService(fake_auth)
        svc.update("E1", "CAL1", ev, if_match='W/"1"')
        assert responses.calls[0].request.headers["If-Match"] == 'W/"1"'

    @responses.activate
    def test_delete(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/events/E1",
            status=204,
        )
        GraphCalendarService(fake_auth).delete("E1")


class TestTasksWrite:
    @responses.activate
    def test_create(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.POST,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks",
            json={
                "id": "T1",
                "@odata.etag": 'W/"1"',
                "title": "Write docs",
                "body": {"contentType": "text", "content": ""},
                "status": "notStarted",
            },
            status=201,
        )
        t = GoogleTask(
            task_id="tg", tasklist_id="list", title="Write docs"
        )
        svc = GraphTasksService(fake_auth)
        ms = svc.create("L1", t)
        assert ms.task_id == "T1"
        assert ms.status == "notStarted"

    @responses.activate
    def test_update(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks/T1",
            json={
                "id": "T1",
                "@odata.etag": 'W/"2"',
                "title": "Write docs v2",
                "body": {"contentType": "text", "content": ""},
                "status": "completed",
            },
            status=200,
        )
        t = GoogleTask(
            task_id="tg",
            tasklist_id="list",
            title="Write docs v2",
            status="completed",
        )
        svc = GraphTasksService(fake_auth)
        ms = svc.update("L1", "T1", t, if_match='W/"1"')
        assert ms.status == "completed"
        assert responses.calls[0].request.headers["If-Match"] == 'W/"1"'

    @responses.activate
    def test_delete(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.DELETE,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks/T1",
            status=204,
        )
        GraphTasksService(fake_auth).delete("L1", "T1")
