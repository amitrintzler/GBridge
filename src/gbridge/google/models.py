"""Canonical data models for Google API resources.

All models are frozen dataclasses — immutable after creation.
The ``to_hash_dict`` method returns only sync-relevant fields
(excludes etag, raw response, and other volatile metadata) so the
SHA-256 content hash stays stable across API refetches that didn't
change actual data.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoogleContact:
    """A single Google People API contact."""

    resource_name: str  # e.g. "people/c1234567890"
    etag: str
    display_name: str = ""
    given_name: str = ""
    family_name: str = ""
    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    organization: str = ""
    title: str = ""
    notes: str = ""
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        """Return only sync-relevant fields for deterministic hashing."""
        return {
            "resource_name": self.resource_name,
            "display_name": self.display_name,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "emails": list(self.emails),
            "phones": list(self.phones),
            "organization": self.organization,
            "title": self.title,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GoogleEvent:
    """A single Google Calendar event."""

    event_id: str
    calendar_id: str
    etag: str
    summary: str = ""
    description: str = ""
    location: str = ""
    start: str = ""  # ISO 8601 datetime or date
    end: str = ""
    recurrence: tuple[str, ...] = ()
    attendees: tuple[str, ...] = ()  # sorted email list
    status: str = "confirmed"
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "calendar_id": self.calendar_id,
            "summary": self.summary,
            "description": self.description,
            "location": self.location,
            "start": self.start,
            "end": self.end,
            "recurrence": list(self.recurrence),
            "attendees": list(self.attendees),
            "status": self.status,
        }


@dataclass(frozen=True)
class GoogleTask:
    """A single Google Tasks item."""

    task_id: str
    tasklist_id: str
    title: str = ""
    notes: str = ""
    status: str = "needsAction"  # "needsAction" | "completed"
    due: str | None = None  # ISO 8601 date or None
    completed: str | None = None  # ISO 8601 datetime or None
    updated: str = ""
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "tasklist_id": self.tasklist_id,
            "title": self.title,
            "notes": self.notes,
            "status": self.status,
            "due": self.due,
            "completed": self.completed,
        }
