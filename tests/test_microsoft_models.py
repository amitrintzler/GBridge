"""Tests for MicrosoftContact/Event/Task and mapping helpers."""

from __future__ import annotations

from gbridge.core.hasher import content_hash
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.microsoft.mapping import (
    google_contact_to_ms_payload,
    google_event_to_ms_payload,
    google_task_to_ms_payload,
    ms_contact_to_google_shape,
    ms_event_to_google_shape,
    ms_payload_to_ms_contact,
    ms_payload_to_ms_event,
    ms_payload_to_ms_task,
    ms_status_to_google,
    ms_task_to_google_shape,
)
from gbridge.microsoft.models import MicrosoftContact, MicrosoftTask


class TestMicrosoftContact:
    def test_hash_is_stable_across_reparse(self) -> None:
        payload = {
            "id": "AAA",
            "@odata.etag": 'W/"1"',
            "displayName": "Alice",
            "givenName": "Alice",
            "surname": "Example",
            "emailAddresses": [{"address": "alice@example.com"}],
            "mobilePhone": "+1-555-0100",
            "companyName": "Acme",
            "jobTitle": "Engineer",
            "personalNotes": "",
            "lastModifiedDateTime": "2026-04-17T12:00:00Z",
        }
        c1 = ms_payload_to_ms_contact(payload)
        # Simulate server bumping only server-generated fields.
        payload2 = {
            **payload,
            "@odata.etag": 'W/"2"',
            "lastModifiedDateTime": "2026-04-17T12:30:00Z",
        }
        c2 = ms_payload_to_ms_contact(payload2)
        assert content_hash(c1) == content_hash(c2)

    def test_hash_changes_when_data_changes(self) -> None:
        base = MicrosoftContact(contact_id="A", display_name="Alice")
        changed = MicrosoftContact(contact_id="A", display_name="Alice P")
        assert content_hash(base) != content_hash(changed)


class TestContactMapping:
    def test_google_to_graph_roundtrip_preserves_hash(self) -> None:
        g = GoogleContact(
            resource_name="people/c1",
            etag="e",
            display_name="Bob Smith",
            given_name="Bob",
            family_name="Smith",
            emails=("bob@x.com",),
            phones=("+1-555-9999",),
            organization="Acme",
            title="Manager",
            notes="note",
        )
        payload = google_contact_to_ms_payload(g)
        # Graph would echo back with id + etag.
        payload_from_server = {
            **payload,
            "id": "MSID1",
            "@odata.etag": 'W/"1"',
            "emailAddresses": payload["emailAddresses"],
        }
        ms = ms_payload_to_ms_contact(payload_from_server)
        g_shape = ms_contact_to_google_shape(ms)
        assert g_shape.display_name == g.display_name
        assert g_shape.emails == g.emails
        assert g_shape.phones == g.phones
        assert g_shape.organization == g.organization

    def test_multi_phone_split(self) -> None:
        g = GoogleContact(
            resource_name="people/c1",
            etag="e",
            display_name="Multi Phone",
            phones=("+1-111", "+1-222", "+1-333"),
        )
        payload = google_contact_to_ms_payload(g)
        assert payload["mobilePhone"] == "+1-111"
        assert payload["businessPhones"] == ["+1-222", "+1-333"]


class TestEventMapping:
    def test_google_to_graph_datetime(self) -> None:
        g = GoogleEvent(
            event_id="e1",
            calendar_id="primary",
            etag="",
            summary="Standup",
            description="notes",
            location="Room 1",
            start="2026-05-01T09:00:00-05:00",
            end="2026-05-01T09:30:00-05:00",
            attendees=("a@x.com", "b@x.com"),
            status="confirmed",
        )
        payload = google_event_to_ms_payload(g, default_timezone="America/New_York")
        assert payload["subject"] == "Standup"
        assert payload["body"]["contentType"] == "text"
        assert payload["start"]["timeZone"] == "America/New_York"
        assert payload["location"] == {"displayName": "Room 1"}
        assert len(payload["attendees"]) == 2

    def test_date_only_start(self) -> None:
        g = GoogleEvent(
            event_id="e2",
            calendar_id="primary",
            etag="",
            summary="All-day",
            start="2026-05-01",
            end="2026-05-02",
        )
        payload = google_event_to_ms_payload(g)
        assert payload["start"]["dateTime"] == "2026-05-01T00:00:00"

    def test_ms_payload_parse_strips_server_fields_from_hash(self) -> None:
        payload = {
            "id": "E1",
            "@odata.etag": 'W/"1"',
            "subject": "Standup",
            "body": {"contentType": "text", "content": "daily"},
            "location": {"displayName": "Room 1"},
            "start": {"dateTime": "2026-05-01T09:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-01T09:30:00", "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": "a@x.com"}},
                {"emailAddress": {"address": "b@x.com"}},
            ],
            "isCancelled": False,
            "lastModifiedDateTime": "2026-04-17T12:00:00Z",
            "changeKey": "abc",
        }
        ev1 = ms_payload_to_ms_event(payload, calendar_id="primary")
        payload2 = {
            **payload,
            "@odata.etag": 'W/"2"',
            "lastModifiedDateTime": "2026-04-17T13:00:00Z",
            "changeKey": "xyz",
        }
        ev2 = ms_payload_to_ms_event(payload2, calendar_id="primary")
        assert content_hash(ev1) == content_hash(ev2)
        gshape = ms_event_to_google_shape(ev1)
        assert gshape.summary == "Standup"
        assert gshape.attendees == ("a@x.com", "b@x.com")


class TestTaskMapping:
    def test_google_task_to_graph_status_maps(self) -> None:
        g = GoogleTask(
            task_id="t1",
            tasklist_id="L1",
            title="Write docs",
            notes="short",
            status="needsAction",
            due="2026-05-10",
        )
        payload = google_task_to_ms_payload(g)
        assert payload["status"] == "notStarted"
        assert payload["dueDateTime"]["dateTime"] == "2026-05-10T00:00:00"

    def test_completed_round_trip(self) -> None:
        g = GoogleTask(
            task_id="t2",
            tasklist_id="L1",
            title="Done",
            status="completed",
            completed="2026-05-10T12:00:00Z",
        )
        payload = google_task_to_ms_payload(g)
        assert payload["status"] == "completed"
        assert payload["completedDateTime"]["dateTime"].startswith("2026-05-10T12:00:00")

    def test_ms_payload_parse(self) -> None:
        payload = {
            "id": "T1",
            "@odata.etag": 'W/"1"',
            "title": "Write docs",
            "body": {"contentType": "text", "content": "notes"},
            "status": "inProgress",
            "dueDateTime": {"dateTime": "2026-05-10T00:00:00", "timeZone": "UTC"},
        }
        t = ms_payload_to_ms_task(payload, tasklist_id="L1")
        assert t.title == "Write docs"
        assert t.due == "2026-05-10"
        assert t.status == "inProgress"

    def test_status_collapse(self) -> None:
        assert ms_status_to_google("inProgress") == "needsAction"
        assert ms_status_to_google("waitingOnOthers") == "needsAction"
        assert ms_status_to_google("deferred") == "needsAction"
        assert ms_status_to_google("completed") == "completed"
        assert ms_status_to_google("notStarted") == "needsAction"
        assert ms_status_to_google("unknown") == "needsAction"

    def test_google_shape_after_status_collapse(self) -> None:
        ms = MicrosoftTask(
            task_id="T", tasklist_id="L", title="X", status="waitingOnOthers"
        )
        g = ms_task_to_google_shape(ms)
        assert g.status == "needsAction"
