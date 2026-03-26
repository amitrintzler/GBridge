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

## Quick Start (5 minutes)

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

### Step 3: Set Up Google API Credentials (one-time)

GBridge needs permission to read your Google data. This takes about 3 minutes:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** > **New Project** > name it "GBridge" > **Create**
3. In the search bar, search for and enable each of these APIs:
   - **People API**
   - **Google Calendar API**
   - **Tasks API**
4. Go to **APIs & Services** > **Credentials**
5. Click **Create Credentials** > **OAuth 2.0 Client ID**
   - If asked to configure a consent screen, choose **External**, fill in the app name ("GBridge"), and save
6. For Application type, choose **Desktop application**
7. Click **Create**, then **Download JSON**
8. Rename the downloaded file to `client_secret.json`
9. Move it to your GBridge config folder:

| OS | Location |
|---|---|
| Windows | `%APPDATA%\GBridge\client_secret.json` |
| macOS | `~/Library/Application Support/GBridge/client_secret.json` |
| Linux | `~/.config/gbridge/client_secret.json` |

**Don't know where to put it?** Just run `gbridge` — it will tell you the exact path.

### Step 4: Run Your First Sync

```
gbridge
```

**What happens:**

1. Your browser opens to a Google sign-in page
2. Sign in and click "Allow" (GBridge only requests read-only access)
3. The browser shows "Authentication successful" — you can close it
4. Back in the terminal, you'll see:

```
GBridge v0.1.0

Connecting to Google...
Authenticated with Google.

Syncing...

Sync complete:
  Contacts       342 found  (342 new, 0 updated, 0 unchanged)
  Events         128 found  (128 new, 0 updated, 0 unchanged)
  Tasks           15 found  (15 new, 0 updated, 0 unchanged)

  Outlook: not_found
  (Outlook write-back will be available in Phase 2)

All data saved locally. No changes were made to your Google account.
```

That's it. GBridge has read your Google data and saved a local snapshot. Your Google account was not modified in any way.

### Step 5: Check Status Anytime

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

## CLI Commands

| Command | What it does |
|---|---|
| `gbridge` or `gbridge sync` | Run a sync cycle |
| `gbridge status` | Show sync status and item counts |
| `gbridge auth` | Re-authenticate with Google |
| `gbridge --version` | Show version info |

## Troubleshooting

**"GBridge needs a Google API credentials file"**
You haven't placed `client_secret.json` yet. Follow Step 3 above. GBridge will print the exact path where it expects the file.

**"Authentication failed"**
Run `gbridge auth` to re-authenticate. If the problem persists, make sure you enabled all 3 APIs (People, Calendar, Tasks) in the Google Cloud Console.

**"Token refresh failed"**
Your saved token expired. Run `gbridge auth` to sign in again.

**Browser doesn't open automatically?**
Copy the URL from the terminal and paste it into your browser manually.

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
  __main__.py          # CLI entry point (sync, status, auth, version)
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
