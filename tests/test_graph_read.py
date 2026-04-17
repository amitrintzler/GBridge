"""Tests for the Microsoft Graph read clients (people / calendar / tasks)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import responses

from gbridge.config.defaults import MICROSOFT_GRAPH_BASE
from gbridge.microsoft._http import DeltaExpiredError, GraphClient, GraphError
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService


@pytest.fixture
def fake_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = {"access_token": "FAKE_AT"}
    return auth


class TestGraphClient:
    @responses.activate
    def test_get_adds_bearer_token(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me",
            json={"displayName": "Alice"},
            status=200,
        )
        client = GraphClient(fake_auth)
        body = client.get("/me")
        assert body == {"displayName": "Alice"}
        assert responses.calls[0].request.headers["Authorization"] == "Bearer FAKE_AT"

    @responses.activate
    def test_retries_on_429_with_retry_after(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me",
            status=429,
            headers={"Retry-After": "0"},
        )
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me",
            json={"displayName": "Alice"},
            status=200,
        )
        client = GraphClient(fake_auth, base_delay=0)
        body = client.get("/me")
        assert body == {"displayName": "Alice"}
        assert len(responses.calls) == 2

    @responses.activate
    def test_410_raises_delta_expired(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta",
            status=410,
            json={"error": {"code": "syncStateNotFound"}},
        )
        client = GraphClient(fake_auth)
        with pytest.raises(DeltaExpiredError):
            client.get("/me/contacts/delta")

    @responses.activate
    def test_non_retryable_raises(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me",
            status=403,
            json={"error": {"code": "accessDenied"}},
        )
        client = GraphClient(fake_auth)
        with pytest.raises(GraphError) as excinfo:
            client.get("/me")
        assert excinfo.value.status == 403

    @responses.activate
    def test_iter_pages_follows_next_link(self, fake_auth: MagicMock) -> None:
        page1 = {
            "value": [{"id": "1"}, {"id": "2"}],
            "@odata.nextLink": f"{MICROSOFT_GRAPH_BASE}/me/contacts?$skiptoken=abc",
        }
        page2 = {
            "value": [{"id": "3"}],
            "@odata.deltaLink": f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta?$deltatoken=xyz",
        }
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            json=page1,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts",
            json=page2,
            status=200,
        )

        client = GraphClient(fake_auth)
        items, delta = client.iter_pages("/me/contacts")
        assert [i["id"] for i in items] == ["1", "2", "3"]
        assert delta and "$deltatoken=xyz" in delta


class TestGraphPeople:
    @responses.activate
    def test_fetch_parses_and_tracks_deletions(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta",
            json={
                "value": [
                    {
                        "id": "C1",
                        "@odata.etag": 'W/"1"',
                        "displayName": "Alice",
                        "givenName": "Alice",
                        "surname": "X",
                        "emailAddresses": [{"address": "a@x.com"}],
                    },
                    {"id": "C2", "@removed": {"reason": "deleted"}},
                ],
                "@odata.deltaLink": f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta?$deltatoken=T1",
            },
            status=200,
        )

        svc = GraphPeopleService(fake_auth)
        result = svc.fetch_all()
        assert len(result.items) == 1
        assert result.items[0].display_name == "Alice"
        assert result.deleted_ids == ["C2"]
        assert result.delta_link and "T1" in result.delta_link

    @responses.activate
    def test_expired_delta_falls_back_to_full(self, fake_auth: MagicMock) -> None:
        # First call with delta_link → 410, second call (full) succeeds.
        expired_link = f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta?$deltatoken=old"
        responses.add(
            responses.GET, expired_link, status=410, json={"error": {"code": "gone"}}
        )
        new_link = (
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta?$deltatoken=new"
        )
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/delta",
            json={"value": [], "@odata.deltaLink": new_link},
            status=200,
        )

        svc = GraphPeopleService(fake_auth)
        result = svc.fetch_all(delta_link=expired_link)
        assert result.items == []
        assert result.delta_link and "new" in result.delta_link


class TestGraphCalendar:
    @responses.activate
    def test_list_calendars(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/calendars",
            json={
                "value": [
                    {"id": "CAL1", "name": "Calendar", "owner": {"name": "Me"}},
                    {"id": "CAL2", "name": "Work"},
                ]
            },
            status=200,
        )

        svc = GraphCalendarService(fake_auth)
        cals = svc.list_calendars()
        assert [c["id"] for c in cals] == ["CAL1", "CAL2"]
        assert cals[0]["name"] == "Calendar"
        assert cals[0]["owner"] == "Me"
        assert cals[1]["owner"] == ""

    @responses.activate
    def test_fetch_events_parses_and_detects_deletes(
        self, fake_auth: MagicMock
    ) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/calendars/CAL1/events/delta",
            json={
                "value": [
                    {
                        "id": "E1",
                        "@odata.etag": 'W/"1"',
                        "subject": "Review",
                        "body": {"contentType": "text", "content": "agenda"},
                        "start": {
                            "dateTime": "2026-05-01T09:00:00",
                            "timeZone": "UTC",
                        },
                        "end": {
                            "dateTime": "2026-05-01T10:00:00",
                            "timeZone": "UTC",
                        },
                        "attendees": [
                            {"emailAddress": {"address": "a@x.com"}},
                        ],
                    },
                    {"id": "E2", "@removed": {"reason": "deleted"}},
                ],
                "@odata.deltaLink": "http://example.com/delta?$deltatoken=T",
            },
            status=200,
        )

        svc = GraphCalendarService(fake_auth)
        result = svc.fetch_events("CAL1")
        assert [e.event_id for e in result.items] == ["E1"]
        assert result.deleted_ids == ["E2"]
        assert result.items[0].summary == "Review"


class TestGraphTasks:
    @responses.activate
    def test_list_tasklists(self, fake_auth: MagicMock) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists",
            json={
                "value": [
                    {"id": "L1", "displayName": "Tasks"},
                    {"id": "L2", "displayName": "Shopping"},
                ]
            },
            status=200,
        )

        svc = GraphTasksService(fake_auth)
        lists = svc.list_tasklists()
        assert [lst["id"] for lst in lists] == ["L1", "L2"]
        assert lists[0]["title"] == "Tasks"

    @responses.activate
    def test_fetch_tasks_with_updated_since_filter(
        self, fake_auth: MagicMock
    ) -> None:
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks",
            json={
                "value": [
                    {
                        "id": "T1",
                        "@odata.etag": 'W/"1"',
                        "title": "Write docs",
                        "body": {"contentType": "text", "content": "notes"},
                        "status": "inProgress",
                    }
                ]
            },
            status=200,
        )

        svc = GraphTasksService(fake_auth)
        tasks = svc.fetch_tasks("L1", updated_since="2026-04-01T00:00:00Z")
        assert len(tasks) == 1
        assert tasks[0].title == "Write docs"
        assert tasks[0].status == "inProgress"

        # The $filter query param should have been sent. `$` is URL-encoded
        # to %24 and spaces to +/%20 depending on encoder — normalise first.
        call_url = responses.calls[0].request.url
        from urllib.parse import unquote

        decoded = unquote(call_url).replace("+", " ")
        assert "$filter=lastModifiedDateTime gt 2026-04-01T00:00:00Z" in decoded
