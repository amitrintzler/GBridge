"""Tests for Outlook auto-detection."""

from __future__ import annotations

from unittest.mock import patch

from gbridge.outlook.detect import OutlookType, detect_outlook


class TestOutlookDetection:
    @patch("gbridge.outlook.detect.platform")
    def test_linux_no_outlook(self, mock_platform: object) -> None:
        mock_platform.system.return_value = "Linux"  # type: ignore[attr-defined]
        with patch("gbridge.outlook.detect.shutil") as mock_shutil:
            mock_shutil.which.return_value = None
            result = detect_outlook()
            assert result == OutlookType.NOT_FOUND

    @patch("gbridge.outlook.detect.platform")
    def test_linux_with_outlook_command(self, mock_platform: object) -> None:
        mock_platform.system.return_value = "Linux"  # type: ignore[attr-defined]
        with patch("gbridge.outlook.detect.shutil") as mock_shutil:
            mock_shutil.which.return_value = "/usr/bin/outlook"
            result = detect_outlook()
            assert result == OutlookType.STANDALONE

    @patch("gbridge.outlook.detect.platform")
    @patch("gbridge.outlook.detect._detect_macos")
    def test_macos_delegates(
        self, mock_detect: object, mock_platform: object
    ) -> None:
        mock_platform.system.return_value = "Darwin"  # type: ignore[attr-defined]
        mock_detect.return_value = OutlookType.M365  # type: ignore[attr-defined]
        result = detect_outlook()
        assert result == OutlookType.M365

    @patch("gbridge.outlook.detect.platform")
    @patch("gbridge.outlook.detect._detect_windows")
    def test_windows_delegates(
        self, mock_detect: object, mock_platform: object
    ) -> None:
        mock_platform.system.return_value = "Windows"  # type: ignore[attr-defined]
        mock_detect.return_value = OutlookType.STANDALONE  # type: ignore[attr-defined]
        result = detect_outlook()
        assert result == OutlookType.STANDALONE

    def test_enum_values(self) -> None:
        assert OutlookType.M365.value == "m365"
        assert OutlookType.STANDALONE.value == "standalone"
        assert OutlookType.NOT_FOUND.value == "not_found"


class TestPathsReadDisclosure:
    """`paths_read_for_current_os` drives the transparency banner."""

    def test_windows(self) -> None:
        from gbridge.outlook.detect import (
            WINDOWS_REGISTRY_PATHS_READ,
            paths_read_for_current_os,
        )
        with patch("gbridge.outlook.detect.platform") as mp:
            mp.system.return_value = "Windows"
            assert paths_read_for_current_os() == WINDOWS_REGISTRY_PATHS_READ

    def test_macos(self) -> None:
        from gbridge.outlook.detect import (
            MACOS_PATHS_READ,
            paths_read_for_current_os,
        )
        with patch("gbridge.outlook.detect.platform") as mp:
            mp.system.return_value = "Darwin"
            assert paths_read_for_current_os() == MACOS_PATHS_READ

    def test_linux_default(self) -> None:
        from gbridge.outlook.detect import (
            LINUX_PATHS_READ,
            paths_read_for_current_os,
        )
        with patch("gbridge.outlook.detect.platform") as mp:
            mp.system.return_value = "Linux"
            assert paths_read_for_current_os() == LINUX_PATHS_READ


class TestMacos:
    """Covers the `_detect_macos` branches without a real macOS."""

    def test_app_missing_returns_not_found(self) -> None:
        from gbridge.outlook.detect import _detect_macos

        with patch("pathlib.Path.exists", return_value=False):
            assert _detect_macos() == OutlookType.NOT_FOUND

    def test_app_present_exchange_in_prefs_is_m365(self) -> None:
        from gbridge.outlook.detect import _detect_macos

        fake_result = type("R", (), {"returncode": 0, "stdout": "Exchange account"})
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run", return_value=fake_result):
            assert _detect_macos() == OutlookType.M365

    def test_app_present_no_exchange_is_standalone(self) -> None:
        from gbridge.outlook.detect import _detect_macos

        fake_result = type("R", (), {"returncode": 0, "stdout": "IMAP only"})
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run", return_value=fake_result):
            assert _detect_macos() == OutlookType.STANDALONE

    def test_defaults_command_failure_falls_back_to_standalone(self) -> None:
        from gbridge.outlook.detect import _detect_macos

        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            assert _detect_macos() == OutlookType.STANDALONE


class TestWindowsBranches:
    """Cover the winreg import-guarded paths via direct import of helpers."""

    def test_enumerate_versions_returns_empty_on_missing_key(self) -> None:
        from gbridge.outlook.detect import _enumerate_office_versions

        fake_winreg = type(
            "W", (), {
                "HKEY_CURRENT_USER": 0,
                "KEY_READ": 0,
                "OpenKey": lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError),
            },
        )
        with patch.dict("sys.modules", {"winreg": fake_winreg}):
            assert _enumerate_office_versions(r"SOFTWARE\Microsoft\Office") == []

    def test_profile_has_exchange_false_when_import_fails(self) -> None:
        from gbridge.outlook.detect import _windows_profile_has_exchange

        with patch.dict("sys.modules", {"winreg": None}):
            assert (
                _windows_profile_has_exchange("HKCU\\...\\Profiles", "Default") is False
            )
