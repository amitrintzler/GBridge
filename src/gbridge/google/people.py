"""Google People API wrapper — read-only contact sync.

Security: uses ``contacts.readonly`` scope — cannot modify or delete
any contacts in the user's Google account.

Sync strategy:
- First run: full fetch with ``requestSyncToken=True``
- Subsequent runs: delta fetch using the stored ``syncToken``
- If Google returns 410 GONE (token expired), falls back to full fetch
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gbridge.config.defaults import DEFAULT_PAGE_SIZE, PEOPLE_API_VERSION, PEOPLE_PERSON_FIELDS
from gbridge.google.models import GoogleContact
from gbridge.utils.backoff import retry_on_api_error

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)


class SyncResult(NamedTuple):
    """Result of a People API sync operation."""

    items: list[GoogleContact]
    sync_token: str | None
    deleted_resource_names: list[str]


class PeopleService:
    """Read-only wrapper around the Google People API."""

    def __init__(self, credentials: Credentials) -> None:
        self._service = build(
            "people", PEOPLE_API_VERSION, credentials=credentials, cache_discovery=False
        )

    def fetch_all(self, sync_token: str | None = None) -> SyncResult:
        """Fetch contacts — full or delta depending on sync_token.

        Returns a SyncResult with contacts, a new sync token, and
        a list of deleted resource names (delta only).
        """
        try:
            return self._fetch(sync_token=sync_token)
        except HttpError as exc:
            if exc.resp.status == 410:
                logger.warning("Sync token expired (410 GONE), performing full sync")
                return self._fetch(sync_token=None)
            raise

    @retry_on_api_error()
    def _fetch_page(
        self,
        sync_token: str | None,
        page_token: str | None,
    ) -> dict:
        """Fetch a single page from the People API connections list."""
        kwargs: dict[str, object] = {
            "resourceName": "people/me",
            "personFields": PEOPLE_PERSON_FIELDS,
            "pageSize": DEFAULT_PAGE_SIZE,
            "requestSyncToken": True,
        }
        if sync_token:
            kwargs["syncToken"] = sync_token
        if page_token:
            kwargs["pageToken"] = page_token

        return self._service.people().connections().list(**kwargs).execute()  # type: ignore[no-any-return]

    def _fetch(self, sync_token: str | None) -> SyncResult:
        contacts: list[GoogleContact] = []
        deleted: list[str] = []
        page_token: str | None = None
        new_sync_token: str | None = None

        while True:
            response = self._fetch_page(sync_token, page_token)

            for person in response.get("connections", []):
                # Deleted contacts appear in delta syncs with metadata.deleted=True
                metadata = person.get("metadata", {})
                if metadata.get("deleted"):
                    rn = person.get("resourceName", "")
                    if rn:
                        deleted.append(rn)
                    continue

                contacts.append(self._parse_person(person))

            new_sync_token = response.get("nextSyncToken")
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            "People API: fetched %d contacts, %d deletions (delta=%s)",
            len(contacts),
            len(deleted),
            sync_token is not None,
        )
        return SyncResult(
            items=contacts,
            sync_token=new_sync_token,
            deleted_resource_names=deleted,
        )

    @staticmethod
    def _parse_person(person: dict) -> GoogleContact:
        """Parse a People API person resource into a GoogleContact."""
        names = person.get("names", [{}])
        primary_name = names[0] if names else {}

        emails = tuple(
            sorted(e.get("value", "") for e in person.get("emailAddresses", []) if e.get("value"))
        )
        phones = tuple(
            sorted(p.get("value", "") for p in person.get("phoneNumbers", []) if p.get("value"))
        )

        orgs = person.get("organizations", [{}])
        primary_org = orgs[0] if orgs else {}

        bios = person.get("biographies", [{}])
        primary_bio = bios[0] if bios else {}

        return GoogleContact(
            resource_name=person.get("resourceName", ""),
            etag=person.get("etag", ""),
            display_name=primary_name.get("displayName", ""),
            given_name=primary_name.get("givenName", ""),
            family_name=primary_name.get("familyName", ""),
            emails=emails,
            phones=phones,
            organization=primary_org.get("name", ""),
            title=primary_org.get("title", ""),
            notes=primary_bio.get("value", ""),
            raw=person,
        )
