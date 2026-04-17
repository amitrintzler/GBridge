"""Tests for the Radicale subprocess supervisor.

We mock `subprocess.Popen` and `socket.create_connection` so tests don't
actually spawn a process or open a port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gbridge.dav.server import (
    RadicaleSupervisor,
    is_pid_alive,
    make_config,
    read_pid,
)

if TYPE_CHECKING:
    from pathlib import Path


class _FakeProc:
    """Minimal stand-in for subprocess.Popen."""

    def __init__(self, pid: int = 42, exit_code: int | None = None) -> None:
        self.pid = pid
        self.returncode = exit_code
        self._exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminated = True
        self._exit_code = 0
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self._exit_code = -9
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._exit_code or 0


@pytest.fixture
def config(tmp_path: Path):
    return make_config(host="127.0.0.1", port=8765, data_dir=tmp_path)


class TestRadicaleSupervisor:
    def test_start_writes_config_and_spawns(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc(pid=1234)
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake) as popen:
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()

        assert popen.called
        args = popen.call_args[0][0]
        assert args[1:3] == ["-m", "radicale"]
        # Config file was written with our host / port.
        cfg_text = config.config_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
        assert "127.0.0.1:8765" in cfg_text
        assert "type = none" in cfg_text  # auth stays off on localhost
        # Pidfile was written.
        assert config.pid_path.read_text(encoding="utf-8") == "1234"  # type: ignore[attr-defined]

    def test_is_healthy_true_when_socket_opens(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc()
        with (
            patch("gbridge.dav.server.subprocess.Popen", return_value=fake),
            patch("gbridge.dav.server.socket.create_connection") as sock,
        ):
            # Simulate port open immediately.
            sock.return_value.__enter__.return_value = MagicMock()
            sock.return_value.__exit__.return_value = False

            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            assert sup.is_healthy(timeout=0.5) is True

    def test_is_healthy_false_when_process_exits(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc(exit_code=1)  # died before listening
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            assert sup.is_healthy(timeout=0.5) is False

    def test_is_healthy_timeout(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc()
        with (
            patch("gbridge.dav.server.subprocess.Popen", return_value=fake),
            patch(
                "gbridge.dav.server.socket.create_connection",
                side_effect=OSError("refused"),
            ),
        ):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            assert sup.is_healthy(timeout=0.2) is False

    def test_stop_terminates(self, tmp_path: Path, config: object) -> None:
        fake = _FakeProc(pid=42)
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            sup.stop()

        assert fake.terminated is True
        assert not config.pid_path.exists()  # type: ignore[attr-defined]

    def test_stop_kills_on_timeout(
        self, tmp_path: Path, config: object
    ) -> None:
        # Simulate a process that ignores terminate()
        fake = _FakeProc(pid=42)

        def fake_wait(timeout: float | None = None) -> int:
            raise __import__("subprocess").TimeoutExpired(cmd="radicale", timeout=timeout or 0)

        fake.wait = fake_wait  # type: ignore[assignment]

        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            # .wait raises once; .kill() is called; .wait raises again (caught).
            sup.stop(grace_seconds=0.0)

        assert fake.killed is True

    def test_stop_is_noop_when_not_started(self, config: object) -> None:
        sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
        sup.stop()  # no exception


class TestPidHelpers:
    def test_read_and_write_pid(self, tmp_path: Path) -> None:
        pid_path = tmp_path / "x.pid"
        pid_path.write_text("99", encoding="utf-8")
        assert read_pid(pid_path) == 99

    def test_read_missing_pid(self, tmp_path: Path) -> None:
        assert read_pid(tmp_path / "nope.pid") is None

    def test_read_garbage_pid(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.pid"
        p.write_text("not a number", encoding="utf-8")
        assert read_pid(p) is None

    def test_is_pid_alive_zero(self) -> None:
        assert is_pid_alive(0) is False

    def test_is_pid_alive_negative(self) -> None:
        assert is_pid_alive(-1) is False

    def test_is_pid_alive_returns_true_for_self(self) -> None:
        import os
        # current process is obviously alive
        assert is_pid_alive(os.getpid()) is True


class TestSupervisorExtra:
    def test_start_cleans_stale_pidfile(
        self, tmp_path: Path, config: object
    ) -> None:
        config.pid_path.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
        config.pid_path.write_text("99999", encoding="utf-8")  # type: ignore[attr-defined]
        fake = _FakeProc(pid=1)
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
        # Start overwrites the pidfile with its own pid.
        assert config.pid_path.read_text(encoding="utf-8") == "1"  # type: ignore[attr-defined]

    def test_pid_property_none_before_start(self, config: object) -> None:
        sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
        assert sup.pid is None

    def test_pid_property_after_start(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc(pid=123)
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
        assert sup.pid == 123

    def test_stop_when_process_already_exited(
        self, tmp_path: Path, config: object
    ) -> None:
        fake = _FakeProc(pid=1, exit_code=0)
        with patch("gbridge.dav.server.subprocess.Popen", return_value=fake):
            sup = RadicaleSupervisor(config)  # type: ignore[arg-type]
            sup.start()
            sup.stop()  # should be a no-op clean-up
