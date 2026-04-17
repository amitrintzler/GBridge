"""Tests for Google RRULE -> Microsoft Graph recurrence object mapping."""

from __future__ import annotations

from gbridge.google.models import GoogleEvent
from gbridge.microsoft.mapping import (
    google_event_to_ms_payload,
    rrule_to_graph_recurrence,
)


class TestRRuleMapping:
    def test_daily_count(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=DAILY;COUNT=5",),
            start="2026-05-01T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "daily"
        assert r["pattern"]["interval"] == 1
        assert r["range"]["type"] == "numbered"
        assert r["range"]["numberOfOccurrences"] == 5
        assert r["range"]["startDate"] == "2026-05-01"

    def test_weekly_byday(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR",),
            start="2026-05-01T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "weekly"
        assert r["pattern"]["daysOfWeek"] == ["monday", "wednesday", "friday"]

    def test_monthly_bymonthday(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=MONTHLY;BYMONTHDAY=15;INTERVAL=2",),
            start="2026-05-15T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "absoluteMonthly"
        assert r["pattern"]["interval"] == 2
        assert r["pattern"]["dayOfMonth"] == 15

    def test_yearly(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25",),
            start="2026-12-25T00:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "absoluteYearly"
        assert r["pattern"]["month"] == 12
        assert r["pattern"]["dayOfMonth"] == 25

    def test_until(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=DAILY;UNTIL=20261231T000000Z",),
            start="2026-05-01T00:00:00Z",
        )
        assert r is not None
        assert r["range"]["type"] == "endDate"
        assert r["range"]["endDate"] == "2026-12-31"

    def test_no_rrule_returns_none(self) -> None:
        assert rrule_to_graph_recurrence((), start="2026-05-01") is None
        assert (
            rrule_to_graph_recurrence(("EXDATE:20260503",), start="2026-05-01") is None
        )

    def test_unknown_freq_returns_none(self) -> None:
        assert (
            rrule_to_graph_recurrence(
                ("RRULE:FREQ=HOURLY;INTERVAL=1",), start="2026-05-01"
            )
            is None
        )

    def test_no_end_default(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=WEEKLY;BYDAY=TU",),
            start="2026-05-05T09:00:00Z",
        )
        assert r is not None
        assert r["range"]["type"] == "noEnd"


class TestEventPayloadIncludesRecurrence:
    def test_payload_has_recurrence_for_rrule(self) -> None:
        e = GoogleEvent(
            event_id="E1",
            calendar_id="primary",
            etag="",
            summary="Weekly sync",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
            recurrence=("RRULE:FREQ=WEEKLY;BYDAY=FR",),
        )
        payload = google_event_to_ms_payload(e)
        assert "recurrence" in payload
        assert payload["recurrence"]["pattern"]["type"] == "weekly"

    def test_payload_omits_recurrence_for_non_recurring(self) -> None:
        e = GoogleEvent(
            event_id="E1",
            calendar_id="primary",
            etag="",
            summary="One-off",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        payload = google_event_to_ms_payload(e)
        assert "recurrence" not in payload
