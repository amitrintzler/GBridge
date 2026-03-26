"""Tests for the Google Calendar API wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gbridge.google.calendar import CalendarService


class TestCalendarService:
    def test_parse_event_timed(self, sample_event_response: dict) -> None:
        event = CalendarService._parse_event(sample_event_response, "primary")
        assert event.event_id == "evt_abc123"
        assert event.calendar_id == "primary"
        assert event.summary == "Team Standup"
        assert event.start == "2025-01-15T09:00:00-05:00"
        assert event.end == "2025-01-15T09:30:00-05:00"
        assert event.attendees == ("alice@example.com", "bob@example.com")
        assert event.recurrence == ("RRULE:FREQ=DAILY;COUNT=5",)

    def test_parse_event_allday(self) -> None:
        event = CalendarService._parse_event(
            {
                "id": "allday1",
                "etag": '"e"',
                "summary": "Holiday",
                "start": {"date": "2025-12-25"},
                "end": {"date": "2025-12-26"},
                "status": "confirmed",
            },
            "cal_holidays",
        )
        assert event.start == "2025-12-25"
        assert event.end == "2025-12-26"
        assert event.calendar_id == "cal_holidays"

    def test_parse_event_empty_fields(self) -> None:
        event = CalendarService._parse_event(
            {"id": "e1", "etag": '"e"', "start": {}, "end": {}},
            "primary",
        )
        assert event.start == ""
        assert event.end == ""
        assert event.attendees == ()
        assert event.recurrence == ()

    @patch("gbridge.google.calendar.build")
    def test_fetch_events_detects_cancelled(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.events().list().execute.return_value = {
            "items": [
                {
                    "id": "evt_ok", "etag": '"e"', "summary": "Good",
                    "start": {}, "end": {}, "status": "confirmed",
                },
                {"id": "evt_gone", "status": "cancelled"},
            ],
            "nextSyncToken": "st1",
        }

        svc = CalendarService(MagicMock())
        result = svc.fetch_events("primary", sync_token="old")

        assert len(result.items) == 1
        assert result.items[0].event_id == "evt_ok"
        assert result.deleted_event_ids == ["evt_gone"]
        assert result.sync_token == "st1"

    @patch("gbridge.google.calendar.build")
    def test_list_calendars(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.calendarList().list().execute.return_value = {
            "items": [
                {"id": "primary", "summary": "My Calendar", "accessRole": "owner"},
                {"id": "holidays", "summary": "Holidays", "accessRole": "reader"},
            ]
        }

        svc = CalendarService(MagicMock())
        cals = svc.list_calendars()
        assert len(cals) == 2
        assert cals[0]["id"] == "primary"
        assert cals[1]["summary"] == "Holidays"
