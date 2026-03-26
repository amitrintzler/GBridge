"""Google Tasks API wrapper — read-only task sync.

Security: uses ``tasks.readonly`` scope — cannot create, modify,
or delete any tasks in the user's Google account.

Sync strategy:
- First run per tasklist: full fetch
- Subsequent runs: delta via ``updatedMin`` timestamp
- Always fetches completed and hidden tasks for a full picture
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from googleapiclient.discovery import build

from gbridge.config.defaults import DEFAULT_PAGE_SIZE, TASKS_API_VERSION
from gbridge.google.models import GoogleTask
from gbridge.utils.backoff import retry_on_api_error

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)


class TasksService:
    """Read-only wrapper around the Google Tasks API."""

    def __init__(self, credentials: Credentials) -> None:
        self._service = build(
            "tasks", TASKS_API_VERSION, credentials=credentials, cache_discovery=False
        )

    @retry_on_api_error()
    def list_tasklists(self) -> list[dict[str, str]]:
        """Return all task lists for the authenticated user.

        Each dict contains 'id', 'title', and 'updated'.
        """
        tasklists: list[dict[str, str]] = []
        page_token: str | None = None

        while True:
            kwargs: dict[str, object] = {"maxResults": DEFAULT_PAGE_SIZE}
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.tasklists().list(**kwargs).execute()

            for tl in response.get("items", []):
                tasklists.append({
                    "id": tl["id"],
                    "title": tl.get("title", ""),
                    "updated": tl.get("updated", ""),
                })

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return tasklists

    def fetch_tasks(
        self, tasklist_id: str, updated_min: str | None = None
    ) -> list[GoogleTask]:
        """Fetch tasks from a tasklist, optionally only those updated after a timestamp.

        Args:
            tasklist_id: The ID of the task list.
            updated_min: ISO 8601 timestamp — only return tasks updated after this.
        """
        return self._fetch(tasklist_id, updated_min=updated_min)

    @retry_on_api_error()
    def _fetch_page(
        self,
        tasklist_id: str,
        updated_min: str | None,
        page_token: str | None,
    ) -> dict:
        kwargs: dict[str, object] = {
            "tasklist": tasklist_id,
            "maxResults": DEFAULT_PAGE_SIZE,
            "showCompleted": True,
            "showHidden": True,
        }
        if updated_min:
            kwargs["updatedMin"] = updated_min
        if page_token:
            kwargs["pageToken"] = page_token

        return self._service.tasks().list(**kwargs).execute()  # type: ignore[no-any-return]

    def _fetch(
        self, tasklist_id: str, updated_min: str | None
    ) -> list[GoogleTask]:
        tasks: list[GoogleTask] = []
        page_token: str | None = None

        while True:
            response = self._fetch_page(tasklist_id, updated_min, page_token)

            for task in response.get("items", []):
                tasks.append(self._parse_task(task, tasklist_id))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            "Tasks API [%s]: fetched %d tasks (delta=%s)",
            tasklist_id,
            len(tasks),
            updated_min is not None,
        )
        return tasks

    @staticmethod
    def _parse_task(task: dict, tasklist_id: str) -> GoogleTask:
        """Parse a Tasks API task resource into a GoogleTask."""
        return GoogleTask(
            task_id=task.get("id", ""),
            tasklist_id=tasklist_id,
            title=task.get("title", ""),
            notes=task.get("notes", ""),
            status=task.get("status", "needsAction"),
            due=task.get("due"),
            completed=task.get("completed"),
            updated=task.get("updated", ""),
            raw=task,
        )
