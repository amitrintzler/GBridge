# GBridge Backlog

## Phase 1 — DONE
- [x] Project scaffold (pyproject.toml, src/gbridge layout, CI)
- [x] Google OAuth 2.0 PKCE auth with OS keychain storage
- [x] Google People API (contacts, syncToken delta sync)
- [x] Google Calendar API (events, incremental sync)
- [x] Google Tasks API (tasks, updatedMin delta)
- [x] SQLite sync ledger (schema, migrations, CRUD)
- [x] SHA-256 diff engine (deterministic hashing)
- [x] Outlook auto-detection (M365 vs standalone vs not found)
- [x] Sync engine skeleton (fetch → hash → diff → ledger)
- [x] CLI with subcommands (setup, sync, status, auth, version)
- [x] Interactive setup wizard with ASCII visual guide
- [x] Standalone installer infrastructure (PyInstaller + NSIS + macOS + Linux)
- [x] Security scanning CI (pip-audit, Bandit, CodeQL, SBOM)
- [x] Trust badges, SECURITY.md, sourced evidence in README
- [x] Colored Mermaid diagrams in README
- [x] 66 unit tests, all passing
- [x] PyInstaller Linux binary build verified

## Phase 2 — Outlook Write-Back — DONE
- [x] Ledger v1 → v2 migration (outlook_hash / etag / last_pushed / tombstone, conflicts table)
- [x] Microsoft MSAL authentication (public client + keyring cache + device-code fallback)
- [x] Microsoft models + Google↔MS mapping with hash-stability
- [x] Graph API HTTP helper (429 Retry-After, 410 delta expired, 412 precondition)
- [x] Graph contacts read + write (`/me/contacts/delta` + CRUD)
- [x] Graph calendar events read + write (`/me/calendars/{id}/events/delta` + CRUD)
- [x] Graph To Do tasks read + write (`/me/todo/lists/{id}/tasks` + CRUD)
- [x] Pusher engine with dry / graph / dav modes
- [x] Conflict detection via If-Match / 412 → `conflicts` table entry
- [x] Embedded Radicale DAV server (subprocess supervisor + health probe + pidfile)
- [x] DAV storage projector — ledger → .vcf / .ics files
- [x] Outlook CalDav Synchronizer (OCS) per-profile XML config writer
- [x] NSIS installer bundles OCS MSI (optional — `installer/windows/vendor/OutlookCalDavSynchronizer.msi`)
- [x] Manual conflict resolution — tray menu, Tk dialog, CLI

## Phase 3 — Background Service & UI — DONE
- [x] APScheduler integration (auto-sync + auto-push every N minutes)
- [x] System tray icon (pystray, lazy-imported) — adds Push / Resolve conflicts items
- [x] Desktop notifications (plyer toasts) for both sync and push
- [x] Tkinter setup wizard — now includes optional Microsoft sign-in step
- [x] Tkinter conflicts dialog
- [x] Daemon orchestrator — dual-job scheduler + Radicale lifecycle
- [x] Auto-start installation:
  - [x] Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  - [x] macOS: ~/Library/LaunchAgents/io.gbridge.autosync.plist
  - [x] Linux: ~/.config/systemd/user/gbridge.service
- [x] CLI wiring: `gbridge daemon`, `gbridge autostart`, `gbridge gui`,
      `gbridge setup --gui`, `gbridge outlook {auth,push,status}`,
      `gbridge conflicts {list,resolve}`

## Phase 4 — Packaging & Distribution (remaining)
- [ ] Test Windows .exe build on actual Windows machine (user task)
- [ ] Test macOS build on actual macOS machine
- [ ] Test NSIS installer (install/uninstall/shortcuts) end-to-end
- [ ] Test macOS .dmg creation
- [ ] Test Linux .deb/.rpm packages
- [ ] Create first GitHub Release (tag v0.1.0)
- [ ] Verify GitHub Actions build-installers workflow
- [ ] Verify security workflow runs on GitHub
- [ ] Verify Mermaid diagrams render on GitHub
- [ ] Windows code signing (Authenticode) — avoid SmartScreen warnings

## Phase 5 — Production Hardening (remaining)
- [ ] End-to-end test with real Google account (user task)
- [ ] End-to-end test with real Outlook (M365)
- [ ] End-to-end test with real Outlook (standalone + OCS)
- [x] Rate limit handling — `Retry-After` honored on Google and Graph
- [x] Recurring-event RRULE → Graph recurrence object (DAILY/WEEKLY/MONTHLY/
      YEARLY with INTERVAL/COUNT/UNTIL/BYDAY/BYMONTHDAY). Rare clauses
      (BYSETPOS, EXDATE, BYYEARDAY) remain best-effort.
- [x] Graph-side deletion propagation (schema v3 `pending_deletions` queue)
- [x] Partial-sync resume — `sync_phase` checkpoint in `sync_state` warns on next run
- [x] Multi-calendar / multi-tasklist selection (settings fields honored by engine)

## Shipped Microsoft client_id note
The default `MICROSOFT_PUBLIC_CLIENT_ID` in `src/gbridge/config/defaults.py`
is intentionally `None` in v0.1.0. End users must register their own Azure
desktop app (free — one-time) and run:

    gbridge outlook auth --client-id <THEIR_GUID>

Flipping that constant to a registered GBridge-owned app is a future
release task.

## Known Gaps / Technical Debt (remaining)
- [ ] mypy strict mode — kept at `--ignore-missing-imports` for now due to
      vobject / radicale / msal stub coverage. Can tighten per-package once
      upstream stubs mature.
- [x] Test coverage — 80% floor enforced via
      `pytest --cov=src/gbridge --cov-fail-under=80` (see pyproject notes)
- [ ] Integration tests with a mocked Google API server (unit tests use
      response fixtures only; Graph side has real cassettes via `responses`)
- [ ] Windows registry autostart not tested on real Windows (user task)
- [ ] macOS plist autostart not tested on real macOS (user task)
- [x] `gbridge.spec` icon — done (`installer/windows/gbridge.ico`)
- [x] CHANGELOG.md — done (v0.1.0 entry)
