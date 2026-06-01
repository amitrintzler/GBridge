"""Microsoft Graph calendar + events client — read + (later) write.

Delta sync is done per-calendar via /me/calendars/{id}/calendarView/delta.
Delta tokens expire (~30 days); DeltaExpiredError triggers a full re-sync,
mirroring Google Calendar's 410 GONE handling.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from gbridge.microsoft._http import DeltaExpiredError, GraphClient
from gbridge.microsoft.mapping import (
    google_event_to_ms_payload,
    ms_payload_to_ms_event,
)

if TYPE_CHECKING:
    from gbridge.google.models import GoogleEvent
    from gbridge.microsoft.auth import MicrosoftAuthManager
    from gbridge.microsoft.models import MicrosoftEvent

logger = logging.getLogger(__name__)


class EventSyncResult(NamedTuple):
    items: list[MicrosoftEvent]
    delta_link: str | None
    deleted_ids: list[str]


class GraphCalendarService:
    """Read + (later) write wrapper for /me/calendars and /me/events."""

    def __init__(
        self,
        auth: MicrosoftAuthManager,
        *,
        client: GraphClient | None = None,
    ) -> None:
        self._client = client or GraphClient(auth)

    def list_calendars(self) -> list[dict[str, str]]:
        """Return calendars visible to the user with id / name / owner."""
        calendars: list[dict[str, str]] = []
        items, _ = self._client.iter_pages("/me/calendars")
        for cal in items:
            calendars.append(
                {
                    "id": str(cal.get("id", "")),
                    "name": str(cal.get("name", "")),
                    "owner": str(cal.get("owner", {}).get("name", "")),
                }
            )
        return calendars

    def fetch_events(
        self, calendar_id: str, delta_link: str | None = None
    ) -> EventSyncResult:
        """Fetch events for a calendar.

        Uses /events/delta on the target calendar. On delta expiration,
        restarts with a fresh delta query.
        """
        try:
            return self._fetch(calendar_id, delta_link)
        except DeltaExpiredError:
            logger.warning(
                "Calendar %s delta link expired, performing full sync",
                calendar_id,
            )
            return self._fetch(calendar_id, None)

    def _fetch(self, calendar_id: str, delta_link: str | None) -> EventSyncResult:
        url = delta_link or f"/me/calendars/{calendar_id}/events/delta"
        items_raw, new_delta = self._client.iter_pages(url)

        events: list[MicrosoftEvent] = []
        deleted: list[str] = []
        for row in items_raw:
            if row.get("@removed"):
                eid = row.get("id", "")
                if eid:
                    deleted.append(eid)
                continue
            events.append(ms_payload_to_ms_event(row, calendar_id))

        logger.info(
            "Graph events [%s]: fetched %d, %d deletions (delta=%s)",
            calendar_id,
            len(events),
            len(deleted),
            delta_link is not None,
        )
        return EventSyncResult(
            items=events, delta_link=new_delta, deleted_ids=deleted
        )

    # ---- write surface -----------------------------------------------------

    def create(
        self, calendar_id: str, event: GoogleEvent, *, timezone: str = "UTC"
    ) -> MicrosoftEvent:
        payload = google_event_to_ms_payload(event, default_timezone=timezone)
        body = self._client.post(
            f"/me/calendars/{calendar_id}/events", json=payload
        )
        return ms_payload_to_ms_event(body, calendar_id)

    def update(
        self,
        outlook_id: str,
        calendar_id: str,
        event: GoogleEvent,
        *,
        if_match: str | None = None,
        timezone: str = "UTC",
    ) -> MicrosoftEvent:
        payload = google_event_to_ms_payload(event, default_timezone=timezone)
        body = self._client.patch(
            f"/me/events/{outlook_id}",
            json=payload,
            if_match=if_match,
        )
        return ms_payload_to_ms_event(body, calendar_id)

    def get_one(self, outlook_id: str, calendar_id: str) -> MicrosoftEvent:
        """Fetch a single Outlook event (used to capture its current etag)."""
        body = self._client.get(f"/me/events/{outlook_id}")
        return ms_payload_to_ms_event(body, calendar_id)

    def delete(self, outlook_id: str, *, if_match: str | None = None) -> None:
        self._client.delete(f"/me/events/{outlook_id}", if_match=if_match)
