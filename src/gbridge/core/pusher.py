"""Outlook push engine — ledger -> Outlook via Graph or DAV.

The pusher is the mirror of `engine.SyncEngine`: where the engine pulls from
Google into the ledger, the pusher drains the ledger into Outlook.

Modes:
    'dry'   — classify each ledger row, return stats; no network or disk I/O.
    'graph' — Microsoft 365 path: call GraphPeople / GraphCalendar /
              GraphTasks services to create/update items in Outlook.
    'dav'   — Task 10: render ledger items to a Radicale collection tree.

Conflict detection (graph mode):
    Before overwriting an Outlook item we pass the stored outlook_etag as
    `If-Match`. If Outlook returns 412 PreconditionFailed, someone edited
    the item in Outlook since our last push. We record a conflict row and
    skip the write. The user resolves via the tray / CLI; the next push
    either force-overwrites (winner=google) or updates our ledger baseline
    to match the current content (winner=outlook).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from gbridge.core import conflicts as conflicts_module
from gbridge.core.hasher import content_hash
from gbridge.microsoft._http import GraphError, PreconditionFailedError

if TYPE_CHECKING:
    from gbridge.config.settings import Settings
    from gbridge.core.ledger import SyncItem, SyncLedger
    from gbridge.dav.storage import DavProjector
    from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask
    from gbridge.microsoft.graph_calendar import GraphCalendarService
    from gbridge.microsoft.graph_people import GraphPeopleService
    from gbridge.microsoft.graph_tasks import GraphTasksService

logger = logging.getLogger(__name__)

PushMode = Literal["dry", "graph", "dav"]
Action = Literal["create", "update", "noop"]


@dataclass
class PushStats:
    """Counters from a single push cycle for one resource type."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return (
            self.created + self.updated + self.unchanged
            + self.conflicts + self.failed
        )


@dataclass
class PlannedAction:
    """What the pusher decided for a single ledger row."""

    action: Action
    item: SyncItem


