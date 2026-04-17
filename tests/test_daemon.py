"""Tests for the Daemon — orchestrator for sync + push + Radicale + tray."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gbridge.core.pusher import PushStats
from gbridge.daemon import Daemon

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.sync_interval_minutes = 0  # disables scheduling during tests
    s.push_interval_minutes = 0
    s.outlook_mode = "disabled"
    s.db_path = tmp_path / "d.db"
    s.client_secrets_path = tmp_path / "secrets.json"
    s.microsoft_client_id = None
    s.microsoft_tenant_id = "common"
    s.dav_host = "127.0.0.1"
    s.dav_port = 8765
    return s


class TestBuildPusher:
    def test_disabled_returns_none(self, settings: MagicMock) -> None:
        d = Daemon(settings=settings)
        # ledger arg can be None — we never reach it.
        assert d._build_pusher(MagicMock(), "disabled") is None  # noqa: SLF001

    def test_graph_without_client_id_notifies_and_returns_none(
        self, settings: MagicMock
    ) -> None:
        settings.outlook_mode = "graph"
        settings.microsoft_client_id = None
        d = Daemon(settings=settings)
        with patch("gbridge.daemon.notify") as mock_notify:
            result = d._build_pusher(MagicMock(), "graph")  # noqa: SLF001
        assert result is None
        mock_notify.assert_called_once()

    def test_dav_mode_returns_pusher(
        self, settings: MagicMock, tmp_path: Path
    ) -> None:
        settings.outlook_mode = "dav"
        d = Daemon(settings=settings)
        with patch("gbridge.daemon.get_data_dir", return_value=tmp_path):
            pusher = d._build_pusher(MagicMock(), "dav")  # noqa: SLF001
        assert pusher is not None
        assert pusher.mode == "dav"


class TestNotifyPush:
    def test_formats_message_with_counts(self) -> None:
        results = {
            "contacts": PushStats(created=2, updated=1),
            "events": PushStats(conflicts=1),
            "tasks": PushStats(),  # empty — skipped in output
        }
        with patch("gbridge.daemon.notify") as mock_notify:
            Daemon._notify_push(results)
        assert mock_notify.called
        body = mock_notify.call_args[0][1]
        assert "contacts: 2 new, 1 updated" in body
        assert "events: 1 conflicts" in body
        assert "tasks" not in body  # no counters -> not rendered

    def test_no_notify_when_all_zero(self) -> None:
        results = {"contacts": PushStats(), "events": PushStats(), "tasks": PushStats()}
        with patch("gbridge.daemon.notify") as mock_notify:
            Daemon._notify_push(results)
        mock_notify.assert_not_called()


class TestRunSyncSafe:
    def test_skips_when_lock_held(self, settings: MagicMock) -> None:
        d = Daemon(settings=settings)
        d._lock.acquire()  # noqa: SLF001 - simulate another sync running
        try:
            with patch("gbridge.daemon.GoogleAuthManager") as auth_cls:
                d._run_sync_safe()  # noqa: SLF001
            auth_cls.assert_not_called()
        finally:
            d._lock.release()  # noqa: SLF001

    def test_notifies_when_credentials_missing(
        self, settings: MagicMock
    ) -> None:
        d = Daemon(settings=settings)
        with patch("gbridge.daemon.notify") as mock_notify:
            d._run_sync_safe()  # noqa: SLF001
        mock_notify.assert_called_once()
        title = mock_notify.call_args[0][0]
        assert "setup needed" in title.lower()


class TestConflictsHelpers:
    def test_count_conflicts_returns_zero_on_fresh_ledger(
        self, settings: MagicMock
    ) -> None:
        d = Daemon(settings=settings)
        assert d._count_conflicts() == 0  # noqa: SLF001

    def test_show_status_reads_ledger(
        self, settings: MagicMock, tmp_path: Path
    ) -> None:
        from gbridge.core.ledger import SyncLedger

        # Seed a few rows.
        lg = SyncLedger(settings.db_path)
        try:
            lg.upsert_item("contact", "c1", "h")
            lg.upsert_item("event", "e1", "h", google_parent_id="cal")
        finally:
            lg.close()

        d = Daemon(settings=settings)
        with patch("gbridge.daemon.notify") as mock_notify:
            d._show_status()  # noqa: SLF001
        args = mock_notify.call_args[0]
        assert "contacts" in args[1]
        assert "events" in args[1]


class TestStop:
    def test_stop_sets_event_and_shuts_down(
        self, settings: MagicMock
    ) -> None:
        d = Daemon(settings=settings)
        d.stop()
        assert d._stop_event.is_set()  # noqa: SLF001


class TestRunPushSafe:
    def test_skips_when_disabled(self, settings: MagicMock) -> None:
        settings.outlook_mode = "disabled"
        d = Daemon(settings=settings)
        with patch("gbridge.daemon.notify") as mock_notify:
            d._run_push_safe()  # noqa: SLF001
        # No notification because the mode is disabled => quiet skip.
        mock_notify.assert_not_called()

    def test_skips_when_lock_held(self, settings: MagicMock) -> None:
        settings.outlook_mode = "dav"
        d = Daemon(settings=settings)
        d._lock.acquire()  # noqa: SLF001
        try:
            with patch("gbridge.daemon.get_data_dir") as mock_dd:
                d._run_push_safe()  # noqa: SLF001
            mock_dd.assert_not_called()
        finally:
            d._lock.release()  # noqa: SLF001

    def test_dav_mode_calls_pusher_and_notifies(
        self, settings: MagicMock, tmp_path: Path
    ) -> None:
        settings.outlook_mode = "dav"
        settings.db_path = tmp_path / "push.db"
        d = Daemon(settings=settings)
        d._last_sync_items = {"contacts": [], "events": [], "tasks": []}  # noqa: SLF001
        from gbridge.core.pusher import PushStats

        fake_pusher = MagicMock()
        fake_pusher.run_push.return_value = {
            "contacts": PushStats(created=1),
            "events": PushStats(),
            "tasks": PushStats(),
        }
        with patch.object(d, "_build_pusher", return_value=fake_pusher), \
             patch("gbridge.daemon.notify") as mock_notify:
            d._run_push_safe()  # noqa: SLF001
        fake_pusher.run_push.assert_called_once()
        mock_notify.assert_called_once()


class TestRadicaleLifecycle:
    def test_start_is_noop_when_not_dav(
        self, settings: MagicMock
    ) -> None:
        d = Daemon(settings=settings)
        with patch("gbridge.daemon.RadicaleSupervisor") as sup_cls:
            d._start_radicale_if_needed()  # noqa: SLF001
        sup_cls.assert_not_called()

    def test_start_spawns_supervisor_on_dav(
        self, settings: MagicMock, tmp_path: Path
    ) -> None:
        settings.outlook_mode = "dav"
        d = Daemon(settings=settings)
        fake_sup = MagicMock()
        fake_sup.is_healthy.return_value = True
        with patch("gbridge.daemon.RadicaleSupervisor", return_value=fake_sup), \
             patch("gbridge.daemon.get_data_dir", return_value=tmp_path):
            d._start_radicale_if_needed()  # noqa: SLF001
        fake_sup.start.assert_called_once()
        assert d._radicale is fake_sup  # noqa: SLF001

    def test_stop_radicale_invokes_supervisor(
        self, settings: MagicMock
    ) -> None:
        d = Daemon(settings=settings)
        d._radicale = MagicMock()  # noqa: SLF001
        d._stop_radicale()  # noqa: SLF001
        d._radicale  # noqa: SLF001, B018 - check it's been reset
        assert d._radicale is None  # noqa: SLF001
