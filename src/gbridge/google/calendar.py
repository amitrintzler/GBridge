"""Google Calendar API wrapper — read-only event sync.

Security: uses ``calendar.readonly`` scope — cannot create, modify,
or delete any events in the user's Google account.

Sync strategy:
- First run per calendar: full fetch with ``requestSyncToken``
- Subsequent runs: incremental sync using stored ``syncToken``
- 410 GONE → automatic full re-sync
- ``showDeleted=True`` to detect deletions in delta mode
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gbridge.config.defaults import CALENDAR_API_VERSION, DEFAULT_PAGE_SIZE
from gbridge.google.models import GoogleEvent
from gbridge.utils.backoff import retry_on_api_error

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)


class CalendarSyncResult(NamedTuple):
    """Result of a Calendar API sync operation."""

    items: list[GoogleEvent]
    sync_token: str | None
    deleted_event_ids: list[str]


class CalendarService:
    """Read-only wrapper around the Google Calendar API."""

    def __init__(self, credentials: Credentials) -> None:
        self._service = build(
            "calendar", CALENDAR_API_VERSION, credentials=credentials, cache_discovery=False
        )

    @retry_on_api_error()
    def list_calendars(self) -> list[dict[str, str]]:
        """Return a list of calendars the user has access to.

        Each dict contains 'id', 'summary', and 'accessRole'.
        """
        calendars: list[dict[str, str]] = []
        page_token: str | None = None

        while True:
            kwargs: dict[str, object] = {"maxResults": DEFAULT_PAGE_SIZE}
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.calendarList().list(**kwargs).execute()

            for cal in response.get("items", []):
                calendars.append({
                    "id": cal["id"],
                    "summary": cal.get("summary", cal["id"]),
                    "accessRole": cal.get("accessRole", "reader"),
                })

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return calendars

    def fetch_events(
        self, calendar_id: str, sync_token: str | None = None
    ) -> CalendarSyncResult:
        """Fetch events — full or incremental depending on sync_token."""
        try:
            return self._fetch(calendar_id, sync_token=sync_token)
        except HttpError as exc:
            if exc.resp.status == 410:
                logger.warning(
                    "Calendar sync token expired (410 GONE) for %s, full re-sync",
                    calendar_id,
                )
                return self._fetch(calendar_id, sync_token=None)
            raise

    @retry_on_api_error()
    def _fetch_page(
        self,
        calendar_id: str,
        sync_token: str | None,
        page_token: str | None,
    ) -> dict:
        kwargs: dict[str, object] = {
            "calendarId": calendar_id,
            "maxResults": DEFAULT_PAGE_SIZE,
            "singleEvents": False,  # keep recurring event masters
        }
        if sync_token:
            kwargs["syncToken"] = sync_token
        else:
            # Full sync — no syncToken means we shouldn't pass showDeleted
            kwargs["showDeleted"] = False
        if page_token:
            kwargs["pageToken"] = page_token

        # When doing incremental sync, show deleted events
        if sync_token:
            kwargs["showDeleted"] = True

        return self._service.events().list(**kwargs).execute()  # type: ignore[no-any-return]

    def _fetch(
        self, calendar_id: str, sync_token: str | None
    ) -> CalendarSyncResult:
        events: list[GoogleEvent] = []
        deleted: list[str] = []
        page_token: str | None = None
        new_sync_token: str | None = None

        while True:
            response = self._fetch_page(calendar_id, sync_token, page_token)

            for event in response.get("items", []):
                if event.get("status") == "cancelled":
                    eid = event.get("id", "")
                    if eid:
                        deleted.append(eid)
                    continue
                events.append(self._parse_event(event, calendar_id))

            new_sync_token = response.get("nextSyncToken")
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            "Calendar API [%s]: fetched %d events, %d deletions (delta=%s)",
            calendar_id,
            len(events),
            len(deleted),
            sync_token is not None,
        )
        return CalendarSyncResult(
            items=events,
            sync_token=new_sync_token,
            deleted_event_ids=deleted,
        )

    @staticmethod
    def _parse_event(event: dict, calendar_id: str) -> GoogleEvent:
        """Parse a Calendar API event resource into a GoogleEvent."""
        start_obj = event.get("start", {})
        end_obj = event.get("end", {})

        # Events may have dateTime (timed) or date (all-day)
        start = start_obj.get("dateTime") or start_obj.get("date", "")
        end = end_obj.get("dateTime") or end_obj.get("date", "")

        attendees = tuple(
            sorted(
                a.get("email", "")
                for a in event.get("attendees", [])
                if a.get("email")
            )
        )

        recurrence = tuple(event.get("recurrence", []))

        return GoogleEvent(
            event_id=event.get("id", ""),
            calendar_id=calendar_id,
            etag=event.get("etag", ""),
            summary=event.get("summary", ""),
            description=event.get("description", ""),
            location=event.get("location", ""),
            start=start,
            end=end,
            recurrence=recurrence,
            attendees=attendees,
            status=event.get("status", "confirmed"),
            raw=event,
        )
