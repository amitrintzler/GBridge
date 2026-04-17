"""Local DAV server for standalone-Outlook push.

When `Settings.outlook_mode == 'dav'`, the daemon spawns a Radicale
subprocess bound to 127.0.0.1 only, and the pusher projects the ledger
into a collection tree Radicale serves over CardDAV + CalDAV.

The third-party Outlook CalDav Synchronizer addin (shipped in the Windows
installer) then reads the local DAV URL and pushes events / contacts /
tasks into the user's classic Outlook profile.
"""

from __future__ import annotations
