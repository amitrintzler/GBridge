"""Canonical data models for Microsoft Graph resources.

Mirrors `gbridge.google.models` in shape so both sides can be compared with
`content_hash()`. `to_hash_dict()` strips server-generated fields
(`@odata.etag`, `lastModifiedDateTime`, `changeKey`, `createdDateTime`) so
a refetch of an unchanged item produces the same hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MicrosoftContact:
    """A single contact from Microsoft Graph (/me/contacts)."""

    contact_id: str  # Graph's `id` field
    etag: str = ""  # @odata.etag (used for If-Match only, not hashed)
    display_name: str = ""
    given_name: str = ""
    family_name: str = ""
    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    organization: str = ""
    title: str = ""
    notes: str = ""  # stored in personalNotes
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        """Sync-relevant fields only — used for SHA-256 parity with Google side."""
        return {
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
class MicrosoftEvent:
    """A single event from Microsoft Graph (/me/events)."""

    event_id: str
    calendar_id: str
    etag: str = ""
    summary: str = ""  # Graph `subject`
    description: str = ""  # Graph `body.content` with contentType=text
    location: str = ""  # Graph `location.displayName`
    start: str = ""  # ISO 8601 datetime string
    end: str = ""
    recurrence: tuple[str, ...] = ()  # expressed as one or more RRULE strings
    attendees: tuple[str, ...] = ()  # sorted attendee email tuple
    status: str = "confirmed"  # derived from `showAs` / `isCancelled`
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        return {
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
class MicrosoftTask:
    """A single task from Microsoft To Do (/me/todo/lists/{id}/tasks).

    Note: Microsoft To Do exposes more status states than Google Tasks.
    We preserve the raw status but collapse anything non-completed to
    ``needsAction`` when mapping back to Google-compatible values.
    """

    task_id: str
    tasklist_id: str
    title: str = ""
    notes: str = ""
    # Graph values: notStarted|inProgress|completed|waitingOnOthers|deferred
    status: str = "notStarted"
    due: str | None = None  # ISO 8601 date (YYYY-MM-DD)
    completed: str | None = None  # ISO 8601 datetime
    etag: str = ""
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_hash_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "notes": self.notes,
            "status": self.status,
            "due": self.due,
            "completed": self.completed,
        }
