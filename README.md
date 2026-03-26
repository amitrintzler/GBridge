# GBridge

[![CI](https://github.com/amitrintzler/GBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/amitrintzler/GBridge/actions/workflows/ci.yml)
[![Security](https://github.com/amitrintzler/GBridge/actions/workflows/security.yml/badge.svg)](https://github.com/amitrintzler/GBridge/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/amitrintzler/GBridge/blob/main/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Google Scopes: Read-Only](https://img.shields.io/badge/Google_Scopes-Read--Only-brightgreen.svg)](#safety-guarantees)
[![No Telemetry](https://img.shields.io/badge/Telemetry-None-brightgreen.svg)](https://github.com/amitrintzler/GBridge/blob/main/SECURITY.md)
[![Open Source](https://img.shields.io/badge/Open_Source-100%25-brightgreen.svg)](https://github.com/amitrintzler/GBridge)

**Sync your Google Contacts, Calendar, and Tasks with Microsoft Outlook.**

GBridge is a free, open-source tool that keeps your Google and Outlook data in sync — automatically, securely, and without touching your existing data.

Created by **Amit Rintzler**.

---

## Download & Install (No Technical Knowledge Needed)

### Windows

1. Download **`gbridge-windows.exe`** from the [Releases page](https://github.com/amitrintzler/GBridge/releases/latest)
2. Double-click the downloaded file
3. The setup wizard opens and walks you through everything

**That's it. No Python, no terminal, no technical steps.**

### macOS

1. Download **`gbridge-macos`** from the [Releases page](https://github.com/amitrintzler/GBridge/releases/latest)
2. Open Terminal (search "Terminal" in Spotlight)
3. Run: `chmod +x ~/Downloads/gbridge-macos && ~/Downloads/gbridge-macos setup`

### Linux

1. Download **`gbridge-linux`** from the [Releases page](https://github.com/amitrintzler/GBridge/releases/latest)
2. Open Terminal
3. Run: `chmod +x ~/Downloads/gbridge-linux && ~/Downloads/gbridge-linux setup`

---

## What Happens When You Run It

The setup wizard guides you through everything step by step:

```
GBridge v0.1.0 — Setup Wizard

========================================================
  Welcome! This wizard will set up GBridge for you.
  It takes about 5 minutes, and you only do it once.
========================================================

[Step 1/5] Checking Python version...
  Python 3.12.0 — OK

[Step 2/5] Google API credentials
```

If you haven't set up Google credentials yet, it shows you exactly what to click:

```
  +----------------------------------------------------------+
  |  STEP A: Create a Google Cloud Project                   |
  +----------------------------------------------------------+
  |                                                          |
  |  1. Go to: https://console.cloud.google.com              |
  |                                                          |
  |  2. Click the project dropdown at the top:               |
  |     +---------------------------------------------+      |
  |     | [v] Select a project          [NEW PROJECT] |      |
  |     +---------------------------------------------+      |
  |                                        ^^^^^^^^^^^       |
  |                                    Click "NEW PROJECT"   |
  |                                                          |
  |  3. Name it "GBridge" and click CREATE                   |
  +----------------------------------------------------------+

  +----------------------------------------------------------+
  |  STEP B: Enable the 3 APIs                               |
  +----------------------------------------------------------+
  |                                                          |
  |  In the search bar at the top, search for each API       |
  |  and click ENABLE:                                       |
  |                                                          |
  |  +----------------------------------------------------+  |
  |  | [Search] People API                                |  |
  |  +----------------------------------------------------+  |
  |     -> Click the result -> Click [ENABLE]                |
  |                                                          |
  |  Repeat for:                                             |
  |     [x] People API                                       |
  |     [x] Google Calendar API                              |
  |     [x] Tasks API                                        |
  +----------------------------------------------------------+

  +----------------------------------------------------------+
  |  STEP C: Create OAuth Credentials                        |
  +----------------------------------------------------------+
  |                                                          |
  |  1. In the left sidebar, click:                          |
  |     APIs & Services > Credentials                        |
  |                                                          |
  |  2. Click:  [+ CREATE CREDENTIALS]                       |
  |             > OAuth client ID                            |
  |                                                          |
  |  3. If asked for consent screen:                         |
  |     - Choose "External"                                  |
  |     - App name: "GBridge"                                |
  |     - Fill your email, click Save                        |
  |                                                          |
  |  4. Application type: [Desktop application]              |
  |     Name: "GBridge"                                      |
  |     Click [CREATE]                                       |
  |                                                          |
  |  5. On the popup, click:                                 |
  |     +----------------------------------+                 |
  |     |  [DOWNLOAD JSON]                 |                 |
  |     +----------------------------------+                 |
  |                                                          |
  |  6. Rename the downloaded file to:                       |
  |     client_secret.json                                   |
  +----------------------------------------------------------+
```

After you place the file and press ENTER, it finishes automatically:

```
[Step 3/5] Signing in to Google...
  Your browser will open. Sign in and click 'Allow'.
  Authenticated — OK

[Step 4/5] Running your first sync...
  Contacts       342 items synced
  Events         128 items synced
  Tasks           15 items synced

[Step 5/5] Outlook detection...
  No Outlook detected — Outlook sync coming in Phase 2

========================================================
  Setup complete! GBridge is ready.
========================================================

  What you can do now:

    gbridge          Run a sync (fetches latest from Google)
    gbridge status   See what's in your local sync ledger
    gbridge auth     Re-authenticate if needed

  Your Google data was NOT modified. GBridge only reads.
```

---

## Key Features

- **Contacts** — syncs all your Google contacts
- **Calendar** — syncs all your Google calendar events
- **Tasks** — syncs all your Google tasks
- **Works with any Outlook** — Microsoft 365 (cloud) and standalone classic Outlook
- **Auto-detection** — GBridge figures out which Outlook you have automatically
- **Windows, macOS, and Linux**

## Safety Guarantees

GBridge is built with a **zero-risk** philosophy:

1. **Read-only** — GBridge *cannot* modify, delete, or corrupt your Google data. It only reads.
2. **No guessing** — items are tracked by unique IDs. No accidental merges.
3. **Smart sync** — only items that actually changed are synced.
4. **Local-only** — all data stays on your computer. Nothing goes to third-party servers.
5. **Secure storage** — login tokens are stored in your OS keychain (Windows Credential Locker / macOS Keychain / Linux Secret Service).

## Commands

| Command | What it does |
|---|---|
| `gbridge setup` | **First-time setup wizard (start here)** |
| `gbridge` | Run a sync |
| `gbridge status` | Check what's synced |
| `gbridge auth` | Sign in to Google again |
| `gbridge --version` | Show version |

## Where Is My Data?

| What | Windows | macOS | Linux |
|---|---|---|---|
| Config | `%APPDATA%\GBridge\` | `~/Library/Application Support/GBridge/` | `~/.config/gbridge/` |
| Sync database | Same folder | Same folder | Same folder |
| Login tokens | Windows Credential Locker | macOS Keychain | Secret Service |
| Logs | Same folder, `logs/` | Same folder, `logs/` | Same folder, `logs/` |

## Troubleshooting

**The setup wizard says it can't find `client_secret.json`**
Follow the visual guide in the wizard. It tells you exactly where to put the file.

**Browser doesn't open?**
Copy the URL from the terminal and paste it into your browser.

**"Authentication failed"?**
Run `gbridge auth` to sign in again. Make sure you enabled all 3 APIs in Google Cloud Console.

**Want to start over?**
Run `gbridge auth` to re-authenticate, or delete the config folder (see "Where Is My Data?" above).

---

## For Developers

### Install from source

```bash
git clone https://github.com/amitrintzler/GBridge.git
cd GBridge
pip install -e ".[dev]"
```

### Run tests

```bash
pytest tests/ -v
ruff check src/ tests/
```

### Build installers

```bash
# Windows (run on Windows)
installer\windows\build.bat

# macOS (run on macOS)
bash installer/macos/build.sh

# Linux (run on Linux)
bash installer/linux/build.sh
```

### Project Structure

```
src/gbridge/
  __main__.py          # CLI (setup wizard, sync, status, auth)
  core/
    engine.py          # Sync orchestrator
    ledger.py          # SQLite sync state
    hasher.py          # SHA-256 content fingerprinting
  google/
    auth.py            # OAuth 2.0 + OS keychain
    people.py          # Contacts API
    calendar.py        # Calendar API
    tasks.py           # Tasks API
    models.py          # Data models
  outlook/
    detect.py          # M365 vs standalone detection
  config/
    settings.py        # JSON config
    defaults.py        # Constants
  utils/
    logger.py          # Rotating file logger
    backoff.py         # API retry logic
installer/
  windows/             # NSIS installer + build script
  macos/               # .app bundle + build script
  linux/               # .deb/.rpm + build script
```

## License

MIT License. See [LICENSE](LICENSE) for details.