class Pusher:
    """Orchestrates the ledger -> Outlook push."""

    def __init__(
        self,
        ledger: SyncLedger,
        settings: Settings,
        *,
        mode: PushMode = "dry",
        people_svc: GraphPeopleService | None = None,
        calendar_svc: GraphCalendarService | None = None,
        tasks_svc: GraphTasksService | None = None,
        projector: DavProjector | None = None,
    ) -> None:
        self._ledger = ledger
        self._settings = settings
        self._mode = mode
        self._people = people_svc
        self._calendar = calendar_svc
        self._tasks = tasks_svc
        self._projector = projector

    @property
    def mode(self) -> PushMode:
        return self._mode

    def run_push(
        self,
        *,
        contacts: list[GoogleContact] | None = None,
        events: list[GoogleEvent] | None = None,
        tasks: list[GoogleTask] | None = None,
    ) -> dict[str, PushStats]:
        """Push every ledger resource type. Returns per-type stats.

        In non-dry modes the corresponding model list is required so the
        pusher has something to send to Outlook.
        """
        if self._mode == "dav":
            results = self._run_dav(contacts or [], events or [], tasks or [])
            # DAV path: deletion is implicit (projector rewrote the whole tree).
            self._drain_dav_deletion_queue()
        else:
            # Handle Google-side deletions first so we don't push new state to
            # an item that's about to vanish on the Outlook side.
            deletion_failures = self._drain_graph_deletion_queue()
            results = {
                "contacts": self._run_contacts(contacts),
                "events": self._run_events(events),
                "tasks": self._run_tasks(tasks),
            }
            # Surface persistent deletion failures as 'failed' on the right bucket.
            for rtype, n in deletion_failures.items():
                if rtype in results:
                    results[rtype].failed += n
        for rtype, stats in results.items():
            logger.info(
                "Push %s (mode=%s): %d created, %d updated, %d unchanged, "
                "%d conflicts, %d failed",
                rtype,
                self._mode,
                stats.created,
                stats.updated,
                stats.unchanged,
                stats.conflicts,
                stats.failed,
            )
        return results

    # ---- planning (shared across modes) ------------------------------------

    def plan(self, item_type: str) -> list[PlannedAction]:
        """Classify every ledger row of `item_type` into an Action."""
        return [
            PlannedAction(self._classify(row), row)
            for row in self._ledger.list_items(item_type)
        ]

    @staticmethod
    def _classify(item: SyncItem) -> Action:
        if not item.outlook_id:
            return "create"
        if item.content_hash == item.outlook_hash:
            return "noop"
        return "update"

    # ---- per-resource orchestration ---------------------------------------

    def _run_contacts(
        self, items: list[GoogleContact] | None
    ) -> PushStats:
        return self._run(
            item_type="contact",
            items=items,
            get_id=lambda c: c.resource_name,
            get_parent=lambda _c: "",
            apply=self._apply_contact,
        )

    def _run_events(self, items: list[GoogleEvent] | None) -> PushStats:
        return self._run(
            item_type="event",
            items=items,
            get_id=lambda e: e.event_id,
            get_parent=lambda e: e.calendar_id,
            apply=self._apply_event,
        )

    def _run_tasks(self, items: list[GoogleTask] | None) -> PushStats:
        return self._run(
            item_type="task",
            items=items,
            get_id=lambda t: t.task_id,
            get_parent=lambda t: t.tasklist_id,
            apply=self._apply_task,
        )

    def _run(  # noqa: PLR0913
        self,
        *,
        item_type: str,
        items: list[object] | None,
        get_id,
        get_parent,
        apply,
    ) -> PushStats:
        stats = PushStats()
        planned = {(p.item.google_id, p.item.google_parent_id): p for p in self.plan(item_type)}

        if self._mode == "dry":
            # No item models required in dry mode — base decision on ledger only.
            for plan_entry in planned.values():
                self._tally_dry(plan_entry, stats)
            return stats

        if items is None:
            logger.error(
                "Pusher mode=%s needs live %s items, got None; treating all as failed",
                self._mode,
                item_type,
            )
            stats.failed = len(planned)
            return stats

        # Build a lookup from Google id -> model.
        model_index = {(get_id(m), get_parent(m)): m for m in items}

        for key, plan_entry in planned.items():
            model = model_index.get(key)
            if plan_entry.action == "noop":
                stats.unchanged += 1
                continue
            if model is None:
                logger.warning(
                    "Push: %s %s queued but no source model this cycle; skipping",
                    item_type,
                    key[0],
                )
                stats.failed += 1
                continue
            try:
                apply(plan_entry, model, stats)
            except PreconditionFailedError:
                self._record_conflict(item_type, plan_entry.item)
                stats.conflicts += 1
            except GraphError as exc:
                logger.exception("Push %s %s failed: %s", item_type, key[0], exc)
                stats.failed += 1

        return stats

    @staticmethod
    def _tally_dry(planned: PlannedAction, stats: PushStats) -> None:
        if planned.action == "create":
            stats.created += 1
        elif planned.action == "update":
            stats.updated += 1
        else:
            stats.unchanged += 1

    # ---- apply helpers (graph mode) ---------------------------------------

    def _apply_contact(
        self,
        planned: PlannedAction,
        contact: GoogleContact,
        stats: PushStats,
    ) -> None:
        if self._mode != "graph":
            stats.failed += 1
            return
        if self._people is None:
            logger.warning(
                "graph mode missing people_svc; contact %s will be retried later",
                contact.resource_name,
            )
            stats.failed += 1
            return
        if planned.action == "create":
            ms = self._people.create(contact)
            self._persist_outlook(
                "contact",
                contact.resource_name,
                "",
                ms.contact_id,
                ms.etag,
            )
            stats.created += 1
        else:  # update
            ms = self._people.update(
                planned.item.outlook_id,
                contact,
                if_match=planned.item.outlook_etag or None,
            )
            self._persist_outlook(
                "contact",
                contact.resource_name,
                "",
                ms.contact_id,
                ms.etag,
            )
            stats.updated += 1

    def _apply_event(
        self,
        planned: PlannedAction,
        event: GoogleEvent,
        stats: PushStats,
    ) -> None:
        if self._mode != "graph":
            stats.failed += 1
            return
        if self._calendar is None:
            logger.warning(
                "graph mode missing calendar_svc; event %s will be retried later",
                event.event_id,
            )
            stats.failed += 1
            return
        if planned.action == "create":
            ms = self._calendar.create(event.calendar_id, event)
            self._persist_outlook(
                "event",
                event.event_id,
                event.calendar_id,
                ms.event_id,
                ms.etag,
            )
            stats.created += 1
        else:
            ms = self._calendar.update(
                planned.item.outlook_id,
                event.calendar_id,
                event,
                if_match=planned.item.outlook_etag or None,
            )
            self._persist_outlook(
                "event",
                event.event_id,
                event.calendar_id,
                ms.event_id,
                ms.etag,
            )
            stats.updated += 1

    def _apply_task(
        self,
        planned: PlannedAction,
        task: GoogleTask,
        stats: PushStats,
    ) -> None:
        if self._mode != "graph":
            stats.failed += 1
            return
        if self._tasks is None:
            logger.warning(
                "graph mode missing tasks_svc; task %s will be retried later",
                task.task_id,
            )
            stats.failed += 1
            return
        if planned.action == "create":
            ms = self._tasks.create(task.tasklist_id, task)
            self._persist_outlook(
                "task",
                task.task_id,
                task.tasklist_id,
                ms.task_id,
                ms.etag,
            )
            stats.created += 1
        else:
            ms = self._tasks.update(
                task.tasklist_id,
                planned.item.outlook_id,
                task,
                if_match=planned.item.outlook_etag or None,
            )
            self._persist_outlook(
                "task",
                task.task_id,
                task.tasklist_id,
                ms.task_id,
                ms.etag,
            )
            stats.updated += 1

    # ---- ledger + conflict helpers ----------------------------------------

    def _persist_outlook(
        self,
        item_type: str,
        google_id: str,
        google_parent_id: str,
        outlook_id: str,
        outlook_etag: str,
    ) -> None:
        row = self._ledger.get_item(item_type, google_id, google_parent_id)
        if row is None:
            return
        self._ledger.set_outlook_state(
            item_type=item_type,
            google_id=google_id,
            google_parent_id=google_parent_id,
            outlook_id=outlook_id,
            outlook_hash=row.content_hash,
            outlook_etag=outlook_etag,
        )

    # ---- DAV mode ----------------------------------------------------------

    def _run_dav(
        self,
        contacts: list[GoogleContact],
        events: list[GoogleEvent],
        tasks: list[GoogleTask],
    ) -> dict[str, PushStats]:
        """Project every resource to the Radicale filesystem tree in one pass.

        DAV mode has no optimistic concurrency: OCS in Outlook does the
        last-write-wins resolution. We rewrite the full tree and then
        update every ledger row with its new outlook_hash so subsequent
        runs won't re-project unchanged items (we still rebuild because
        it's cheap — the optimisation is possible but not needed here).
        """
        results: dict[str, PushStats] = {
            "contacts": PushStats(),
            "events": PushStats(),
            "tasks": PushStats(),
        }
        if self._projector is None:
            logger.error("DAV mode requires a projector; skipping")
            for s in results.values():
                s.failed += 1
            return results

        try:
            self._projector.project(
                contacts=contacts, events=events, tasks=tasks,
            )
        except OSError:
            logger.exception("DAV projection failed")
            for s in results.values():
                s.failed += max(len(contacts), len(events), len(tasks)) or 1
            return results

        self._account_dav(
            stats=results["contacts"],
            item_type="contact",
            items=[(c.resource_name, "", content_hash(c)) for c in contacts],
        )
        self._account_dav(
            stats=results["events"],
            item_type="event",
            items=[
                (e.event_id, e.calendar_id, content_hash(e)) for e in events
            ],
        )
        self._account_dav(
            stats=results["tasks"],
            item_type="task",
            items=[
                (t.task_id, t.tasklist_id, content_hash(t)) for t in tasks
            ],
        )
        return results

    def _account_dav(
        self,
        *,
        stats: PushStats,
        item_type: str,
        items: list[tuple[str, str, str]],
    ) -> None:
        """Update ledger and stats after a successful DAV projection."""
        for google_id, parent, new_hash in items:
            row = self._ledger.get_item(item_type, google_id, parent)
            if row is None:
                continue
            if row.outlook_hash == new_hash:
                stats.unchanged += 1
                continue
            was_created = not row.outlook_id
            self._ledger.set_outlook_state(
                item_type=item_type,
                google_id=google_id,
                google_parent_id=parent,
                outlook_id=row.outlook_id or _dav_virtual_id(google_id),
                outlook_hash=new_hash,
                outlook_etag="",  # DAV mode doesn't track per-item ETags here
            )
            if was_created:
                stats.created += 1
            else:
                stats.updated += 1

    # ---- deletion propagation ---------------------------------------------

    _TYPE_TO_RESULT_KEY = {"contact": "contacts", "event": "events", "task": "tasks"}

    def _drain_graph_deletion_queue(self) -> dict[str, int]:
        """Issue DELETEs for each queued deletion; return per-type failures."""
        failures: dict[str, int] = {"contacts": 0, "events": 0, "tasks": 0}
        if self._mode != "graph":
            return failures
        for row in self._ledger.list_pending_deletions():
            deletion_id, item_type, google_id, parent_id, outlook_id = row
            rkey = self._TYPE_TO_RESULT_KEY.get(item_type, "contacts")
            if not outlook_id:
                # Nothing to delete on the Outlook side — drop the row.
                self._ledger.clear_pending_deletion(deletion_id)
                continue
            try:
                self._delete_on_graph(item_type, outlook_id, parent_id)
                self._ledger.clear_pending_deletion(deletion_id)
            except GraphError as exc:
                logger.warning(
                    "Graph delete failed for %s %s: %s",
                    item_type,
                    google_id,
                    exc,
                )
                failures[rkey] += 1
        return failures

    def _drain_dav_deletion_queue(self) -> None:
        """DAV projector already dropped the files — just clear the queue."""
        for row in self._ledger.list_pending_deletions():
            self._ledger.clear_pending_deletion(row[0])

    def _delete_on_graph(
        self, item_type: str, outlook_id: str, parent_id: str
    ) -> None:
        if item_type == "contact":
            if self._people is None:
                raise RuntimeError("graph mode missing people_svc")
            self._people.delete(outlook_id)
        elif item_type == "event":
            if self._calendar is None:
                raise RuntimeError("graph mode missing calendar_svc")
            self._calendar.delete(outlook_id)
        elif item_type == "task":
            if self._tasks is None:
                raise RuntimeError("graph mode missing tasks_svc")
            self._tasks.delete(parent_id, outlook_id)

    def _record_conflict(self, item_type: str, item: SyncItem) -> None:
        """On 412 we know Outlook was edited; record a conflict.

        The stored `outlook_hash` is our last-known hash (stale by definition);
        the user will pick a winner and the next push will reconcile.
        """
        conflicts_module.record_conflict(
            self._ledger,
            item_type=item_type,
            google_id=item.google_id,
            google_parent_id=item.google_parent_id,
            google_hash=item.content_hash,
            outlook_hash=item.outlook_hash or "<changed-in-outlook>",
        )


# ---- helper so tests / daemon can hash without reaching into pusher -------


def outlook_side_hash(model: GoogleContact | GoogleEvent | GoogleTask) -> str:
    """Compute the content hash of a Google-side model.

    Exposed so callers outside the pusher can build expected hashes for
    conflict seeding without duplicating the import.
    """
    return content_hash(model)


def _dav_virtual_id(google_id: str) -> str:
    """Synthetic outlook_id used in DAV mode so ledger queries stay consistent."""
    return f"dav:{google_id}"
