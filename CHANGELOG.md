# Changelog

All notable changes to GBridge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-17

Initial release. Phase 1 (Google read) + Phase 2 (Outlook write) + Phase 3
(daemon / tray / wizard / autostart) all landed in the same cut.

### Added (gap-close pass)

- **Google→Outlook deletion propagation** — when Google drops an item we
  enqueue the outlook_id in the `pending_deletions` table (schema v3) and
  the next push cycle issues the corresponding Graph DELETE (or DAV tree
  rewrite) before forgetting about it. (BACKLOG: "Deletion propagation".)
- **Recurring event mapping** — `RRULE → Graph recurrence object` now
  supports DAILY/WEEKLY/MONTHLY/YEARLY with INTERVAL, COUNT, UNTIL,
  BYDAY, and BYMONTHDAY. Unsupported clauses are ignored (best-effort).

### Added

- **Google read-only sync** — Contacts (People API), Calendar, Tasks, all
  under `*.readonly` scopes; cannot modify the user's Google data.
- **SQLite ledger** with WAL mode and version-tracked migrations (v1 → v2).
- **SHA-256 content hashing** so only real changes trigger updates.
- **OS-keychain token storage** via `keyring` — Windows Credential Locker,
  macOS Keychain, Linux Secret Service.
- **Phase 2 Outlook write-back**:
  - Microsoft Graph (M365) path: MSAL public-client auth, `/me/contacts`,
    `/me/calendars/{id}/events`, `/me/todo/lists/{id}/tasks` with delta
    sync + If-Match / 412 conflict detection.
  - Standalone Outlook path: embedded Radicale subprocess + ledger-to-DAV
    projector writing .vcf / .ics files into `%LOCALAPPDATA%\gbridge\dav\`.
  - Outlook CalDav Synchronizer addin bundled in the Windows installer
    (silent MSI install + per-profile `options_<profile>.xml` seed).
- **Manual conflict resolution UX** — `conflicts` table, tray menu item
  "Resolve conflicts (N)", Tk dialog, CLI (`gbridge conflicts list` /
  `gbridge conflicts resolve <id> --winner {google|outlook}`).
- **Background service (Phase 3)**: APScheduler-backed sync + push jobs,
  pystray tray icon with "Sync now" / "Push to Outlook" / "Show status",
  plyer toast notifications, OS-level autostart helpers.
- **Standalone installers** for Windows (NSIS), macOS, Linux via
  PyInstaller.
- **Security CI**: Ruff + Bandit + pip-audit + CodeQL + SBOM on every
  commit, weekly vulnerability scans.
- **Partial-sync resume hint** — the engine checkpoints `sync_phase` so a
  crash mid-cycle is logged on next start.
- **Retry-After honored** on Google 429 / 503 responses.
- **Multi-calendar / multi-tasklist filtering** via
  `Settings.enabled_calendars` / `enabled_tasklists`.

### Known limitations (to be addressed in future releases)

- **Microsoft public client_id** is not yet shipped; end users must
  register their own Azure app and run `gbridge outlook auth --client-id
  <GUID>`. See README for the 3-step setup.
- **Task sub-task hierarchy** is not synced — Microsoft To Do has no
  parent/child concept. Google Tasks subtasks land as siblings in Outlook.
- **Recurring events**: common RRULE cases (DAILY / WEEKLY / MONTHLY /
  YEARLY with INTERVAL / COUNT / UNTIL / BYDAY / BYMONTHDAY) round-trip
  cleanly in v0.1.0. Rarer clauses like BYSETPOS, BYYEARDAY, EXDATE lists,
  and multi-RRULE stacks are ignored on the Graph side (preserved
  byte-for-byte on the DAV side).
- **Graph To Do statuses** `inProgress | waitingOnOthers | deferred` all
  collapse to Google's `needsAction` on reverse mapping.
- **DAV path conflict detection** is delegated to the Outlook CalDav
  Synchronizer addin — GBridge just rewrites the authoritative DAV state.
- **Windows code signing** is not yet set up; users may see SmartScreen
  warnings on first install.

### Tested

269 unit tests, 80% line coverage, Ruff + Bandit clean. Covering:
ledger migrations (v1→v2→v3), conflicts CRUD, deletion queue,
sync engine orchestration + multi-calendar filtering + partial-sync
checkpoint, MSAL auth (interactive + device-code fallback), Google ↔
Microsoft model mapping, recurrence RRULE → Graph object, Graph HTTP
helper (retries / Retry-After / 410 / 412), Graph read + write + delete
clients, pusher (dry / graph / DAV), Radicale subprocess supervisor,
DAV storage projector, OCS config XML, CLI subcommands, daemon lifecycle,
tray menu composition (incl. conflicts), backoff retry / Retry-After.

[0.1.0]: https://github.com/amitrintzler/GBridge/releases/tag/v0.1.0
