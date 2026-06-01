"""Microsoft Graph contacts client — read + write.

Phase 2 (read): fetch + delta sync for /me/contacts, so we can detect
Outlook-side edits for conflict resolution before we overwrite.

Write paths (create/update/delete) live in this same module so callers
get one object per resource type, mirroring Google's people/calendar/tasks
service layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from gbridge.microsoft._http import DeltaExpiredError, GraphClient
from gbridge.microsoft.mapping import (
    google_contact_to_ms_payload,
    ms_payload_to_ms_contact,
)

if TYPE_CHECKING:
    from gbridge.google.models import GoogleContact
    from gbridge.microsoft.auth import MicrosoftAuthManager
    from gbridge.microsoft.models import MicrosoftContact

logger = logging.getLogger(__name__)


class ContactSyncResult(NamedTuple):
    items: list[MicrosoftContact]
    delta_link: str | None
    deleted_ids: list[str]


class GraphPeopleService:
    """Read + (later) write wrapper for /me/contacts."""

    def __init__(
        self,
        auth: MicrosoftAuthManager,
        *,
        client: GraphClient | None = None,
    ) -> None:
        self._client = client or GraphClient(auth)

    def fetch_all(self, delta_link: str | None = None) -> ContactSyncResult:
        """Fetch contacts via /me/contacts/delta (or resume from delta_link).

        If Graph returns 410 on an expired delta link we automatically fall
        back to a full re-sync, mirroring the Google side's 410-GONE recovery.
        """
        try:
            return self._fetch(delta_link)
        except DeltaExpiredError:
            logger.warning("Microsoft delta link expired, performing full sync")
            return self._fetch(None)

    def _fetch(self, delta_link: str | None) -> ContactSyncResult:
        url = delta_link or "/me/contacts/delta"
        items_raw, new_delta = self._client.iter_pages(url)

        contacts: list[MicrosoftContact] = []
        deleted: list[str] = []
        for row in items_raw:
            removed = row.get("@removed")
            if removed:
                cid = row.get("id", "")
                if cid:
                    deleted.append(cid)
                continue
            contacts.append(ms_payload_to_ms_contact(row))

        logger.info(
            "Graph contacts: fetched %d, %d deletions (delta=%s)",
            len(contacts),
            len(deleted),
            delta_link is not None,
        )
        return ContactSyncResult(
            items=contacts, delta_link=new_delta, deleted_ids=deleted
        )

    # ---- write surface -----------------------------------------------------

    def create(self, contact: GoogleContact) -> MicrosoftContact:
        """Create a new contact in Outlook from a Google-side source item."""
        payload = google_contact_to_ms_payload(contact)
        body = self._client.post("/me/contacts", json=payload)
        return ms_payload_to_ms_contact(body)

    def update(
        self,
        outlook_id: str,
        contact: GoogleContact,
        *,
        if_match: str | None = None,
    ) -> MicrosoftContact:
        """Update an existing Outlook contact. Caller passes stored etag for If-Match."""
        payload = google_contact_to_ms_payload(contact)
        body = self._client.patch(
            f"/me/contacts/{outlook_id}",
            json=payload,
            if_match=if_match,
        )
        return ms_payload_to_ms_contact(body)

    def get_one(self, outlook_id: str) -> MicrosoftContact:
        """Fetch a single Outlook contact (used to capture its current etag)."""
        body = self._client.get(f"/me/contacts/{outlook_id}")
        return ms_payload_to_ms_contact(body)

    def delete(self, outlook_id: str, *, if_match: str | None = None) -> None:
        self._client.delete(f"/me/contacts/{outlook_id}", if_match=if_match)
