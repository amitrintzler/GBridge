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
