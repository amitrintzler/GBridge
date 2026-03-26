"""SHA-256 content hashing for sync diff detection.

Produces a deterministic hex digest from the sync-relevant fields of a
Google resource.  Two items with the same hash have identical content —
no sync action needed.  This avoids unnecessary writes and protects
user data from accidental overwrites.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gbridge.google.models import GoogleContact, GoogleEvent, GoogleTask


def content_hash(obj: GoogleContact | GoogleEvent | GoogleTask) -> str:
    """Compute a deterministic SHA-256 hex digest of sync-relevant fields.

    The hash is computed from a canonical JSON string with sorted keys
    and compact separators, ensuring the same logical content always
    produces the same hash regardless of dict ordering.
    """
    data = obj.to_hash_dict()
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
