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
        # Populated by run_sync so a downstream Pusher can reuse the fetched
        # models without a second round-trip to Google.
        self.last_contacts: list[GoogleContact] = []
        self.last_events: list[GoogleEvent] = []
        self.last_tasks: list[GoogleTask] = []

    def run_sync(self) -> dict[str, SyncStats]:
        """Run a full sync cycle for all resource types.

        Returns a dict mapping resource type to its sync statistics.

        Partial-sync resume: before each resource type we write a
        checkpoint into sync_state so that if the process dies mid-cycle
        the next run can log which phase was incomplete. The checkpoint
        is cleared on successful completion.
        """
        creds = self._auth.get_credentials()
        results: dict[str, SyncStats] = {}

        self._note_interrupted_previous_run()

        for phase_label, phase_fn in (
            ("contacts", lambda: self._sync_contacts(PeopleService(creds))),
            ("events", lambda: self._sync_events(CalendarService(creds))),
            ("tasks", lambda: self._sync_tasks(TasksService(creds))),
        ):
            self._ledger.set_sync_state("sync_phase", phase_label)
            results[phase_label] = phase_fn()

        self._ledger.set_sync_state("sync_phase", "")

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

    def _note_interrupted_previous_run(self) -> None:
        prev = self._ledger.get_sync_state("sync_phase") or ""
        if prev:
            logger.warning(
                "Previous sync was interrupted during '%s' phase; "
                "resuming with a full cycle (delta tokens still valid)",
                prev,
            )

    def _sync_contacts(self, people_svc: PeopleService) -> SyncStats:
        sync_token = self._ledger.get_sync_state("people_sync_token")
        result = people_svc.fetch_all(sync_token=sync_token)

        self.last_contacts = list(result.items)
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
        enabled = set(self._settings.get("enabled_calendars") or [])  # type: ignore[arg-type]
        if enabled:
            calendars = [c for c in calendars if c["id"] in enabled]
            logger.info("Syncing %d of %d calendars (user-selected)",
                        len(calendars), len(enabled))
        collected_events: list[GoogleEvent] = []

        for cal in calendars:
            cal_id = cal["id"]
            state_key = f"calendar_{cal_id}_sync_token"
            sync_token = self._ledger.get_sync_state(state_key)

            result = calendar_svc.fetch_events(cal_id, sync_token=sync_token)
            collected_events.extend(result.items)
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

        self.last_events = collected_events
        return total_stats

    def _sync_tasks(self, tasks_svc: TasksService) -> SyncStats:
        total_stats = SyncStats()
        tasklists = tasks_svc.list_tasklists()
        enabled = set(self._settings.get("enabled_tasklists") or [])  # type: ignore[arg-type]
        if enabled:
            tasklists = [tl for tl in tasklists if tl["id"] in enabled]
            logger.info("Syncing %d of %d tasklists (user-selected)",
                        len(tasklists), len(enabled))
        collected_tasks: list[GoogleTask] = []

        for tl in tasklists:
            tl_id = tl["id"]
            state_key = f"tasks_{tl_id}_updated_min"
            updated_min = self._ledger.get_sync_state(state_key)

            tasks = tasks_svc.fetch_tasks(tl_id, updated_min=updated_min)
            collected_tasks.extend(tasks)
            stats = self._process_items("task", tasks, google_parent_id=tl_id)

            # Track the latest 'updated' timestamp for next delta
            if tasks:
                latest = max(t.updated for t in tasks)
                self._ledger.set_sync_state(state_key, latest)

            total_stats.new += stats.new
            total_stats.updated += stats.updated
            total_stats.unchanged += stats.unchanged

        self.last_tasks = collected_tasks
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
