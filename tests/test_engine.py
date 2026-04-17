"""Tests for the SyncEngine orchestration layer.

Covers run_sync across all three resource types, checkpointing, and
multi-calendar / multi-tasklist filtering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gbridge.core.engine import SyncEngine
from gbridge.core.ledger import SyncLedger
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.google.people import SyncResult

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "e.db")
    yield lg
    lg.close()


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.db_path = None
    s.get = MagicMock(return_value=[])  # no calendar/tasklist filtering
    return s


@pytest.fixture
def auth() -> MagicMock:
    a = MagicMock()
    a.get_credentials.return_value = object()
    return a


def _contact(rn: str = "people/c1", name: str = "Alice") -> GoogleContact:
    return GoogleContact(resource_name=rn, etag="e", display_name=name)


def _event(eid: str = "E1", cal: str = "primary") -> GoogleEvent:
    return GoogleEvent(
        event_id=eid,
        calendar_id=cal,
        etag="e",
        summary="Standup",
        start="2026-05-01T09:00:00Z",
        end="2026-05-01T09:30:00Z",
    )


def _task(tid: str = "T1", list_id: str = "L1") -> GoogleTask:
    return GoogleTask(
        task_id=tid, tasklist_id=list_id, title="Do", updated="2026-04-17T00:00:00Z"
    )


def _mk_services(
    contacts: list[GoogleContact],
    events_by_cal: dict[str, list[GoogleEvent]],
    tasks_by_list: dict[str, list[GoogleTask]],
):
    """Build MagicMock service classes returning the given payloads."""
    from gbridge.google.calendar import CalendarSyncResult

    people = MagicMock()
    people.return_value.fetch_all.return_value = SyncResult(
        items=contacts, sync_token="NEW", deleted_resource_names=[],
    )

    cal = MagicMock()
    cal.return_value.list_calendars.return_value = [
        {"id": k, "summary": k, "accessRole": "owner"} for k in events_by_cal
    ]
    def _fetch_events(cal_id: str, sync_token: str | None = None):  # noqa: ARG001
        return CalendarSyncResult(
            items=events_by_cal.get(cal_id, []),
            sync_token="TOK",
            deleted_event_ids=[],
        )
    cal.return_value.fetch_events.side_effect = _fetch_events

    tasks = MagicMock()
    tasks.return_value.list_tasklists.return_value = [
        {"id": k, "title": k, "updated": "2026"} for k in tasks_by_list
    ]
    def _fetch_tasks(list_id: str, updated_min: str | None = None):  # noqa: ARG001
        return tasks_by_list.get(list_id, [])
    tasks.return_value.fetch_tasks.side_effect = _fetch_tasks

    return people, cal, tasks


class TestRunSync:
    def test_orchestrates_all_three_resources(
        self, ledger: SyncLedger, settings: MagicMock, auth: MagicMock
    ) -> None:
        people, cal, tasks = _mk_services(
            contacts=[_contact("people/a"), _contact("people/b", "Bob")],
            events_by_cal={"primary": [_event("E1")]},
            tasks_by_list={"L1": [_task("T1")]},
        )
        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks):
            engine = SyncEngine(ledger, auth, settings)
            stats = engine.run_sync()

        assert stats["contacts"].new == 2
        assert stats["events"].new == 1
        assert stats["tasks"].new == 1
        assert len(engine.last_contacts) == 2
        assert len(engine.last_events) == 1
        assert len(engine.last_tasks) == 1

    def test_clears_sync_phase_on_success(
        self, ledger: SyncLedger, settings: MagicMock, auth: MagicMock
    ) -> None:
        people, cal, tasks = _mk_services(
            contacts=[], events_by_cal={}, tasks_by_list={},
        )
        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks):
            engine = SyncEngine(ledger, auth, settings)
            engine.run_sync()
        assert ledger.get_sync_state("sync_phase") == ""

    def test_interrupted_previous_run_is_logged(
        self,
        ledger: SyncLedger,
        settings: MagicMock,
        auth: MagicMock,
        caplog,
    ) -> None:
        ledger.set_sync_state("sync_phase", "events")
        people, cal, tasks = _mk_services(
            contacts=[], events_by_cal={}, tasks_by_list={},
        )
        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks), \
             caplog.at_level("WARNING"):
            engine = SyncEngine(ledger, auth, settings)
            engine.run_sync()
        assert any("interrupted" in msg for msg in caplog.messages)


class TestFiltering:
    def test_enabled_calendars_filters(
        self, ledger: SyncLedger, auth: MagicMock
    ) -> None:
        s = MagicMock()
        s.get = lambda key, default=None: (
            ["primary"] if key == "enabled_calendars" else default
        )
        people, cal, tasks = _mk_services(
            contacts=[],
            events_by_cal={
                "primary": [_event("E1", "primary")],
                "other": [_event("E2", "other")],
            },
            tasks_by_list={},
        )
        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks):
            engine = SyncEngine(ledger, auth, s)
            engine.run_sync()
        # Only "primary" calendar was fetched.
        assert cal.return_value.fetch_events.call_count == 1
        called_cal_ids = [
            c.args[0] for c in cal.return_value.fetch_events.call_args_list
        ]
        assert called_cal_ids == ["primary"]

    def test_enabled_tasklists_filters(
        self, ledger: SyncLedger, auth: MagicMock
    ) -> None:
        s = MagicMock()
        s.get = lambda key, default=None: (
            ["L1"] if key == "enabled_tasklists" else default
        )
        people, cal, tasks = _mk_services(
            contacts=[],
            events_by_cal={},
            tasks_by_list={
                "L1": [_task("T1", "L1")],
                "L2": [_task("T2", "L2")],
            },
        )
        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks):
            engine = SyncEngine(ledger, auth, s)
            engine.run_sync()
        assert tasks.return_value.fetch_tasks.call_count == 1


class TestDeletions:
    def test_contact_delete_propagates_to_ledger(
        self, ledger: SyncLedger, settings: MagicMock, auth: MagicMock
    ) -> None:
        # Seed a ledger row that we'll then delete via fetch_all
        ledger.upsert_item("contact", "people/gone", "H")
        from gbridge.google.people import SyncResult

        people = MagicMock()
        people.return_value.fetch_all.return_value = SyncResult(
            items=[], sync_token="X",
            deleted_resource_names=["people/gone"],
        )
        cal = MagicMock()
        cal.return_value.list_calendars.return_value = []
        tasks = MagicMock()
        tasks.return_value.list_tasklists.return_value = []

        with patch("gbridge.core.engine.PeopleService", people), \
             patch("gbridge.core.engine.CalendarService", cal), \
             patch("gbridge.core.engine.TasksService", tasks):
            engine = SyncEngine(ledger, auth, settings)
            stats = engine.run_sync()

        assert stats["contacts"].deleted == 1
        assert ledger.get_item("contact", "people/gone") is None
