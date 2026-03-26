# GBridge

**Sync your Google Contacts, Calendar, and Tasks with Microsoft Outlook.**

GBridge is a free, open-source tool that keeps your Google and Outlook data in sync — automatically, securely, and without touching your existing data.

Created by **Amit Rintzler**.

## Key Features

- **Contacts** — Google People API with delta sync (only changed contacts)
- **Calendar** — Google Calendar API with incremental sync tokens
- **Tasks** — Google Tasks API with timestamp-based delta sync
- **Two sync paths** — works with Microsoft 365 (cloud) *and* standalone classic Outlook
- **Auto-detection** — GBridge silently figures out which Outlook you have
- **Cross-platform** — Windows, macOS, and Linux
- **Safe by design** — read-only Google scopes, SHA-256 diff engine, no fuzzy matching

## Safety Guarantees

GBridge is built with a **zero-risk** philosophy:

1. **Read-only Google access** — GBridge uses `readonly` API scopes. It *cannot* modify, delete, or corrupt your Google data. Ever.
2. **No fuzzy matching** — items are tracked by their unique Google IDs (resource_name, event ID, task ID). No guessing, no accidental merges.
3. **SHA-256 diff engine** — only items whose content has actually changed are synced. If nothing changed, nothing happens.
4. **Local-only state** — all sync state lives in a local SQLite database on your machine. Nothing is sent to third-party servers.
5. **Secure token storage** — OAuth tokens are stored in your OS keychain (Windows Credential Locker, macOS Keychain, Linux Secret Service) — never in plain-text files.
6. **Atomic config writes** — configuration files are written atomically with restricted permissions (owner-only).

---

## Quick Start — One Command Setup

After installing, run this single command. It walks you through everything:

```
gbridge setup
```

The wizard will:
1. Check your Python version
2. Open Google Cloud Console in your browser
3. Guide you through creating API credentials (with visual instructions)
4. Authenticate your Google account
5. Run your first sync

**That's it. One command.**

---

## Detailed Setup Guide

If you prefer to set things up manually, follow these steps:

### Step 1: Install Python

You need Python 3.11 or newer. Check if you already have it:

```
python3 --version
```

You should see something like `Python 3.12.x`. If not, install it:

- **Windows:** Download from [python.org](https://www.python.org/downloads/). Check "Add to PATH" during install.
- **macOS:** `brew install python@3.12`
- **Linux:** `sudo apt install python3.12` (Ubuntu/Debian) or `sudo dnf install python3.12` (Fedora)

### Step 2: Install GBridge

```
pip install git+https://github.com/amitrintzler/GBridge.git
```

To verify it installed correctly, run:

```
gbridge --version
```

You should see:

```
GBridge v0.1.0
Python 3.12.x on Linux
```

### Step 3: Run the Setup Wizard

```
gbridge setup
```

The wizard opens your browser and prints step-by-step visual instructions. Here's what you'll see:

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

If the credentials file isn't set up yet, the wizard shows you exactly what to do:

### Visual Guide: Google Cloud Console Setup

The wizard displays these visual guides in your terminal:

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

After you download and place the file, press ENTER. The wizard continues:

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

### Step 4: Check Status Anytime

```
gbridge status
```

Shows what's currently in the local sync ledger:

```
GBridge v0.1.0 — Status

  Contacts in ledger:  342
  Events in ledger:    128
  Tasks in ledger:      15

  Last synced: 2026-03-26T18:30:00+00:00

  Database: /home/you/.config/gbridge/gbridge_sync.db
  Config:   /home/you/.config/gbridge/client_secret.json
```

---

## CLI Commands

| Command | What it does |
|---|---|
| `gbridge setup` | **One-click setup wizard (start here!)** |
| `gbridge` or `gbridge sync` | Run a sync cycle |
| `gbridge status` | Show sync status and item counts |
| `gbridge auth` | Re-authenticate with Google |
| `gbridge --version` | Show version info |

## Where Is My Data?

| What | Location |
|---|---|
| Config file | Windows: `%APPDATA%\GBridge\config.json` / macOS: `~/Library/Application Support/GBridge/config.json` / Linux: `~/.config/gbridge/config.json` |
| Sync database | Same folder as config, named `gbridge_sync.db` |
| Credentials | Stored in your OS keychain (not a file) |
| Logs | Same folder, under `logs/gbridge.log` |

Run `gbridge status` to see the exact paths on your system.

## Troubleshooting

**"GBridge needs a Google API credentials file"**
Run `gbridge setup` — it will guide you through creating one. Or follow the visual guide above.

**"Authentication failed"**
Run `gbridge auth` to re-authenticate. Make sure you enabled all 3 APIs (People, Calendar, Tasks) in the Google Cloud Console.

**"Token refresh failed"**
Your saved token expired. Run `gbridge auth` to sign in again.

**Browser doesn't open automatically?**
Copy the URL from the terminal and paste it into your browser manually.

**Don't know where to put `client_secret.json`?**
Run `gbridge setup` or `gbridge sync` — both will print the exact path.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone https://github.com/amitrintzler/GBridge.git
cd GBridge
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
```

### Lint & Type Check

```bash
ruff check src/ tests/
mypy src/gbridge/ --ignore-missing-imports
```

## Project Structure

```
src/gbridge/
  __main__.py          # CLI entry point (setup, sync, status, auth, version)
  core/
    engine.py          # Sync orchestrator: fetch -> diff -> ledger
    ledger.py          # SQLite sync state tracking
    hasher.py          # SHA-256 content fingerprinting
  google/
    auth.py            # OAuth 2.0 with OS keychain storage
    people.py          # Contacts API (People API v1)
    calendar.py        # Calendar API v3
    tasks.py           # Tasks API v1
    models.py          # Immutable data models
  outlook/
    detect.py          # M365 vs standalone auto-detection
  config/
    settings.py        # JSON config management
    defaults.py        # Default values and constants
  utils/
    logger.py          # Rotating file logger
    backoff.py         # Exponential retry for API calls
```

## How It Works

```
Google Account                    GBridge                         Outlook
  (read-only)               (local on your machine)

  Contacts  ------>  Fetch via People API  ------>  (Phase 2)
  Calendar  ------>  Fetch via Calendar API ----->  (Phase 2)
  Tasks     ------>  Fetch via Tasks API   ------>  (Phase 2)
                          |
                     SHA-256 diff
                          |
                     SQLite ledger
                  (tracks what changed)
```

**Phase 1** (current): Fetches from Google, computes diffs, tracks state locally.
**Phase 2** (next): Writes changes to Outlook via Microsoft Graph API or local DAV server.

## License

MIT License. See [LICENSE](LICENSE) for details.
