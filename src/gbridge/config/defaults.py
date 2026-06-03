"""Default configuration values for GBridge."""

from __future__ import annotations

APP_NAME = "GBridge"
APP_VERSION = "0.2.1"

DEFAULT_SYNC_INTERVAL_MINUTES = 15
DEFAULT_DB_NAME = "gbridge_sync.db"

# Google API scopes — READ-ONLY to guarantee zero impact on user data.
GOOGLE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]

# Google API service versions
PEOPLE_API_VERSION = "v1"
CALENDAR_API_VERSION = "v3"
TASKS_API_VERSION = "v1"

# People API field mask — only fields we need for sync
PEOPLE_PERSON_FIELDS = (
    "names,emailAddresses,phoneNumbers,organizations,biographies,metadata"
)

# Pagination limits
DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 1000

# Keyring service name for credential storage
KEYRING_SERVICE = "gbridge"
KEYRING_GOOGLE_TOKEN_KEY = "google_credentials"
KEYRING_MICROSOFT_TOKEN_KEY = "microsoft_credentials"

# Microsoft Graph / MSAL
# The default public-client id is intentionally None — a future release may
# ship a registered GBridge Azure app and flip this to a real GUID, which
# switches first-run MS auth to zero-config for end users. Until then, users
# provide their own via Settings.microsoft_client_id.
MICROSOFT_PUBLIC_CLIENT_ID: str | None = None
MICROSOFT_DEFAULT_TENANT = "common"  # personal + work/school accounts
MICROSOFT_AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}"
MICROSOFT_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MICROSOFT_SCOPES: list[str] = [
    "Contacts.ReadWrite",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
]

# Outlook integration mode — 'disabled' | 'graph' (M365) | 'dav' (standalone).
DEFAULT_OUTLOOK_MODE = "disabled"
DEFAULT_PUSH_INTERVAL_MINUTES = 15

# Localhost-only DAV server (for standalone Outlook path B)
DAV_HOST = "127.0.0.1"
DAV_PORT = 8765

# Retry / backoff
MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 1.0
