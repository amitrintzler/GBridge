# GBridge Backlog

## Phase 1 — DONE (this session)
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
- [x] PyInstaller Linux binary build verified (28MB, all commands work)

## Phase 2 — Outlook Write-Back
- [ ] Microsoft Graph API integration (M365 path)
  - [ ] Microsoft MSAL authentication (OAuth 2.0)
  - [ ] Graph API contacts write (create/update/delete)
  - [ ] Graph API calendar events write
  - [ ] Graph API tasks write
- [ ] Embedded Radicale DAV server (standalone Outlook path)
  - [ ] Radicale server on localhost:8765
  - [ ] CardDAV endpoint for contacts
  - [ ] CalDAV endpoint for calendar + tasks
  - [ ] Outlook configuration guide for connecting to DAV
- [ ] Two-way sync conflict resolution
- [ ] Deletion propagation (Google → Outlook)

## Phase 3 — Background Service & UI
- [ ] APScheduler integration (auto-sync every N minutes)
- [ ] System tray icon (pystray)
- [ ] Desktop notifications (plyer toasts)
- [ ] Tkinter setup wizard (GUI replacement for CLI wizard)
- [ ] Service installation:
  - [ ] Windows: NSSM service
  - [ ] macOS: launchd plist
  - [ ] Linux: systemd unit

## Phase 4 — Packaging & Distribution
- [ ] Test Windows .exe build on actual Windows machine
- [ ] Test macOS build on actual macOS machine
- [ ] Test NSIS installer (install/uninstall/shortcuts)
- [ ] Test macOS .dmg creation
- [ ] Test Linux .deb/.rpm packages
- [ ] Create first GitHub Release (tag v0.1.0)
- [ ] Verify GitHub Actions build-installers workflow
- [ ] Verify security workflow runs on GitHub
- [ ] Verify Mermaid diagrams render on GitHub

## Phase 5 — Production Hardening
- [ ] End-to-end test with real Google account
- [ ] End-to-end test with real Outlook (M365)
- [ ] End-to-end test with real Outlook (standalone)
- [ ] Rate limit handling for large accounts (10K+ contacts)
- [ ] Recurring event expansion / handling
- [ ] Multi-calendar selection UI
- [ ] Multi-tasklist selection UI
- [ ] Sync progress indicators (progress bar)
- [ ] Error recovery (partial sync resume)

## Known Gaps / Technical Debt
- [ ] mypy strict mode (currently uses --ignore-missing-imports)
- [ ] Test coverage report (pytest-cov configured but not enforced)
- [ ] Integration tests (mock Google API server)
- [ ] Windows registry detection not tested on real Windows
- [ ] macOS plist detection not tested on real macOS
- [ ] `gbridge.spec` icon file (currently None)
- [ ] CHANGELOG.md for release notes
