"""Project ledger items into Radicale's filesystem collection tree.

Given a set of Google models this module writes:

    <collections_root>/
        gbridge/
            contacts/
                .Radicale.props        (marks it as an addressbook)
                <resource_name>.vcf
            calendar/
                .Radicale.props        (marks it as a VEVENT calendar)
                <event_id>.ics
            tasks/
                .Radicale.props        (marks it as a VTODO calendar)
                <task_id>.ics

Each push cycle rewrites the tree in full — idempotent and stateless.
Deletion is implicit: items missing from the cycle's model list vanish
from disk and therefore vanish from the DAV feed Outlook consumes.

Conflict detection in DAV mode is delegated to the Outlook CalDav
Synchronizer addin running inside Outlook — GBridge overwrites the
authoritative DAV copy every cycle, and OCS picks a winner when local
Outlook state diverges.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - runtime use in method signatures
from typing import TYPE_CHECKING

import vobject

if TYPE_CHECKING:
    from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask

logger = logging.getLogger(__name__)


@dataclass
class ProjectionStats:
    contacts: int = 0
    events: int = 0
    tasks: int = 0

    @property
    def total(self) -> int:
        return self.contacts + self.events + self.tasks


class DavProjector:
    """Stateless ledger -> filesystem renderer for Radicale."""

    def __init__(self, collections_root: Path, *, user: str = "gbridge") -> None:
        self._root = collections_root / user
        self._contacts_dir = self._root / "contacts"
        self._calendar_dir = self._root / "calendar"
        self._tasks_dir = self._root / "tasks"

    # ---- public surface ----------------------------------------------------

    def project(
        self,
        *,
        contacts: list[GoogleContact] | None = None,
        events: list[GoogleEvent] | None = None,
        tasks: list[GoogleTask] | None = None,
    ) -> ProjectionStats:
        """Rebuild all DAV collections from the provided models."""
        self._ensure_collections()
        stats = ProjectionStats()

        stats.contacts = self._render_collection(
            directory=self._contacts_dir,
            suffix=".vcf",
            items=[(self._contact_id(c), self.render_contact(c)) for c in contacts or []],
        )
        stats.events = self._render_collection(
            directory=self._calendar_dir,
            suffix=".ics",
            items=[(e.event_id, self.render_event(e)) for e in events or []],
        )
        stats.tasks = self._render_collection(
            directory=self._tasks_dir,
            suffix=".ics",
            items=[(t.task_id, self.render_task(t)) for t in tasks or []],
        )

        logger.info(
            "DAV projection: %d contacts, %d events, %d tasks",
            stats.contacts,
            stats.events,
            stats.tasks,
        )
        return stats

    # ---- rendering (exposed for testing) ----------------------------------

    @staticmethod
    def render_contact(contact: GoogleContact) -> str:
        card = vobject.vCard()
        card.add("fn").value = contact.display_name or (
            f"{contact.given_name} {contact.family_name}".strip() or "Unnamed"
        )
        n = card.add("n")
        n.value = vobject.vcard.Name(
            family=contact.family_name,
            given=contact.given_name,
        )
        for email in contact.emails:
            item = card.add("email")
            item.value = email
            item.type_param = "INTERNET"
        for phone in contact.phones:
            item = card.add("tel")
            item.value = phone
            item.type_param = "VOICE"
        if contact.organization or contact.title:
            org = card.add("org")
            org.value = [contact.organization or ""]
            if contact.title:
                card.add("title").value = contact.title
        if contact.notes:
            card.add("note").value = contact.notes
        card.add("uid").value = contact.resource_name or "gbridge-unknown"
        return str(card.serialize())

    @staticmethod
    def render_event(event: GoogleEvent) -> str:
        # Hand-rolled iCalendar — avoids vobject's strict datetime coercion
        # (our inputs are already pre-normalised ISO strings from Google).
        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//GBridge//NONSGML Event//EN",
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(event.event_id or 'gbridge-event')}",
            f"SUMMARY:{_ics_escape(event.summary or '(no title)')}",
        ]
        if event.description:
            lines.append(f"DESCRIPTION:{_ics_escape(event.description)}")
        if event.location:
            lines.append(f"LOCATION:{_ics_escape(event.location)}")
        if event.start:
            lines.append(f"DTSTART:{_ics_datetime(event.start)}")
        if event.end:
            lines.append(f"DTEND:{_ics_datetime(event.end)}")
        for rrule in event.recurrence:
            if rrule.startswith("RRULE:"):
                lines.append(rrule)
            else:
                lines.append(f"RRULE:{rrule}")
        for attendee in event.attendees:
            lines.append(f"ATTENDEE:mailto:{attendee}")
        lines.append(
            "STATUS:" + ("CANCELLED" if event.status == "cancelled" else "CONFIRMED")
        )
        lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    @staticmethod
    def render_task(task: GoogleTask) -> str:
        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//GBridge//NONSGML Task//EN",
            "BEGIN:VTODO",
            f"UID:{_ics_escape(task.task_id or 'gbridge-task')}",
            f"SUMMARY:{_ics_escape(task.title or '(no title)')}",
        ]
        if task.notes:
            lines.append(f"DESCRIPTION:{_ics_escape(task.notes)}")
        if task.due:
            lines.append(f"DUE;VALUE=DATE:{_ics_datetime(task.due)}")
        lines.append(
            "STATUS:"
            + ("COMPLETED" if task.status == "completed" else "NEEDS-ACTION")
        )
        if task.completed:
            lines.append(f"COMPLETED:{_ics_datetime(task.completed)}")
        lines.append("END:VTODO")
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    # ---- internals ---------------------------------------------------------

    def _ensure_collections(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._write_props(
            self._contacts_dir,
            {"tag": "VADDRESSBOOK", "D:displayname": "GBridge Contacts"},
        )
        self._write_props(
            self._calendar_dir,
            {
                "tag": "VCALENDAR",
                "D:displayname": "GBridge Calendar",
                "C:supported-calendar-component-set": "VEVENT",
            },
        )
        self._write_props(
            self._tasks_dir,
            {
                "tag": "VCALENDAR",
                "D:displayname": "GBridge Tasks",
                "C:supported-calendar-component-set": "VTODO",
            },
        )

    @staticmethod
    def _write_props(directory: Path, props: dict[str, str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".Radicale.props").write_text(
            json.dumps(props, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _render_collection(
        *,
        directory: Path,
        suffix: str,
        items: list[tuple[str, str]],
    ) -> int:
        # Clear stale files (except .Radicale.props) so deletions propagate.
        for child in directory.iterdir():
            if child.name.startswith(".Radicale"):
                continue
            try:
                child.unlink()
            except OSError:
                logger.debug("Failed to remove stale %s", child)

        written = 0
        for item_id, body in items:
            path = directory / (_safe_filename(item_id) + suffix)
            path.write_text(body, encoding="utf-8")
            written += 1
        return written

    @staticmethod
    def _contact_id(c: GoogleContact) -> str:
        # Google contact resource names look like "people/c12345" — strip the slash.
        return c.resource_name.replace("/", "_")


# ---- helpers -------------------------------------------------------------


def _safe_filename(raw: str) -> str:
    """Collapse anything non-alphanumeric to an underscore."""
    return "".join(ch if ch.isalnum() else "_" for ch in raw) or "item"


def _ics_escape(value: str) -> str:
    """Escape characters that have special meaning in iCalendar TEXT values."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _ics_datetime(value: str) -> str:
    """Normalise ISO 8601 / date-only strings into iCalendar `YYYYMMDDTHHMMSSZ` or `YYYYMMDD`."""
    v = value.strip()
    if len(v) == 10 and v.count("-") == 2:
        # Date-only — YYYY-MM-DD -> YYYYMMDD
        return v.replace("-", "")
    # Remove punctuation (colons, dashes) and preserve optional trailing Z.
    trailing_z = v.endswith("Z")
    core = v.rstrip("Z")
    cleaned = core.replace("-", "").replace(":", "")
    return cleaned + ("Z" if trailing_z else "")
