"""Tests for the diagnostics / `gbridge doctor` self-check."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gbridge.__main__ import main
from gbridge.core.diagnostics import Check, run_diagnostics, summary_line
from gbridge.core.ledger import SyncLedger

if TYPE_CHECKING:
    from pathlib import Path


def _settings(tmp_path: Path, **over: object) -> MagicMock:
    s = MagicMock()
    s.client_secrets_path = tmp_path / "client_secret.json"
    s.db_path = tmp_path / "db.sqlite"
    s.microsoft_client_id = over.get("microsoft_client_id", "")
    s.outlook_mode = over.get("outlook_mode", "disabled")
    return s


class TestRunDiagnostics:
    def test_fresh_install_reports_fails(self, tmp_path: Path) -> None:
        s = _settings(tmp_path)
        with patch("gbridge.core.diagnostics._google_token_present", return_value=False), \
             patch("gbridge.core.diagnostics._microsoft_token_present", return_value=False):
            checks = run_diagnostics(s)
        by_name = {c.name: c for c in checks}
        assert by_name["Google credentials"].status == "fail"
        assert by_name["Google sign-in"].status == "fail"
        assert by_name["Microsoft app ID"].status == "warn"
        assert by_name["Microsoft sign-in"].status == "info"  # skipped, no id
        assert summary_line(checks).startswith("Setup needed")

    def test_google_ready_no_outlook(self, tmp_path: Path) -> None:
        s = _settings(tmp_path)
        s.client_secrets_path.write_text("{}", encoding="utf-8")
        # Seed a ledger so the data check is green.
        lg = SyncLedger(s.db_path)
        lg.upsert_item("contact", "people/c1", "h")
        lg.close()
        with patch("gbridge.core.diagnostics._google_token_present", return_value=True), \
             patch("gbridge.core.diagnostics._microsoft_token_present", return_value=False):
            checks = run_diagnostics(s)
        by_name = {c.name: c for c in checks}
        assert by_name["Google credentials"].status == "ok"
        assert by_name["Google sign-in"].status == "ok"
        assert "1 contacts" in by_name["Local sync data"].detail
        # No Google 'fail' remains -> summary is warn-level (MS app id not set).
        assert "optional steps" in summary_line(checks)

    def test_fully_configured_is_all_set(self, tmp_path: Path) -> None:
        s = _settings(tmp_path, microsoft_client_id="GUID", outlook_mode="graph")
        s.client_secrets_path.write_text("{}", encoding="utf-8")
        lg = SyncLedger(s.db_path)
        lg.close()
        with patch("gbridge.core.diagnostics._google_token_present", return_value=True), \
             patch("gbridge.core.diagnostics._microsoft_token_present", return_value=True), \
             patch("gbridge.outlook.detect.detect_outlook") as det:
            det.return_value.value = "m365"
            checks = run_diagnostics(s)
        statuses = {c.status for c in checks}
        assert "fail" not in statuses
        assert "warn" not in statuses
        assert summary_line(checks) == "All set — GBridge is ready."

    def test_pending_conflicts_warns(self, tmp_path: Path) -> None:
        s = _settings(tmp_path, microsoft_client_id="GUID", outlook_mode="graph")
        s.client_secrets_path.write_text("{}", encoding="utf-8")
        lg = SyncLedger(s.db_path)
        try:
            from gbridge.core import conflicts as cmod

            cmod.record_conflict(
                lg, item_type="contact", google_id="people/c1",
                google_hash="g", outlook_hash="o",
            )
        finally:
            lg.close()
        with patch("gbridge.core.diagnostics._google_token_present", return_value=True), \
             patch("gbridge.core.diagnostics._microsoft_token_present", return_value=True):
            checks = run_diagnostics(s)
        conflict_check = next(c for c in checks if c.name == "Conflicts")
        assert conflict_check.status == "warn"
        assert "1 need resolution" in conflict_check.detail


class TestCheckRender:
    def test_marks(self) -> None:
        assert Check("X", "ok", "y").render() == "  [x] X: y"
        assert Check("X", "fail", "y").render() == "  [ ] X: y"
        assert Check("X", "warn", "y").render() == "  [!] X: y"
        assert Check("X", "info", "y").render() == "  [i] X: y"


class TestDoctorCLI:
    def test_doctor_exit_code_and_output(self, tmp_path: Path, capsys) -> None:
        fake = _settings(tmp_path)
        with patch("gbridge.__main__.Settings", return_value=fake), \
             patch("gbridge.core.diagnostics._google_token_present", return_value=False), \
             patch("gbridge.core.diagnostics._microsoft_token_present", return_value=False):
            backup = sys.argv
            sys.argv = ["gbridge", "doctor"]
            try:
                rc = main()
            finally:
                sys.argv = backup
        out = capsys.readouterr().out
        assert "setup check" in out
        assert "Google credentials" in out
        assert rc == 1  # fresh install has fails
