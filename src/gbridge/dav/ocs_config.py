"""Generate a seed Outlook CalDav Synchronizer per-profile config file.

OCS keeps its per-profile settings under
``%APPDATA%\\CalDavSynchronizer\\options_<profile>.xml``. The plain MSI
install of OCS does NOT create these — the user is expected to open OCS
inside Outlook and click through a setup wizard. Our installer skips that
friction by seeding an XML pointing at our local Radicale, pre-named as
"GBridge Contacts / Calendar / Tasks". The user still has to pick the
target Outlook folder inside OCS the first time, but server URLs,
protocols, and sync intervals are already filled in.

The XML format is OCS-specific. We emit only the fields OCS requires to
import a profile (any missing optional fields default inside OCS).

References:
    https://github.com/aluxnimm/outlookcaldavsynchronizer
"""

from __future__ import annotations

import logging
import os
import platform
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET  # noqa: S405 - only emit, no parsing of untrusted input

logger = logging.getLogger(__name__)


OCS_ADAPTERS = {
    "contacts": "CardDavContacts",
    "calendar": "CalDavCalendar",
    "tasks": "CalDavTasks",
}


def ocs_config_dir() -> Path:
    """Return the per-user OCS config directory (creating it if needed)."""
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
        root = Path(appdata) / "CalDavSynchronizer"
    else:
        # OCS is Windows-only in practice, but tests / CI on Linux need a path.
        root = Path.home() / ".config" / "CalDavSynchronizer"
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_profile_xml(
    *,
    dav_host: str,
    dav_port: int,
    sync_interval_minutes: int = 15,
    user: str = "gbridge",
) -> str:
    """Return a complete OCS options XML string."""
    root = ET.Element("Options")
    profiles = ET.SubElement(root, "Options")

    base_url = f"http://{dav_host}:{dav_port}/{user}"
    for kind, adapter in OCS_ADAPTERS.items():
        opt = ET.SubElement(profiles, "Option")
        ET.SubElement(opt, "Id").text = str(uuid.uuid4())
        ET.SubElement(opt, "Name").text = f"GBridge {kind.capitalize()}"
        ET.SubElement(opt, "Inactive").text = "false"
        ET.SubElement(opt, "Active").text = "true"
        ET.SubElement(opt, "ServerAdapterType").text = adapter
        ET.SubElement(opt, "CalenderUrl").text = f"{base_url}/{kind}/"
        ET.SubElement(opt, "UserName").text = ""
        ET.SubElement(opt, "Password").text = ""
        ET.SubElement(opt, "EmailAddress").text = ""
        ET.SubElement(
            opt, "SynchronizationIntervalInMinutes"
        ).text = str(sync_interval_minutes)
        # Bindings the user fills from OCS UI on first run:
        ET.SubElement(opt, "OutlookFolderEntryId").text = ""
        ET.SubElement(opt, "OutlookProfileName").text = ""

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Python 3.9+ pretty-print
    body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"


def write_profile_config(
    *,
    dav_host: str,
    dav_port: int,
    sync_interval_minutes: int = 15,
    user: str = "gbridge",
    profile_name: str = "GBridge",
    target_dir: Path | None = None,
) -> Path:
    """Write the options_<profile>.xml file and return its path.

    Safe to call repeatedly — it overwrites the target atomically.
    """
    directory = target_dir or ocs_config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    xml_body = build_profile_xml(
        dav_host=dav_host,
        dav_port=dav_port,
        sync_interval_minutes=sync_interval_minutes,
        user=user,
    )
    target = directory / f"options_{profile_name}.xml"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(xml_body, encoding="utf-8")
    tmp.replace(target)
    logger.info("Wrote OCS profile config: %s", target)
    return target
