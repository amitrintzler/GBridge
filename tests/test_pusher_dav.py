"""Tests for Pusher DAV mode — full-tree projection + ledger bookkeeping."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gbridge.core.hasher import content_hash
from gbridge.core.ledger import SyncLedger
from gbridge.core.pusher import Pusher
from gbridge.dav.storage import DavProjector
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ledger(tmp_path: Path) -> SyncLedger:
    lg = SyncLedger(tmp_path / "pd.db")
    yield lg
    lg.close()


@pytest.fixture
def projector(tmp_path: Path) -> DavProjector:
    return DavProjector(tmp_path / "collections")


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.outlook_mode = "dav"
    return s


class TestDavMode:
    def test_projects_and_updates_ledger(
        self,
        ledger: SyncLedger,
        projector: DavProjector,
        settings: MagicMock,
        tmp_path: Path,
    ) -> None:
        c = GoogleContact(
            resource_name="people/c1", etag="", display_name="Alice"
        )
        e = GoogleEvent(
            event_id="E1",
            calendar_id="primary",
            etag="",
            summary="Standup",
            start="2026-05-01T09:00:00Z",
            end="2026-05-01T09:30:00Z",
        )
        t = GoogleTask(
            task_id="T1", tasklist_id="L1", title="Write docs"
        )
        ledger.upsert_item("contact", "people/c1", content_hash(c))
        ledger.upsert_item("event", "E1", content_hash(e), google_parent_id="primary")
        ledger.upsert_item("task", "T1", content_hash(t), google_parent_id="L1")

        p = Pusher(ledger, settings, mode="dav", projector=projector)
        stats = p.run_push(contacts=[c], events=[e], tasks=[t])

        assert stats["contacts"].created == 1
        assert stats["events"].created == 1
        assert stats["tasks"].created == 1

        # Ledger tracks DAV ids + hashes.
        row_c = ledger.get_item("contact", "people/c1")
        assert row_c is not None
        assert row_c.outlook_id.startswith("dav:")
        assert row_c.outlook_hash == content_hash(c)

        # Files on disk.
        contacts_dir = tmp_path / "collections" / "gbridge" / "contacts"
        assert any(contacts_dir.glob("*.vcf"))

    def test_unchanged_items_are_counted_unchanged(
        self,
        ledger: SyncLedger,
        projector: DavProjector,
        settings: MagicMock,
    ) -> None:
        c = GoogleContact(resource_name="people/c1", etag="", display_name="A")
        ledger.upsert_item("contact", "people/c1", content_hash(c))

        p = Pusher(ledger, settings, mode="dav", projector=projector)
        p.run_push(contacts=[c])
        stats2 = p.run_push(contacts=[c])

        assert stats2["contacts"].unchanged == 1
        assert stats2["contacts"].created == 0
        assert stats2["contacts"].updated == 0

    def test_content_change_counts_as_update(
        self,
        ledger: SyncLedger,
        projector: DavProjector,
        settings: MagicMock,
    ) -> None:
        c1 = GoogleContact(resource_name="people/c1", etag="", display_name="A")
        c2 = GoogleContact(resource_name="people/c1", etag="", display_name="A v2")
        ledger.upsert_item("contact", "people/c1", content_hash(c1))

        p = Pusher(ledger, settings, mode="dav", projector=projector)
        p.run_push(contacts=[c1])
        # Second cycle: Google content changed; ledger content_hash updated too.
        ledger.upsert_item("contact", "people/c1", content_hash(c2))
        stats = p.run_push(contacts=[c2])
        assert stats["contacts"].updated == 1

    def test_missing_projector_fails_loudly(
        self, ledger: SyncLedger, settings: MagicMock
    ) -> None:
        p = Pusher(ledger, settings, mode="dav")  # no projector
        stats = p.run_push()
        for s in stats.values():
            assert s.failed >= 1
