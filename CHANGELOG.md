# Changelog

All notable changes to GBridge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-03

Post-0.1.0 correctness fixes and features. Ledger schema is unchanged (v3),
so upgrading in place is safe.

### Fixed

- **Conflict resolution now actually takes effect.** Previously the pusher
  never consulted the `winner` column: a resolved conflict did nothing, and
  the next push's 412 re-detection reset `winner` back to NULL — trapping the
  user in a loop. The pusher now checks the conflict table before every
  write: unresolved conflicts are skipped (no re-attempt, no reset);
  `winner=google` force-overwrites Outlook without the stale `If-Match`;
  `winner=outlook` fetches Outlook's current etag (new per-service
  `get_one()`) and advances the ledger baseline so syncing stops nagging
  until Google changes again. Resolved rows are cleared after action.
- **Monthly/yearly "Nth weekday" recurrence no longer corrupts dates.**
  `FREQ=MONTHLY;BYDAY=3TU` ("3rd Tuesday") previously collapsed silently to
  "the 1st of the month". It now maps to Graph `relativeMonthly` /
  `relativeYearly` with the correct `daysOfWeek` + `index`, supporting
  ordinal-prefixed BYDAY (`3TU`, `-1FR`) and `BYSETPOS`. Clauses with no
  Graph equivalent (BYYEARDAY, BYWEEKNO, EXDATE, RDATE) are now logged
  instead of silently dropped.
- **`gbridge outlook push` works standalone.** It now refreshes from Google
  first so the push operates on live models — previously a direct
  `outlook push` in graph mode marked every item failed because it had no
  source data. Dry-run still classifies from the ledger alone.

### Added

- **Calendar / task-list selection from the CLI.** `gbridge calendars` and
  `gbridge tasklists` list your Google calendars/lists and mark which are
  synced; `--select id1,id2` limits the sync, `--all` clears the filter.
- **Sync/push progress indicators.** `SyncEngine.run_sync()` and
  `Pusher.run_push()` accept an optional `progress_cb(phase, done, total)`;
  `gbridge sync` and `gbridge outlook push` print per-phase progress.
- **macOS `.dmg` always produced.** `installer/macos/build.sh` packages a
  `.dmg` via `hdiutil` (no Homebrew needed); the release CI now ships
  `gbridge-macos.dmg`.
- **Windows installer in CI.** The release workflow builds the NSIS
  `GBridge-Setup.exe` (best-effort) alongside the raw `gbridge-windows.exe`.

### Changed

- **mypy tightened.** Removed the blanket `--ignore-missing-imports` from CI;
  stub-less third-party libs are scoped in `[[tool.mypy.overrides]]`, so a
  missing first-party import is now a hard error.

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
