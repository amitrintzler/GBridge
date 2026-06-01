"""Microsoft To Do tasks client — read + (later) write.

Unlike contacts / events, Microsoft To Do does not expose a /delta endpoint.
Incremental sync uses an `$filter=lastModifiedDateTime gt <ISO>` predicate,
mirroring the Google Tasks `updatedMin` pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gbridge.microsoft._http import GraphClient
from gbridge.microsoft.mapping import (
    google_task_to_ms_payload,
    ms_payload_to_ms_task,
)

if TYPE_CHECKING:
    from gbridge.google.models import GoogleTask
    from gbridge.microsoft.auth import MicrosoftAuthManager
    from gbridge.microsoft.models import MicrosoftTask

logger = logging.getLogger(__name__)


class GraphTasksService:
    """Read + (later) write wrapper for /me/todo/lists and their tasks."""

    def __init__(
        self,
        auth: MicrosoftAuthManager,
        *,
        client: GraphClient | None = None,
    ) -> None:
        self._client = client or GraphClient(auth)

    def list_tasklists(self) -> list[dict[str, str]]:
        """Return all To Do task lists for the signed-in user."""
        lists: list[dict[str, str]] = []
        items, _ = self._client.iter_pages("/me/todo/lists")
        for lst in items:
            lists.append(
                {
                    "id": str(lst.get("id", "")),
                    "title": str(lst.get("displayName", "")),
                }
            )
        return lists

    def fetch_tasks(
        self, tasklist_id: str, updated_since: str | None = None
    ) -> list[MicrosoftTask]:
        """Fetch tasks from a To Do list, optionally filtered by last modified time.

        Args:
            tasklist_id: Graph To Do list id.
            updated_since: ISO 8601 timestamp — only return tasks with
                ``lastModifiedDateTime > updated_since``. Pass None for full.
        """
        params: dict[str, object] = {}
        if updated_since:
            params["$filter"] = f"lastModifiedDateTime gt {updated_since}"

        url = f"/me/todo/lists/{tasklist_id}/tasks"
        items_raw, _ = self._client.iter_pages(url, params=params or None)

        tasks = [ms_payload_to_ms_task(row, tasklist_id) for row in items_raw]
        logger.info(
            "Graph todo [%s]: fetched %d tasks (delta=%s)",
            tasklist_id,
            len(tasks),
            updated_since is not None,
        )
        return tasks

    # ---- write surface -----------------------------------------------------

    def create(self, tasklist_id: str, task: GoogleTask) -> MicrosoftTask:
        payload = google_task_to_ms_payload(task)
        body = self._client.post(
            f"/me/todo/lists/{tasklist_id}/tasks", json=payload
        )
        return ms_payload_to_ms_task(body, tasklist_id)

    def update(
        self,
        tasklist_id: str,
        outlook_id: str,
        task: GoogleTask,
        *,
        if_match: str | None = None,
    ) -> MicrosoftTask:
        payload = google_task_to_ms_payload(task)
        body = self._client.patch(
            f"/me/todo/lists/{tasklist_id}/tasks/{outlook_id}",
            json=payload,
            if_match=if_match,
        )
        return ms_payload_to_ms_task(body, tasklist_id)

    def get_one(self, tasklist_id: str, outlook_id: str) -> MicrosoftTask:
        """Fetch a single Outlook task (used to capture its current etag)."""
        body = self._client.get(
            f"/me/todo/lists/{tasklist_id}/tasks/{outlook_id}"
        )
        return ms_payload_to_ms_task(body, tasklist_id)

    def delete(
        self,
        tasklist_id: str,
        outlook_id: str,
        *,
        if_match: str | None = None,
    ) -> None:
        self._client.delete(
            f"/me/todo/lists/{tasklist_id}/tasks/{outlook_id}",
            if_match=if_match,
        )
