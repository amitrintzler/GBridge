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


class TestRelativeMonthly:
    """MONTHLY + BYDAY must map to relativeMonthly, not silently become 'the 1st'."""

    def test_third_tuesday_via_byday_prefix(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=MONTHLY;BYDAY=3TU",),
            start="2026-05-19T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "relativeMonthly"
        assert r["pattern"]["daysOfWeek"] == ["tuesday"]
        assert r["pattern"]["index"] == "third"
        # Crucially, it must NOT have collapsed to dayOfMonth.
        assert "dayOfMonth" not in r["pattern"]

    def test_third_tuesday_via_bysetpos(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=MONTHLY;BYDAY=TU;BYSETPOS=3",),
            start="2026-05-19T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "relativeMonthly"
        assert r["pattern"]["index"] == "third"

    def test_last_friday(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=MONTHLY;BYDAY=-1FR",),
            start="2026-05-29T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "relativeMonthly"
        assert r["pattern"]["daysOfWeek"] == ["friday"]
        assert r["pattern"]["index"] == "last"

    def test_plain_monthly_still_absolute(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=MONTHLY;BYMONTHDAY=15",),
            start="2026-05-15T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "absoluteMonthly"
        assert r["pattern"]["dayOfMonth"] == 15


class TestRelativeYearly:
    def test_yearly_byday(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=4TH",),
            start="2026-11-26T09:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "relativeYearly"
        assert r["pattern"]["month"] == 11
        assert r["pattern"]["daysOfWeek"] == ["thursday"]
        assert r["pattern"]["index"] == "fourth"

    def test_yearly_absolute_still_works(self) -> None:
        r = rrule_to_graph_recurrence(
            ("RRULE:FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25",),
            start="2026-12-25T00:00:00Z",
        )
        assert r is not None
        assert r["pattern"]["type"] == "absoluteYearly"
        assert r["pattern"]["month"] == 12
        assert r["pattern"]["dayOfMonth"] == 25


class TestUnsupportedClausesWarn:
    def test_byyearday_logs_warning(self, caplog) -> None:
        with caplog.at_level("WARNING"):
            r = rrule_to_graph_recurrence(
                ("RRULE:FREQ=YEARLY;BYYEARDAY=100",),
                start="2026-04-10T09:00:00Z",
            )
        # Still produces a best-effort recurrence (absoluteYearly), but warns.
        assert r is not None
        assert any("BYYEARDAY" in m for m in caplog.messages)


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
