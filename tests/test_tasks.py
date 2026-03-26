"""Tests for the Google Tasks API wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gbridge.google.tasks import TasksService


class TestTasksService:
    def test_parse_task(self, sample_task_response: dict) -> None:
        task = TasksService._parse_task(sample_task_response, "tl1")
        assert task.task_id == "task_xyz789"
        assert task.tasklist_id == "tl1"
        assert task.title == "Review PR #42"
        assert task.notes == "Check the edge cases"
        assert task.status == "needsAction"
        assert task.due == "2025-01-20"
        assert task.completed is None

    def test_parse_task_completed(self) -> None:
        task = TasksService._parse_task(
            {
                "id": "t_done",
                "title": "Done task",
                "status": "completed",
                "completed": "2025-01-18T14:00:00.000Z",
                "updated": "2025-01-18T14:00:00.000Z",
            },
            "tl1",
        )
        assert task.status == "completed"
        assert task.completed == "2025-01-18T14:00:00.000Z"

    def test_parse_task_minimal(self) -> None:
        task = TasksService._parse_task({"id": "t_min"}, "tl1")
        assert task.task_id == "t_min"
        assert task.title == ""
        assert task.notes == ""
        assert task.status == "needsAction"

    @patch("gbridge.google.tasks.build")
    def test_fetch_tasks(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.tasks().list().execute.return_value = {
            "items": [
                {
                    "id": "t1", "title": "Task 1",
                    "status": "needsAction", "updated": "2025-01-15T00:00:00Z",
                },
                {
                    "id": "t2", "title": "Task 2",
                    "status": "completed", "updated": "2025-01-16T00:00:00Z",
                },
            ]
        }

        svc = TasksService(MagicMock())
        tasks = svc.fetch_tasks("tl1")
        assert len(tasks) == 2
        assert tasks[0].task_id == "t1"
        assert tasks[1].status == "completed"

    @patch("gbridge.google.tasks.build")
    def test_list_tasklists(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.tasklists().list().execute.return_value = {
            "items": [
                {"id": "tl1", "title": "My Tasks", "updated": "2025-01-01T00:00:00Z"},
            ]
        }

        svc = TasksService(MagicMock())
        tls = svc.list_tasklists()
        assert len(tls) == 1
        assert tls[0]["title"] == "My Tasks"
