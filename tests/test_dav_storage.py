"""Tests for the DAV storage projector (ledger -> .vcf/.ics files)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from gbridge.dav.storage import DavProjector, _ics_datetime, _safe_filename
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def projector(tmp_path: Path) -> DavProjector:
    return DavProjector(tmp_path / "collections")


class TestVcardRender:
    def test_minimal(self) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Alice Example",
            given_name="Alice",
            family_name="Example",
        )
        body = DavProjector.render_contact(c)
        assert body.startswith("BEGIN:VCARD")
        assert body.rstrip().endswith("END:VCARD")
        assert "FN:Alice Example" in body
        assert "UID:people/c1" in body

    def test_emails_phones_org(self) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            display_name="Bob Smith",
            emails=("bob@x.com", "bs@y.com"),
            phones=("+1-555-1111",),
            organization="Acme",
            title="Manager",
            notes="Met at OSCON",
        )
        body = DavProjector.render_contact(c)
        assert "bob@x.com" in body
        assert "bs@y.com" in body
        assert "+1-555-1111" in body
        assert "Acme" in body
        assert "TITLE:Manager" in body
        assert "NOTE:Met at OSCON" in body


class TestIcalEventRender:
    def test_simple_event(self) -> None:
        e = GoogleEvent(
            event_id="E1",
            calendar_id="primary",
            etag="",
            summary="Standup",
            description="Daily",
            location="Room 1",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
            attendees=("a@x.com",),
        )
        body = DavProjector.render_event(e)
        assert "BEGIN:VCALENDAR" in body
        assert "BEGIN:VEVENT" in body
        assert "SUMMARY:Standup" in body
        assert "LOCATION:Room 1" in body
        assert "UID:E1" in body
        assert "ATTENDEE:mailto:a@x.com" in body
        assert "STATUS:CONFIRMED" in body

    def test_cancelled_status(self) -> None:
        e = GoogleEvent(
            event_id="E2",
            calendar_id="primary",
            etag="",
            summary="Gone",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
            status="cancelled",
        )
        body = DavProjector.render_event(e)
        assert "STATUS:CANCELLED" in body

    def test_recurrence_roundtrip(self) -> None:
        e = GoogleEvent(
            event_id="E3",
            calendar_id="primary",
            etag="",
            summary="Weekly",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
            recurrence=("RRULE:FREQ=WEEKLY;COUNT=4",),
        )
        body = DavProjector.render_event(e)
        assert "RRULE:FREQ=WEEKLY;COUNT=4" in body


class TestIcalTaskRender:
    def test_pending_task(self) -> None:
        t = GoogleTask(
            task_id="T1",
            tasklist_id="L1",
            title="Write docs",
            notes="draft",
            status="needsAction",
            due="2026-05-10",
        )
        body = DavProjector.render_task(t)
        assert "BEGIN:VTODO" in body
        assert "SUMMARY:Write docs" in body
        assert "DUE" in body
        assert "NEEDS-ACTION" in body

    def test_completed_task(self) -> None:
        t = GoogleTask(
            task_id="T2",
            tasklist_id="L1",
            title="Ship it",
            status="completed",
            completed="2026-05-10T12:00:00Z",
        )
        body = DavProjector.render_task(t)
        assert "STATUS:COMPLETED" in body
        assert "COMPLETED:20260510T120000Z" in body


class TestProjection:
    def test_writes_collection_layout(self, projector: DavProjector) -> None:
        contacts = [
            GoogleContact(resource_name="people/c1", etag="", display_name="Alice"),
        ]
        events = [
            GoogleEvent(
                event_id="E1",
                calendar_id="primary",
                etag="",
                summary="Standup",
                start="2026-05-01T09:00:00Z",
                end="2026-05-01T09:30:00Z",
            ),
        ]
        tasks = [
            GoogleTask(task_id="T1", tasklist_id="L1", title="Write docs"),
        ]

        stats = projector.project(contacts=contacts, events=events, tasks=tasks)
        assert stats.contacts == 1
        assert stats.events == 1
        assert stats.tasks == 1
        assert stats.total == 3

        # Layout
        root = projector._root  # noqa: SLF001
        assert (root / "contacts" / ".Radicale.props").exists()
        assert (root / "calendar" / ".Radicale.props").exists()
        assert (root / "tasks" / ".Radicale.props").exists()

        props = json.loads(
            (root / "contacts" / ".Radicale.props").read_text(encoding="utf-8")
        )
        assert props["tag"] == "VADDRESSBOOK"

        # Item files
        assert any((root / "contacts").glob("*.vcf"))
        assert any((root / "calendar").glob("*.ics"))
        assert any((root / "tasks").glob("*.ics"))

    def test_deletions_propagate(self, projector: DavProjector) -> None:
        c1 = GoogleContact(resource_name="people/c1", etag="", display_name="Alice")
        c2 = GoogleContact(resource_name="people/c2", etag="", display_name="Bob")

        projector.project(contacts=[c1, c2])
        contacts_dir = projector._root / "contacts"  # noqa: SLF001
        assert len(list(contacts_dir.glob("*.vcf"))) == 2

        # Re-project with c2 removed.
        projector.project(contacts=[c1])
        remaining = list(contacts_dir.glob("*.vcf"))
        assert len(remaining) == 1
        assert "c1" in remaining[0].name or "people_c1" in remaining[0].name


class TestHelpers:
    def test_safe_filename(self) -> None:
        assert _safe_filename("people/c1") == "people_c1"
        assert _safe_filename("") == "item"
        assert _safe_filename("with space & chars") == "with_space___chars"

    def test_ics_datetime(self) -> None:
        assert _ics_datetime("2026-05-10") == "20260510"
        assert _ics_datetime("2026-05-10T09:00:00Z") == "20260510T090000Z"
        assert _ics_datetime("2026-05-10T09:00:00") == "20260510T090000"
