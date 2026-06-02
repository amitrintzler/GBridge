# Windows installer

`build.bat` builds `gbridge.exe` with PyInstaller, then packages it into
`GBridge-Setup.exe` with NSIS (`gbridge.nsi`).

## Optional: bundle the Outlook CalDav Synchronizer addin

The **standalone classic Outlook** sync path (`outlook_mode = dav`) needs the
free third-party [Outlook CalDav Synchronizer](https://caldavsynchronizer.org/)
addin. The **Microsoft 365 / Graph path does not need it.**

To bundle it so the installer sets it up silently:

1. Download the latest release from
   <https://github.com/aluxnimm/outlookcaldavsynchronizer/releases>
2. If the release provides an MSI, place it here:
   ```
   installer/windows/vendor/OutlookCalDavSynchronizer.msi
   ```
3. Run `build.bat`. The NSIS script detects the vendored MSI at build time
   and installs it with `msiexec /qn /norestart`.

If the file is absent, the installer skips it and tells the user where to
get it — GBridge still installs and the M365 path works normally.

> An automatic download from inside the installer is intentionally not used:
> OCS ships as a versioned archive (the exact asset name changes per release),
> so an unattended fetch cannot be pinned/verified at build time. Vendoring a
> known-good MSI is the reliable path. This is tracked in BACKLOG under
> Phase 4 packaging.

## Code signing

`GBridge-Setup.exe` and `gbridge.exe` are not yet Authenticode-signed, so
Windows SmartScreen shows a warning on first run. Signing requires a
certificate (owner action — see BACKLOG).
