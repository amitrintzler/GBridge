# Security Policy

## Trust Model

GBridge is designed with a **zero-trust, read-only** philosophy. Here's exactly what it does and doesn't do:

### What GBridge DOES

| Action | Details |
|---|---|
| Reads Google Contacts | Via People API with `contacts.readonly` scope |
| Reads Google Calendar | Via Calendar API with `calendar.readonly` scope |
| Reads Google Tasks | Via Tasks API with `tasks.readonly` scope |
| Stores sync state | Local SQLite database on your computer |
| Stores login tokens | In your OS keychain (Windows Credential Locker / macOS Keychain / Linux Secret Service) |
| Connects to | `googleapis.com` and `accounts.google.com` only |

### What GBridge DOES NOT DO

- Does NOT modify, delete, or write to your Google account (read-only scopes make this impossible)
- Does NOT send data to any server other than Google's APIs
- Does NOT collect analytics, telemetry, or usage data
- Does NOT run in the background unless you explicitly set it up
- Does NOT access files on your computer (except its own config folder)
- Does NOT require admin/root privileges to run
- Does NOT contain ads, trackers, or monetization of any kind

### Network Connections

GBridge only connects to these domains:
- `accounts.google.com` — OAuth authentication
- `people.googleapis.com` — Contacts sync
- `www.googleapis.com` — Calendar and Tasks sync
- `oauth2.googleapis.com` — Token refresh

No other network connections are made. You can verify this with a network monitor.

## Verifying Downloads

Every release includes a `checksums.sha256` file. To verify your download:

### Windows (PowerShell)
```powershell
Get-FileHash gbridge-windows.exe -Algorithm SHA256
# Compare the output with the hash in checksums.sha256
```

### macOS / Linux
```bash
sha256sum -c checksums.sha256
```

## Source Code Transparency

GBridge is 100% open source under the MIT license. You can:
- Read every line of code on [GitHub](https://github.com/amitrintzler/GBridge)
- Build from source yourself to verify the binary matches
- Audit the dependency list in `pyproject.toml`

## Automated Security Checks

Every code change is automatically scanned by:
- **Ruff security rules** — catches common Python vulnerabilities (injection, hardcoded secrets, etc.)
- **Bandit** — deep static security analysis
- **pip-audit** — scans all dependencies for known CVEs
- **CodeQL** — GitHub's semantic code analysis
- **SBOM generation** — full Software Bill of Materials published with each release

## Code Signing

### Current Status
Binaries are currently **unsigned**. On Windows, you may see a SmartScreen warning ("Windows protected your PC"). This is normal for all new open-source software — it does not mean the software is malicious. Microsoft shows this warning for any software that hasn't been downloaded thousands of times yet. As GBridge gains more users, this warning will disappear automatically.

To bypass SmartScreen:
1. Click "More info"
2. Click "Run anyway"

On macOS, if Gatekeeper blocks the app:
1. Open System Preferences > Security & Privacy
2. Click "Open Anyway"

### Why no code signing?
Code signing certificates cost money ($200+/year). GBridge is a free, community-driven project — we don't charge users and we don't have corporate sponsors. Instead, we rely on:
- **Full source code transparency** — every line is on GitHub
- **Automated security scanning** — CodeQL, Bandit, pip-audit on every commit
- **SHA-256 checksums** — verify your download matches what we built
- **Reproducible builds** — you can build from source yourself

## Reporting a Vulnerability

If you discover a security vulnerability in GBridge:

1. **DO NOT** open a public GitHub issue
2. Email: Create a private security advisory at https://github.com/amitrintzler/GBridge/security/advisories/new
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work on a fix immediately.

## Dependency Policy

- Dependencies are kept to a minimum (only Google API libraries, keyring, and APScheduler)
- All dependencies are scanned weekly for known vulnerabilities
- We pin minimum versions but allow compatible updates
- A full SBOM (Software Bill of Materials) is published with every release

## Permissions Summary

| Resource | Access Level | Purpose |
|---|---|---|
| Google Contacts | Read-only | Sync contacts to Outlook |
| Google Calendar | Read-only | Sync events to Outlook |
| Google Tasks | Read-only | Sync tasks to Outlook |
| OS Keychain | Read/Write | Store OAuth tokens securely |
| Local filesystem | Config folder only | SQLite database + logs |
| Network | Google APIs only | Fetch data |
