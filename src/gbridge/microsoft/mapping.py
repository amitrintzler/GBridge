"""Pure functions mapping Google <-> Microsoft Graph resource shapes.

No I/O here — these functions build / consume dicts that callers then
POST to Graph or compare against stored hashes. Keeping this module free
of network calls makes it easy to unit test exhaustively.

Limitations (documented in CHANGELOG):
- Subtasks / parent nesting: Google Tasks supports parent; Graph To Do does
  not. Subtask hierarchy is NOT synced in v1 — children appear as siblings.
- Status collapse: Graph To Do's `inProgress | waitingOnOthers | deferred`
  all map to Google's `needsAction`.
- Note format: Graph `body.contentType` is always forced to `"text"` so
  hashes are stable across Outlook's HTML auto-wrapping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.microsoft.models import MicrosoftContact, MicrosoftEvent, MicrosoftTask

# ---- Contacts ------------------------------------------------------------


def google_contact_to_ms_payload(contact: GoogleContact) -> dict[str, Any]:
    """Convert a Google contact into a Graph `contact` POST body."""
    payload: dict[str, Any] = {
        "displayName": contact.display_name,
        "givenName": contact.given_name,
        "surname": contact.family_name,
    }
    if contact.emails:
        payload["emailAddresses"] = [
            {"address": e, "name": contact.display_name or e} for e in contact.emails
        ]
    if contact.phones:
        # First phone -> mobile; rest -> business. Preserves ordering reasonably.
        payload["mobilePhone"] = contact.phones[0]
        if len(contact.phones) > 1:
            payload["businessPhones"] = list(contact.phones[1:])
    if contact.organization:
        payload["companyName"] = contact.organization
    if contact.title:
        payload["jobTitle"] = contact.title
    if contact.notes:
        payload["personalNotes"] = contact.notes
    return payload


def ms_payload_to_ms_contact(payload: dict[str, Any]) -> MicrosoftContact:
    """Parse a Graph contact response into a MicrosoftContact."""
    emails = tuple(
        e["address"] for e in payload.get("emailAddresses", []) if e.get("address")
    )
    phones: list[str] = []
    mobile = payload.get("mobilePhone")
    if mobile:
        phones.append(mobile)
    for p in payload.get("businessPhones", []):
        if p:
            phones.append(p)
    return MicrosoftContact(
        contact_id=str(payload.get("id", "")),
        etag=str(payload.get("@odata.etag", "")),
        display_name=str(payload.get("displayName", "")),
        given_name=str(payload.get("givenName", "")),
        family_name=str(payload.get("surname", "")),
        emails=emails,
        phones=tuple(phones),
        organization=str(payload.get("companyName", "")),
        title=str(payload.get("jobTitle", "")),
        notes=str(payload.get("personalNotes", "")),
        raw=payload,
    )


# ---- Events --------------------------------------------------------------


def _start_end_to_graph(value: str, tz: str) -> dict[str, str]:
    """Graph events need `{dateTime, timeZone}` for both date and datetime."""
    # For date-only values Graph accepts `YYYY-MM-DDT00:00:00`.
    if len(value) == 10 and value.count("-") == 2:
        return {"dateTime": f"{value}T00:00:00", "timeZone": tz}
    # Strip trailing Z if present — Graph wants naive + timeZone field.
    normalized = value[:-1] if value.endswith("Z") else value
    return {"dateTime": normalized, "timeZone": tz}


def google_event_to_ms_payload(
    event: GoogleEvent, *, default_timezone: str = "UTC"
) -> dict[str, Any]:
    """Build a Graph `event` POST body from a GoogleEvent."""
    payload: dict[str, Any] = {
        "subject": event.summary,
        "body": {"contentType": "text", "content": event.description},
        "start": _start_end_to_graph(event.start, default_timezone),
        "end": _start_end_to_graph(event.end, default_timezone),
    }
    if event.location:
        payload["location"] = {"displayName": event.location}
    if event.attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": a, "name": a}, "type": "required"}
            for a in event.attendees
        ]
    if event.status == "cancelled":
        payload["isCancelled"] = True

    recurrence = rrule_to_graph_recurrence(
        event.recurrence, start=event.start, default_timezone=default_timezone
    )
    if recurrence is not None:
        payload["recurrence"] = recurrence
    return payload


# ---- Recurrence mapping --------------------------------------------------

_RRULE_FREQ_TO_GRAPH = {
    "DAILY": "daily",
    "WEEKLY": "weekly",
    "MONTHLY": "absoluteMonthly",
    "YEARLY": "absoluteYearly",
}
_RRULE_BYDAY_TO_GRAPH = {
    "MO": "monday", "TU": "tuesday", "WE": "wednesday", "TH": "thursday",
    "FR": "friday", "SA": "saturday", "SU": "sunday",
}


def rrule_to_graph_recurrence(
    rules: tuple[str, ...],
    *,
    start: str,
    default_timezone: str = "UTC",
) -> dict[str, Any] | None:
    """Convert a Google RRULE: line to a Graph ``recurrence`` object.

    Supports the common subset:
      - FREQ=DAILY|WEEKLY|MONTHLY|YEARLY
      - INTERVAL=<n>
      - COUNT=<n>  (mapped to endType=numbered)
      - UNTIL=<date/datetime>  (mapped to endType=endDate)
      - BYDAY=MO,TU,...
      - BYMONTHDAY=<n>

    Returns None if no recognised RRULE is present. Unrecognised clauses are
    ignored so round-trip stays best-effort — complex cases may drift.
    """
    rrule = next(
        (r[len("RRULE:"):] for r in rules if r.startswith("RRULE:")),
        None,
    )
    if not rrule:
        return None

    parts: dict[str, str] = {}
    for chunk in rrule.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip().upper()] = v.strip()

    freq = parts.get("FREQ", "").upper()
    if freq not in _RRULE_FREQ_TO_GRAPH:
        return None
    interval = int(parts.get("INTERVAL", "1") or "1")
    pattern: dict[str, Any] = {
        "type": _RRULE_FREQ_TO_GRAPH[freq],
        "interval": interval,
    }
    if freq == "WEEKLY":
        byday = parts.get("BYDAY", "")
        days = [
            _RRULE_BYDAY_TO_GRAPH[d]
            for d in byday.split(",")
            if d in _RRULE_BYDAY_TO_GRAPH
        ]
        if days:
            pattern["daysOfWeek"] = days
    if freq == "MONTHLY":
        pattern["dayOfMonth"] = int(parts.get("BYMONTHDAY", "1"))
    if freq == "YEARLY":
        pattern["dayOfMonth"] = int(parts.get("BYMONTHDAY", "1"))
        pattern["month"] = int(parts.get("BYMONTH", "1"))

    start_date = start[:10] if len(start) >= 10 else start
    range_block: dict[str, Any] = {
        "type": "noEnd",
        "startDate": start_date,
        "recurrenceTimeZone": default_timezone,
    }
    if "COUNT" in parts:
        range_block["type"] = "numbered"
        range_block["numberOfOccurrences"] = int(parts["COUNT"])
    elif "UNTIL" in parts:
        range_block["type"] = "endDate"
        until = parts["UNTIL"]
        # Date-only UNTIL is already YYYYMMDD; datetime has T…Z suffix.
        if len(until) >= 8:
            y, m, d = until[:4], until[4:6], until[6:8]
            range_block["endDate"] = f"{y}-{m}-{d}"

    return {"pattern": pattern, "range": range_block}


def ms_payload_to_ms_event(payload: dict[str, Any], calendar_id: str) -> MicrosoftEvent:
    """Parse a Graph event response into a MicrosoftEvent."""
    body = payload.get("body", {})
    location = payload.get("location") or {}
    attendee_emails = tuple(
        sorted(
            a.get("emailAddress", {}).get("address", "")
            for a in payload.get("attendees", [])
            if a.get("emailAddress", {}).get("address")
        )
    )
    status = "cancelled" if payload.get("isCancelled") else "confirmed"
    start = payload.get("start", {}).get("dateTime", "")
    end = payload.get("end", {}).get("dateTime", "")
    return MicrosoftEvent(
        event_id=str(payload.get("id", "")),
        calendar_id=calendar_id,
        etag=str(payload.get("@odata.etag", "")),
        summary=str(payload.get("subject", "")),
        description=str(body.get("content", "")),
        location=str(location.get("displayName", "")),
        start=start,
        end=end,
        recurrence=(),
        attendees=attendee_emails,
        status=status,
        raw=payload,
    )


# ---- Tasks ---------------------------------------------------------------


_STATUS_GOOGLE_TO_GRAPH = {
    "needsAction": "notStarted",
    "completed": "completed",
}
_STATUS_GRAPH_TO_GOOGLE = {
    "notStarted": "needsAction",
    "inProgress": "needsAction",
    "completed": "completed",
    "waitingOnOthers": "needsAction",
    "deferred": "needsAction",
}


def google_task_to_ms_payload(
    task: GoogleTask, *, default_timezone: str = "UTC"
) -> dict[str, Any]:
    """Build a Graph To Do `task` POST body from a GoogleTask."""
    payload: dict[str, Any] = {
        "title": task.title,
        "status": _STATUS_GOOGLE_TO_GRAPH.get(task.status, "notStarted"),
        "body": {"contentType": "text", "content": task.notes or ""},
    }
    if task.due:
        payload["dueDateTime"] = {
            "dateTime": f"{task.due}T00:00:00",
            "timeZone": default_timezone,
        }
    if task.completed:
        # Graph completedDateTime requires dateTime + timeZone — normalise.
        stamp = task.completed.rstrip("Z")
        payload["completedDateTime"] = {"dateTime": stamp, "timeZone": "UTC"}
    return payload


def ms_payload_to_ms_task(payload: dict[str, Any], tasklist_id: str) -> MicrosoftTask:
    body = payload.get("body", {})
    due = payload.get("dueDateTime", {}).get("dateTime") if payload.get("dueDateTime") else None
    if due:
        # Normalise to date-only to match Google side.
        due = due[:10]
    completed = (
        payload.get("completedDateTime", {}).get("dateTime")
        if payload.get("completedDateTime")
        else None
    )
    return MicrosoftTask(
        task_id=str(payload.get("id", "")),
        tasklist_id=tasklist_id,
        title=str(payload.get("title", "")),
        notes=str(body.get("content", "")),
        status=str(payload.get("status", "notStarted")),
        due=due,
        completed=completed,
        etag=str(payload.get("@odata.etag", "")),
        raw=payload,
    )


def ms_status_to_google(status: str) -> str:
    """Collapse Graph's richer task status to Google's 2-value enum."""
    return _STATUS_GRAPH_TO_GOOGLE.get(status, "needsAction")


# ---- Reverse-direction helpers (MS -> Google-compatible dataclasses) ----


def ms_contact_to_google_shape(contact: MicrosoftContact) -> GoogleContact:
    """Represent a Microsoft contact as a GoogleContact for hash parity.

    The `resource_name` and `etag` fields are populated with the Graph id
    and etag respectively — this is a compatibility shim for `content_hash`
    comparison only. Do NOT use the result as a real Google contact.
    """
    return GoogleContact(
        resource_name=contact.contact_id,
        etag=contact.etag,
        display_name=contact.display_name,
        given_name=contact.given_name,
        family_name=contact.family_name,
        emails=contact.emails,
        phones=contact.phones,
        organization=contact.organization,
        title=contact.title,
        notes=contact.notes,
    )


def ms_event_to_google_shape(event: MicrosoftEvent) -> GoogleEvent:
    return GoogleEvent(
        event_id=event.event_id,
        calendar_id=event.calendar_id,
        etag=event.etag,
        summary=event.summary,
        description=event.description,
        location=event.location,
        start=event.start,
        end=event.end,
        recurrence=event.recurrence,
        attendees=event.attendees,
        status=event.status,
    )


def ms_task_to_google_shape(task: MicrosoftTask) -> GoogleTask:
    return GoogleTask(
        task_id=task.task_id,
        tasklist_id=task.tasklist_id,
        title=task.title,
        notes=task.notes,
        status=ms_status_to_google(task.status),
        due=task.due,
        completed=task.completed,
        updated=datetime.now(UTC).isoformat(),
    )
