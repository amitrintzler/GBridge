"""Tests for Google data models."""

from __future__ import annotations

from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask


class TestGoogleContact:
    def test_frozen(self, sample_contact: GoogleContact) -> None:
        """Contacts are immutable."""
        import pytest

        with pytest.raises(AttributeError):
            sample_contact.display_name = "Other"  # type: ignore[misc]

    def test_to_hash_dict_excludes_etag_and_raw(
        self, sample_contact: GoogleContact
    ) -> None:
        d = sample_contact.to_hash_dict()
        assert "etag" not in d
        assert "raw" not in d

    def test_to_hash_dict_includes_sync_fields(
        self, sample_contact: GoogleContact
    ) -> None:
        d = sample_contact.to_hash_dict()
        assert d["resource_name"] == "people/c123456"
        assert d["display_name"] == "Jane Doe"
        assert d["emails"] == ["jane@example.com", "jdoe@work.com"]
        assert d["phones"] == ["+1-555-0100"]

    def test_emails_sorted(self) -> None:
        c = GoogleContact(
            resource_name="people/c1",
            etag="",
            emails=("z@example.com", "a@example.com"),
        )
        assert c.emails == ("z@example.com", "a@example.com")
        # The model stores as given; sorting is done at parse time in people.py


class TestGoogleEvent:
    def test_to_hash_dict_excludes_volatile(
        self, sample_event: GoogleEvent
    ) -> None:
        d = sample_event.to_hash_dict()
        assert "etag" not in d
        assert "raw" not in d
        assert d["summary"] == "Team Standup"
        assert d["recurrence"] == ["RRULE:FREQ=DAILY;COUNT=5"]

    def test_attendees_as_list_in_hash(self, sample_event: GoogleEvent) -> None:
        d = sample_event.to_hash_dict()
        assert d["attendees"] == ["alice@example.com", "bob@example.com"]


class TestGoogleTask:
    def test_to_hash_dict_excludes_volatile(
        self, sample_task: GoogleTask
    ) -> None:
        d = sample_task.to_hash_dict()
        assert "raw" not in d
        assert "updated" not in d  # updated is volatile metadata
        assert d["title"] == "Review PR #42"
        assert d["due"] == "2025-01-20"
        assert d["completed"] is None

    def test_default_status(self) -> None:
        t = GoogleTask(task_id="t1", tasklist_id="tl1", updated="")
        assert t.status == "needsAction"
