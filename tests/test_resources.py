"""Tests for the resource-path helper."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from gbridge.utils.resources import ICON_FILENAME, get_icon_path

if TYPE_CHECKING:
    from pathlib import Path


class TestGetIconPath:
    def test_returns_path_in_source_tree(self) -> None:
        path = get_icon_path()
        assert path is not None
        assert path.name == ICON_FILENAME
        assert path.exists()

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        # Simulate a frozen bundle whose _MEIPASS does not contain the icon.
        with patch("gbridge.utils.resources.sys") as mock_sys:
            mock_sys._MEIPASS = str(tmp_path)
            assert get_icon_path() is None
