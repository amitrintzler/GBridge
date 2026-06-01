"""Tests that a resolved conflict actually takes effect on the next push.

This guards the bug where the pusher never consulted the `winner` column,
so a resolved conflict (a) did nothing and (b) was reset to NULL by the
next 412 re-detection — trapping the user in a loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import responses

from gbridge.config.defaults import MICROSOFT_GRAPH_BASE
from gbridge.core import conflicts as cmod
from gbridge.core.hasher import content_hash
from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.microsoft.graph_calendar import GraphCalendarService
from gbridge.microsoft.graph_people import GraphPeopleService
from gbridge.microsoft.graph_tasks import GraphTasksService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def fake_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = {"access_token": "AT"}
    return auth


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "cr.db")
    yield lg
    lg.close()


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.outlook_mode = "graph"
    return s


def _pusher(ledger: SyncLedger, settings: MagicMock, auth: MagicMock) -> Pusher:
    return Pusher(
        ledger,
        settings,
        mode="graph",
        people_svc=GraphPeopleService(auth),
        calendar_svc=GraphCalendarService(auth),
        tasks_svc=GraphTasksService(auth),
    )


def _seed_drifted_contact(ledger: SyncLedger, c: GoogleContact) -> None:
    """Ledger row already pushed, but Google content has since drifted."""
    ledger.upsert_item("contact", c.resource_name, content_hash(c))
    ledger.set_outlook_state(
        item_type="contact",
        google_id=c.resource_name,
        outlook_id="MSID1",
        outlook_hash="STALE_HASH",  # != content_hash(c) -> classify == update
        outlook_etag='W/"1"',
    )


class TestUnresolvedConflictIsNotReset:
    @responses.activate
    def test_pending_conflict_is_skipped_and_winner_preserved(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        # A conflict already exists and is still unresolved.
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="<changed-in-outlook>",
        )
        # No HTTP endpoints registered: if the pusher re-attempts a PATCH the
        # test will error out, proving the re-attempt happened.
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(contacts=[c])

        assert stats["contacts"].conflicts == 1
        assert stats["contacts"].updated == 0
        # Winner is still NULL (not reset/destroyed) and the row still exists.
        row = cmod.get_conflict(ledger, cid)
        assert row is not None
        assert row.winner is None
        assert len(responses.calls) == 0  # no re-attempt


class TestGoogleWins:
    @responses.activate
    def test_force_overwrites_without_if_match_and_clears(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="<changed-in-outlook>",
        )
        cmod.resolve_conflict(ledger, cid, "google")

        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"id": "MSID1", "@odata.etag": 'W/"9"', "displayName": "Alice v2"},
            status=200,
        )

        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(contacts=[c])

        assert stats["contacts"].updated == 1
        # Force overwrite => NO If-Match header sent.
        assert "If-Match" not in responses.calls[0].request.headers
        # Conflict row cleared.
        assert cmod.get_conflict(ledger, cid) is None
        # Ledger baseline advanced => next push is a noop.
        row = ledger.get_item("contact", "people/c1")
        assert row is not None
        assert row.outlook_hash == content_hash(c)
        assert row.outlook_etag == 'W/"9"'

    @responses.activate
    def test_next_push_is_noop_after_google_win(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"id": "MSID1", "@odata.etag": 'W/"9"', "displayName": "Alice v2"},
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        p.run_push(contacts=[c])

        # Second cycle: nothing to do.
        stats2 = p.run_push(contacts=[c])
        assert stats2["contacts"].unchanged == 1
        assert stats2["contacts"].updated == 0


class TestOutlookWins:
    @responses.activate
    def test_keeps_outlook_fetches_fresh_etag_no_patch(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "outlook")

        # Only a GET should happen (to capture the fresh etag) — no PATCH.
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"id": "MSID1", "@odata.etag": 'W/"99"', "displayName": "Edited in Outlook"},
            status=200,
        )

        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(contacts=[c])

        assert stats["contacts"].unchanged == 1
        assert stats["contacts"].updated == 0
        # Exactly one GET, zero PATCH.
        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == "GET"
        # Conflict cleared; baseline advanced with the fresh Outlook etag.
        assert cmod.get_conflict(ledger, cid) is None
        row = ledger.get_item("contact", "people/c1")
        assert row is not None
        assert row.outlook_hash == content_hash(c)
        assert row.outlook_etag == 'W/"99"'

    @responses.activate
    def test_next_push_is_noop_after_outlook_win(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "outlook")
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"id": "MSID1", "@odata.etag": 'W/"99"', "displayName": "Edited"},
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        p.run_push(contacts=[c])

        stats2 = p.run_push(contacts=[c])
        assert stats2["contacts"].unchanged == 1


class TestEventResolution:
    def _seed(self, ledger: SyncLedger, e: GoogleEvent) -> None:
        ledger.upsert_item("event", e.event_id, content_hash(e), google_parent_id=e.calendar_id)
        ledger.set_outlook_state(
            item_type="event", google_id=e.event_id, google_parent_id=e.calendar_id,
            outlook_id="MSE1", outlook_hash="STALE", outlook_etag='W/"1"',
        )

    def _event(self) -> GoogleEvent:
        return GoogleEvent(
            event_id="E1", calendar_id="CAL1", etag="", summary="Standup v2",
            start="2026-05-01T09:00:00Z", end="2026-05-01T09:30:00Z",
        )

    @responses.activate
    def test_google_wins_force_patch(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        e = self._event()
        self._seed(ledger, e)
        cid = cmod.record_conflict(
            ledger, item_type="event", google_id="E1", google_parent_id="CAL1",
            google_hash=content_hash(e), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/events/MSE1",
            json={
                "id": "MSE1", "@odata.etag": 'W/"9"', "subject": "Standup v2",
                "body": {"contentType": "text", "content": ""},
                "start": {"dateTime": "2026-05-01T09:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2026-05-01T09:30:00", "timeZone": "UTC"},
            },
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(events=[e])
        assert stats["events"].updated == 1
        assert "If-Match" not in responses.calls[0].request.headers
        assert cmod.get_conflict(ledger, cid) is None

    @responses.activate
    def test_outlook_wins_fetches_event_etag(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        e = self._event()
        self._seed(ledger, e)
        cid = cmod.record_conflict(
            ledger, item_type="event", google_id="E1", google_parent_id="CAL1",
            google_hash=content_hash(e), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "outlook")
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/events/MSE1",
            json={
                "id": "MSE1", "@odata.etag": 'W/"77"', "subject": "Edited",
                "body": {"contentType": "text", "content": ""},
                "start": {"dateTime": "2026-05-01T09:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2026-05-01T09:30:00", "timeZone": "UTC"},
            },
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(events=[e])
        assert stats["events"].unchanged == 1
        row = ledger.get_item("event", "E1", "CAL1")
        assert row is not None
        assert row.outlook_etag == 'W/"77"'


class TestTaskResolution:
    def _seed(self, ledger: SyncLedger, t: GoogleTask) -> None:
        ledger.upsert_item("task", t.task_id, content_hash(t), google_parent_id=t.tasklist_id)
        ledger.set_outlook_state(
            item_type="task", google_id=t.task_id, google_parent_id=t.tasklist_id,
            outlook_id="MST1", outlook_hash="STALE", outlook_etag='W/"1"',
        )

    def _task(self) -> GoogleTask:
        return GoogleTask(task_id="T1", tasklist_id="L1", title="Do v2")

    @responses.activate
    def test_google_wins_force_patch(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        t = self._task()
        self._seed(ledger, t)
        cid = cmod.record_conflict(
            ledger, item_type="task", google_id="T1", google_parent_id="L1",
            google_hash=content_hash(t), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks/MST1",
            json={
                "id": "MST1", "@odata.etag": 'W/"9"', "title": "Do v2",
                "body": {"contentType": "text", "content": ""}, "status": "notStarted",
            },
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(tasks=[t])
        assert stats["tasks"].updated == 1
        assert "If-Match" not in responses.calls[0].request.headers

    @responses.activate
    def test_outlook_wins_fetches_task_etag(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        t = self._task()
        self._seed(ledger, t)
        cid = cmod.record_conflict(
            ledger, item_type="task", google_id="T1", google_parent_id="L1",
            google_hash=content_hash(t), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "outlook")
        responses.add(
            responses.GET,
            f"{MICROSOFT_GRAPH_BASE}/me/todo/lists/L1/tasks/MST1",
            json={
                "id": "MST1", "@odata.etag": 'W/"88"', "title": "Edited",
                "body": {"contentType": "text", "content": ""}, "status": "notStarted",
            },
            status=200,
        )
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(tasks=[t])
        assert stats["tasks"].unchanged == 1
        row = ledger.get_item("task", "T1", "L1")
        assert row is not None
        assert row.outlook_etag == 'W/"88"'


class TestResolutionEdgeCases:
    @responses.activate
    def test_resolved_but_no_source_model_defers(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        p = _pusher(ledger, settings, fake_auth)
        # No source model supplied this cycle -> cannot act -> deferred.
        stats = p.run_push(contacts=[])
        assert stats["contacts"].failed == 1
        # Conflict stays resolved for the next cycle (not cleared, not reset).
        row = cmod.get_conflict(ledger, cid)
        assert row is not None
        assert row.winner == "google"
        assert len(responses.calls) == 0

    @responses.activate
    def test_graph_error_during_resolution_counts_failed(
        self, ledger: SyncLedger, settings: MagicMock, fake_auth: MagicMock
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="Alice v2")
        _seed_drifted_contact(ledger, c)
        cid = cmod.record_conflict(
            ledger, item_type="contact", google_id="people/c1",
            google_hash=content_hash(c), outlook_hash="x",
        )
        cmod.resolve_conflict(ledger, cid, "google")
        responses.add(
            responses.PATCH,
            f"{MICROSOFT_GRAPH_BASE}/me/contacts/MSID1",
            json={"error": {"code": "serverError"}},
            status=500,
        )
        p = _pusher(ledger, settings, fake_auth)
        stats = p.run_push(contacts=[c])
        assert stats["contacts"].failed == 1
        # Unresolved-on-error: winner stays so the user's choice survives a retry.
        row = cmod.get_conflict(ledger, cid)
        assert row is not None
        assert row.winner == "google"
