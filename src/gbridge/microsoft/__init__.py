"""Microsoft Graph integration for GBridge Phase 2.

Mirror of `gbridge.google` but for the Outlook write-back path:
- auth.py      : MSAL public-client authentication, keychain token cache.
- models.py    : frozen dataclasses matching Graph resource shapes.
- mapping.py   : pure functions mapping Google <-> Microsoft payloads.
- graph_*.py   : thin REST wrappers over Graph endpoints.

Unlike the Google side (which is READ-ONLY by policy), this package holds the
Graph credentials required to WRITE contacts / events / tasks in Outlook.
Google remains the source of truth — Microsoft Graph is a sink for the
ledger state.
"""

from __future__ import annotations
