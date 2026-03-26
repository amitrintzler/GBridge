"""Shared test fixtures for GBridge."""

from __future__ import annotations

import pytest

from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask


@pytest.fixture
def sample_contact() -> GoogleContact:
    return GoogleContact(
        resource_name="people/c123456",
        etag='"etag_abc"',
        display_name="Jane Doe",
        given_name="Jane",
        family_name="Doe",
        emails=("jane@example.com", "jdoe@work.com"),
        phones=("+1-555-0100",),
        organization="Acme Corp",
        title="Engineer",
        notes="Met at conference",
        raw={"resourceName": "people/c123456"},
    )


@pytest.fixture
def sample_event() -> GoogleEvent:
    return GoogleEvent(
        event_id="evt_abc123",
        calendar_id="primary",
        etag='"event_etag"',
        summary="Team Standup",
        description="Daily sync meeting",
        location="Room 42",
        start="2025-01-15T09:00:00-05:00",
        end="2025-01-15T09:30:00-05:00",
        recurrence=("RRULE:FREQ=DAILY;COUNT=5",),
        attendees=("alice@example.com", "bob@example.com"),
        status="confirmed",
        raw={"id": "evt_abc123"},
    )


@pytest.fixture
def sample_task() -> GoogleTask:
    return GoogleTask(
        task_id="task_xyz789",
        tasklist_id="MTIzNDU2Nzg5",
        title="Review PR #42",
        notes="Check the edge cases",
        status="needsAction",
        due="2025-01-20",
        completed=None,
        updated="2025-01-15T10:00:00.000Z",
        raw={"id": "task_xyz789"},
    )


@pytest.fixture
def sample_person_response() -> dict:
    """A realistic Google People API person response."""
    return {
        "resourceName": "people/c123456",
        "etag": '"etag_abc"',
        "names": [
            {
                "displayName": "Jane Doe",
                "givenName": "Jane",
                "familyName": "Doe",
            }
        ],
        "emailAddresses": [
            {"value": "jane@example.com"},
            {"value": "jdoe@work.com"},
        ],
        "phoneNumbers": [{"value": "+1-555-0100"}],
        "organizations": [{"name": "Acme Corp", "title": "Engineer"}],
        "biographies": [{"value": "Met at conference"}],
        "metadata": {"sources": [{"type": "CONTACT"}]},
    }


@pytest.fixture
def sample_event_response() -> dict:
    """A realistic Google Calendar API event response."""
    return {
        "id": "evt_abc123",
        "etag": '"event_etag"',
        "summary": "Team Standup",
        "description": "Daily sync meeting",
        "location": "Room 42",
        "start": {"dateTime": "2025-01-15T09:00:00-05:00"},
        "end": {"dateTime": "2025-01-15T09:30:00-05:00"},
        "recurrence": ["RRULE:FREQ=DAILY;COUNT=5"],
        "attendees": [
            {"email": "alice@example.com"},
            {"email": "bob@example.com"},
        ],
        "status": "confirmed",
    }


@pytest.fixture
def sample_task_response() -> dict:
    """A realistic Google Tasks API task response."""
    return {
        "id": "task_xyz789",
        "title": "Review PR #42",
        "notes": "Check the edge cases",
        "status": "needsAction",
        "due": "2025-01-20",
        "updated": "2025-01-15T10:00:00.000Z",
    }
