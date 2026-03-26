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

### 1. Install Python 3.11+

Download from [python.org](https://www.python.org/downloads/) or use your package manager:

```bash
# macOS
brew install python@3.12

# Ubuntu/Debian
sudo apt install python3.12

# Windows — download the installer from python.org
```

### 2. Install GBridge

```bash
pip install git+https://github.com/amitrintzler/GBridge.git
```

Or clone and install locally:

```bash
git clone https://github.com/amitrintzler/GBridge.git
cd GBridge
pip install -e .
```

### 3. Set Up Google API Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable these APIs:
   - **People API** (for contacts)
   - **Google Calendar API** (for events)
   - **Tasks API** (for tasks)
4. Go to **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID**
5. Choose **Desktop application**
6. Download the JSON file and rename it to `client_secret.json`
7. Place it in your GBridge config directory:
   - **Windows:** `%APPDATA%\GBridge\client_secret.json`
   - **macOS:** `~/Library/Application Support/GBridge/client_secret.json`
   - **Linux:** `~/.config/gbridge/client_secret.json`

### 4. Run GBridge

```bash
gbridge
```

On first run, your browser will open to authorize GBridge with your Google account. GBridge only requests **read-only** access.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone https://github.com/amitrintzler/GBridge.git
cd GBridge
uv pip install -e ".[dev]"
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
  __main__.py          # Entry point
  core/
    engine.py          # Sync orchestrator
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

  Contacts  ──────>  Fetch via People API  ──────>  (Phase 2)
  Calendar  ──────>  Fetch via Calendar API ─────>  (Phase 2)
  Tasks     ──────>  Fetch via Tasks API   ──────>  (Phase 2)
                          │
                     SHA-256 diff
                          │
                     SQLite ledger
                  (tracks what changed)
```

**Phase 1** (current): Fetches from Google, computes diffs, tracks state locally.
**Phase 2** (next): Writes changes to Outlook via Microsoft Graph API or local DAV server.

## License

MIT License. See [LICENSE](LICENSE) for details.
