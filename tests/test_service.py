"""Tests for user-level autostart installers.

The Windows branch is covered indirectly via the dispatcher test only —
winreg is unavailable off Windows.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from gbridge.service import get_installer
from gbridge.service.linux import LinuxInstaller
from gbridge.service.macos import MacOSInstaller


class TestMacOSInstaller:
    def test_roundtrip(self, tmp_path: Path) -> None:
        installer = MacOSInstaller()
        # Redirect $HOME so we don't touch the real system.
        with patch("gbridge.service.macos.Path") as mock_path:
            mock_path.home.return_value = tmp_path
            mock_path.side_effect = Path
            assert installer.is_installed() is False
            loc = installer.install("/usr/local/bin/gbridge")
            assert Path(loc).exists()
            assert installer.is_installed() is True
            content = Path(loc).read_text()
            assert "gbridge" in content
            assert "<string>daemon</string>" in content
            assert installer.uninstall() is True
            assert installer.is_installed() is False


class TestLinuxInstaller:
    def test_roundtrip(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))  # type: ignore[attr-defined]
        installer = LinuxInstaller()
        assert installer.is_installed() is False
        loc = installer.install("/usr/local/bin/gbridge")
        assert Path(loc).exists()
        assert installer.is_installed() is True
        content = Path(loc).read_text()
        assert "ExecStart=/usr/local/bin/gbridge daemon" in content
        assert "Restart=on-failure" in content
        assert installer.uninstall() is True
        assert installer.is_installed() is False


class TestGetInstaller:
    @patch("gbridge.service.platform")
    def test_dispatch_linux(self, mock_platform: object) -> None:
        mock_platform.system.return_value = "Linux"  # type: ignore[attr-defined]
        assert isinstance(get_installer(), LinuxInstaller)

    @patch("gbridge.service.platform")
    def test_dispatch_darwin(self, mock_platform: object) -> None:
        mock_platform.system.return_value = "Darwin"  # type: ignore[attr-defined]
        assert isinstance(get_installer(), MacOSInstaller)
