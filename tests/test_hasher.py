"""Tests for SHA-256 content hashing."""

from __future__ import annotations

from gbridge.core.hasher import content_hash
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask


class TestContentHash:
    def test_deterministic(self, sample_contact: GoogleContact) -> None:
        """Same input always produces the same hash."""
        h1 = content_hash(sample_contact)
        h2 = content_hash(sample_contact)
        assert h1 == h2

    def test_different_data_different_hash(self) -> None:
        c1 = GoogleContact(resource_name="people/c1", etag="", display_name="Alice")
        c2 = GoogleContact(resource_name="people/c1", etag="", display_name="Bob")
        assert content_hash(c1) != content_hash(c2)

    def test_etag_change_does_not_change_hash(self) -> None:
        """etag is volatile metadata — excluded from hash."""
        c1 = GoogleContact(resource_name="people/c1", etag="v1", display_name="Alice")
        c2 = GoogleContact(resource_name="people/c1", etag="v2", display_name="Alice")
        assert content_hash(c1) == content_hash(c2)

    def test_raw_change_does_not_change_hash(self) -> None:
        """raw API response is excluded from hash."""
        c1 = GoogleContact(
            resource_name="people/c1", etag="", raw={"extra": "data1"}
        )
        c2 = GoogleContact(
            resource_name="people/c1", etag="", raw={"extra": "data2"}
        )
        assert content_hash(c1) == content_hash(c2)

    def test_hash_is_64_char_hex(self, sample_contact: GoogleContact) -> None:
        h = content_hash(sample_contact)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_event_hash_deterministic(self, sample_event: GoogleEvent) -> None:
        assert content_hash(sample_event) == content_hash(sample_event)

    def test_task_hash_deterministic(self, sample_task: GoogleTask) -> None:
        assert content_hash(sample_task) == content_hash(sample_task)

    def test_task_updated_field_excluded(self) -> None:
        """The 'updated' timestamp is volatile — should not affect hash."""
        t1 = GoogleTask(
            task_id="t1", tasklist_id="tl1", title="Do thing", updated="2025-01-01T00:00:00Z"
        )
        t2 = GoogleTask(
            task_id="t1", tasklist_id="tl1", title="Do thing", updated="2025-06-01T00:00:00Z"
        )
        assert content_hash(t1) == content_hash(t2)
