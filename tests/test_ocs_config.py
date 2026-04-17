"""Tests for the Outlook CalDav Synchronizer profile config generator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET  # noqa: S405 - parses our own output

from gbridge.dav.ocs_config import (
    OCS_ADAPTERS,
    build_profile_xml,
    write_profile_config,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestBuildXml:
    def test_contains_three_options(self) -> None:
        body = build_profile_xml(dav_host="127.0.0.1", dav_port=8765)
        root = ET.fromstring(body)  # noqa: S314 - our own output
        options = root.findall("Options/Option")
        assert len(options) == 3

    def test_urls_and_adapters(self) -> None:
        body = build_profile_xml(
            dav_host="127.0.0.1", dav_port=8765, user="gbridge"
        )
        root = ET.fromstring(body)  # noqa: S314
        names = {o.findtext("Name"): o for o in root.findall("Options/Option")}
        assert "GBridge Contacts" in names
        assert "GBridge Calendar" in names
        assert "GBridge Tasks" in names

        adapters = {
            o.findtext("Name"): o.findtext("ServerAdapterType")
            for o in root.findall("Options/Option")
        }
        assert adapters["GBridge Contacts"] == OCS_ADAPTERS["contacts"]
        assert adapters["GBridge Calendar"] == OCS_ADAPTERS["calendar"]
        assert adapters["GBridge Tasks"] == OCS_ADAPTERS["tasks"]

        # URLs resolve to 127.0.0.1:8765.
        for opt in root.findall("Options/Option"):
            url = opt.findtext("CalenderUrl") or ""
            assert url.startswith("http://127.0.0.1:8765/gbridge/")
            assert url.endswith("/")

    def test_interval_applied(self) -> None:
        body = build_profile_xml(
            dav_host="127.0.0.1", dav_port=8765, sync_interval_minutes=30
        )
        root = ET.fromstring(body)  # noqa: S314
        for opt in root.findall("Options/Option"):
            assert opt.findtext("SynchronizationIntervalInMinutes") == "30"

    def test_unique_ids_per_option(self) -> None:
        body = build_profile_xml(dav_host="127.0.0.1", dav_port=8765)
        root = ET.fromstring(body)  # noqa: S314
        ids = [o.findtext("Id") for o in root.findall("Options/Option")]
        assert len(set(ids)) == 3  # all unique


class TestWriteFile:
    def test_writes_expected_path(self, tmp_path: Path) -> None:
        out = write_profile_config(
            dav_host="127.0.0.1",
            dav_port=8765,
            profile_name="TestProfile",
            target_dir=tmp_path,
        )
        assert out == tmp_path / "options_TestProfile.xml"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<?xml")
        # Well-formed XML
        ET.fromstring(content)  # noqa: S314

    def test_overwrite_safe(self, tmp_path: Path) -> None:
        write_profile_config(
            dav_host="127.0.0.1", dav_port=8765,
            profile_name="P", target_dir=tmp_path,
        )
        write_profile_config(
            dav_host="127.0.0.1", dav_port=9999,
            profile_name="P", target_dir=tmp_path,
        )
        content = (tmp_path / "options_P.xml").read_text(encoding="utf-8")
        assert "9999" in content
        assert "8765" not in content
