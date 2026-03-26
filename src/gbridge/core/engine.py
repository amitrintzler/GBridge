"""Sync engine — orchestrates Google fetch, diff, and ledger updates.

Phase 1 scope: read from Google, compute diffs, update the local ledger.
Phase 2 will add the Outlook write-back path.

Safety guarantees:
- Read-only Google API scopes — cannot modify user's Google data
- All state is local (SQLite ledger) — no external side effects
- Items are only marked as changed when the SHA-256 hash differs
- Deletions detected via API delta signals, not by guessing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gbridge.core.hasher import content_hash
from gbridge.google.calendar import CalendarService
from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
from gbridge.google.people import PeopleService
from gbridge.google.tasks import TasksService

if TYPE_CHECKING:
    from gbridge.config.settings import Settings
    from gbridge.core.ledger import SyncLedger
    from gbridge.google.auth import GoogleAuthManager

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Counters for a single sync run."""

    new: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0


class SyncEngine:
    """Orchestrates the sync pipeline: fetch → diff → ledger."""

    def __init__(
        self,
        ledger: SyncLedger,
        auth: GoogleAuthManager,
        settings: Settings,
    ) -> None:
        self._ledger = ledger
        self._auth = auth
        self._settings = settings

    def run_sync(self) -> dict[str, SyncStats]:
        """Run a full sync cycle for all resource types.

        Returns a dict mapping resource type to its sync statistics.
        """
        creds = self._auth.get_credentials()
        results: dict[str, SyncStats] = {}

        results["contacts"] = self._sync_contacts(PeopleService(creds))
        results["events"] = self._sync_events(CalendarService(creds))
        results["tasks"] = self._sync_tasks(TasksService(creds))

        for rtype, stats in results.items():
            logger.info(
                "Sync %s: %d new, %d updated, %d unchanged, %d deleted",
                rtype,
                stats.new,
                stats.updated,
                stats.unchanged,
                stats.deleted,
            )

        return results

    def _sync_contacts(self, people_svc: PeopleService) -> SyncStats:
        sync_token = self._ledger.get_sync_state("people_sync_token")
        result = people_svc.fetch_all(sync_token=sync_token)

        stats = self._process_items("contact", result.items)

        # Handle deletions from delta sync
        for resource_name in result.deleted_resource_names:
            if self._ledger.remove_item("contact", resource_name):
                stats.deleted += 1

        if result.sync_token:
            self._ledger.set_sync_state("people_sync_token", result.sync_token)

        return stats

    def _sync_events(self, calendar_svc: CalendarService) -> SyncStats:
        total_stats = SyncStats()
        calendars = calendar_svc.list_calendars()

        for cal in calendars:
            cal_id = cal["id"]
            state_key = f"calendar_{cal_id}_sync_token"
            sync_token = self._ledger.get_sync_state(state_key)

            result = calendar_svc.fetch_events(cal_id, sync_token=sync_token)
            stats = self._process_items("event", result.items, google_parent_id=cal_id)

            for event_id in result.deleted_event_ids:
                if self._ledger.remove_item("event", event_id, cal_id):
                    stats.deleted += 1

            if result.sync_token:
                self._ledger.set_sync_state(state_key, result.sync_token)

            total_stats.new += stats.new
            total_stats.updated += stats.updated
            total_stats.unchanged += stats.unchanged
            total_stats.deleted += stats.deleted

        return total_stats

    def _sync_tasks(self, tasks_svc: TasksService) -> SyncStats:
        total_stats = SyncStats()
        tasklists = tasks_svc.list_tasklists()

        for tl in tasklists:
            tl_id = tl["id"]
            state_key = f"tasks_{tl_id}_updated_min"
            updated_min = self._ledger.get_sync_state(state_key)

            tasks = tasks_svc.fetch_tasks(tl_id, updated_min=updated_min)
            stats = self._process_items("task", tasks, google_parent_id=tl_id)

            # Track the latest 'updated' timestamp for next delta
            if tasks:
                latest = max(t.updated for t in tasks)
                self._ledger.set_sync_state(state_key, latest)

            total_stats.new += stats.new
            total_stats.updated += stats.updated
            total_stats.unchanged += stats.unchanged

        return total_stats

    def _process_items(
        self,
        item_type: str,
        items: list[GoogleContact] | list[GoogleEvent] | list[GoogleTask],
        google_parent_id: str = "",
    ) -> SyncStats:
        """Hash each item, compare with ledger, and record changes."""
        stats = SyncStats()

        for item in items:
            h = content_hash(item)
            google_id = self._get_google_id(item)
            etag = self._get_etag(item)

            existing = self._ledger.get_item(item_type, google_id, google_parent_id)
            changed = self._ledger.upsert_item(
                item_type=item_type,
                google_id=google_id,
                content_hash=h,
                etag=etag,
                google_parent_id=google_parent_id,
            )

            if existing is None:
                stats.new += 1
            elif changed:
                stats.updated += 1
            else:
                stats.unchanged += 1

        return stats

    @staticmethod
    def _get_google_id(item: GoogleContact | GoogleEvent | GoogleTask) -> str:
        if isinstance(item, GoogleContact):
            return item.resource_name
        if isinstance(item, GoogleEvent):
            return item.event_id
        return item.task_id

    @staticmethod
    def _get_etag(item: GoogleContact | GoogleEvent | GoogleTask) -> str:
        if isinstance(item, (GoogleContact, GoogleEvent)):
            return item.etag
        return ""
