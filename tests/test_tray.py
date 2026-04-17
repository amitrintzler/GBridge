"""Tests for the tray helper — exercises the fallback path and label builders.

The `pystray` / `PIL` imports are lazy, so if they exist we still don't
launch a real tray (would block). We stub the `icon.run()` call so the
composition logic is exercised without a display.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gbridge.utils import tray as tray_module


def _run_with_fake_pystray(**kwargs):
    """Invoke tray.run_tray with pystray stubbed to a fake module."""
    fake_pystray = MagicMock()
    fake_pystray.Menu.SEPARATOR = object()

    icon = MagicMock()
    # run() blocks in real life — pretend it returned immediately.
    icon.run.return_value = None
    fake_pystray.Icon.return_value = icon
    fake_pystray.MenuItem = lambda *a, **kw: ("MI", a, kw)
    fake_pystray.Menu = MagicMock(side_effect=lambda *items: items)
    fake_pystray.Menu.SEPARATOR = "<sep>"

    fake_pil = MagicMock()
    fake_pil.Image.open.return_value = MagicMock()

    with patch.dict(
        "sys.modules",
        {"pystray": fake_pystray, "PIL": fake_pil},
    ), patch.object(tray_module, "get_icon_path", return_value="fake.ico"):
        ok = tray_module.run_tray(**kwargs)
    return ok, fake_pystray, icon


class TestFallback:
    def test_returns_false_when_pystray_missing(self) -> None:
        # Break the import so the ImportError branch fires.
        with patch.dict("sys.modules", {"pystray": None, "PIL": None}):
            ok = tray_module.run_tray(
                on_sync=lambda: None,
                on_status=lambda: None,
                on_quit=lambda: None,
            )
        assert ok is False

    def test_returns_false_when_icon_path_missing(self) -> None:
        fake_pystray = MagicMock()
        with patch.dict(
            "sys.modules",
            {"pystray": fake_pystray, "PIL": MagicMock()},
        ), patch.object(tray_module, "get_icon_path", return_value=None):
            ok = tray_module.run_tray(
                on_sync=lambda: None,
                on_status=lambda: None,
                on_quit=lambda: None,
            )
        assert ok is False


class TestMenuComposition:
    def test_basic_menu_includes_sync(self) -> None:
        ok, pystray, icon = _run_with_fake_pystray(
            on_sync=lambda: None,
            on_status=lambda: None,
            on_quit=lambda: None,
        )
        assert ok is True
        assert icon.run.called
        # At least the Sync now + Show status + What GBridge reads + Quit items.
        items = pystray.Menu.call_args[0]
        titles = [a[1][0] for a in items if isinstance(a, tuple) and a[0] == "MI"]
        assert "Sync now" in titles
        assert "Show status" in titles
        assert "Quit" in titles

    def test_push_item_added_when_callback_given(self) -> None:
        ok, pystray, _ = _run_with_fake_pystray(
            on_sync=lambda: None,
            on_status=lambda: None,
            on_quit=lambda: None,
            on_push=lambda: None,
        )
        assert ok
        items = pystray.Menu.call_args[0]
        titles = [a[1][0] for a in items if isinstance(a, tuple) and a[0] == "MI"]
        assert "Push to Outlook" in titles

    def test_conflicts_item_uses_dynamic_label(self) -> None:
        captured: list[int] = []

        def count() -> int:
            captured.append(1)
            return 3

        ok, pystray, _ = _run_with_fake_pystray(
            on_sync=lambda: None,
            on_status=lambda: None,
            on_quit=lambda: None,
            on_conflicts=lambda: None,
            conflicts_count_fn=count,
        )
        assert ok
        items = pystray.Menu.call_args[0]
        conflict_items = [
            a for a in items
            if isinstance(a, tuple) and a[0] == "MI" and callable(a[1][0])
        ]
        assert conflict_items, "expected a dynamic-label conflicts item"
        label_fn = conflict_items[0][1][0]
        assert label_fn(None) == "Resolve conflicts (3)"

    def test_conflicts_label_safe_when_counter_raises(self) -> None:
        def boom() -> int:
            raise RuntimeError("broken")

        ok, pystray, _ = _run_with_fake_pystray(
            on_sync=lambda: None,
            on_status=lambda: None,
            on_quit=lambda: None,
            on_conflicts=lambda: None,
            conflicts_count_fn=boom,
        )
        assert ok
        items = pystray.Menu.call_args[0]
        conflict_items = [
            a for a in items
            if isinstance(a, tuple) and a[0] == "MI" and callable(a[1][0])
        ]
        label_fn = conflict_items[0][1][0]
        # Broken counter -> label falls back to zero, not a raise.
        assert label_fn(None) == "Resolve conflicts (0)"

    def test_menu_includes_separator(self) -> None:
        ok, pystray, _ = _run_with_fake_pystray(
            on_sync=lambda: None,
            on_status=lambda: None,
            on_quit=lambda: None,
        )
        assert ok
        items = pystray.Menu.call_args[0]
        assert "<sep>" in items


class TestCallbackDispatch:
    def test_sync_callback_spawns_thread(self) -> None:
        """Clicking 'Sync now' spawns a daemon thread that calls the callback."""
        calls: list[int] = []

        def on_sync() -> None:
            calls.append(1)

        ok, pystray, _ = _run_with_fake_pystray(
            on_sync=on_sync,
            on_status=lambda: None,
            on_quit=lambda: None,
        )
        assert ok
        # Find the Sync now item and invoke its handler.
        items = pystray.Menu.call_args[0]
        for item in items:
            if isinstance(item, tuple) and item[1][0] == "Sync now":
                handler = item[1][1]
                handler(None, None)  # icon, menu_item args
                break
        else:
            pytest.fail("No Sync now item")

        import time
        time.sleep(0.1)  # let the daemon thread run
        assert calls == [1]
