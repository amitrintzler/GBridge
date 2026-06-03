; GBridge Windows Installer (NSIS)
; Creates a standard Windows installer that:
;   - Installs gbridge.exe to Program Files
;   - Creates Start Menu shortcut
;   - Creates Desktop shortcut
;   - Adds uninstaller
;   - No Python required — everything is bundled

!define APPNAME "GBridge"
!define COMPANYNAME "Amit Rintzler"
!define DESCRIPTION "Sync Google Contacts, Calendar, and Tasks with Outlook"
; VERSION is passed from build.bat via /DVERSION=x.y.z
!ifndef VERSION
  !define VERSION "0.2.1"
!endif
!define HELPURL "https://github.com/amitrintzler/GBridge"
!define INSTALLSIZE 50000  ; ~50MB estimate

Name "${APPNAME}"
OutFile "..\..\dist\GBridge-Setup.exe"
InstallDir "$PROGRAMFILES\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "Install_Dir"
RequestExecutionLevel admin
Icon "gbridge.ico"
UninstallIcon "gbridge.ico"

;--------------------------------
; Pages

Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

;--------------------------------
; Installer

Section "Install"
  SetOutPath $INSTDIR

  ; Copy the standalone exe
  File "..\..\dist\windows\gbridge.exe"

  ; Copy the icon so shortcuts and Add/Remove Programs use it
  File "gbridge.ico"

  ; Create config directory for the user
  CreateDirectory "$APPDATA\${APPNAME}"

  ; ---- Outlook CalDav Synchronizer (optional addin, standalone-Outlook) --
  ; The DAV path (standalone classic Outlook) needs the free Outlook CalDav
  ; Synchronizer addin. The M365 / Graph path does NOT need it, so this is
  ; always optional and never blocks the GBridge install.
  ;
  ; Build-time choice:
  ;   * If installer\windows\vendor\OutlookCalDavSynchronizer.msi is present
  ;     when makensis runs, it is bundled and installed silently here.
  ;   * Otherwise the user is told exactly where to get it (a checked-in URL
  ;     download is intentionally NOT used: OCS ships as a versioned archive,
  ;     not a stable MSI URL, so an unattended fetch can't be verified at
  ;     build time — see installer/windows/README for the vendoring step).
  !if /FileExists "vendor\OutlookCalDavSynchronizer.msi"
    DetailPrint "Installing Outlook CalDav Synchronizer (bundled)"
    File "/oname=OutlookCalDavSynchronizer.msi" "vendor\OutlookCalDavSynchronizer.msi"
    ExecWait '"$SYSDIR\msiexec.exe" /i "$INSTDIR\OutlookCalDavSynchronizer.msi" /qn /norestart ALLUSERS=1' $0
    ${If} $0 != 0
      ${AndIf} $0 != 3010
        DetailPrint "OCS MSI returned $0 (ignored; GBridge install continues)"
    ${EndIf}
  !else
    DetailPrint "Outlook CalDav Synchronizer not bundled."
    DetailPrint "  Only needed for standalone (non-M365) Outlook."
    DetailPrint "  Get it from: https://caldavsynchronizer.org/"
  !endif

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Setup Wizard.lnk" "$INSTDIR\gbridge.exe" "setup" "$INSTDIR\gbridge.ico" "" "" "" "Set up GBridge (first time)"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Sync.lnk" "$INSTDIR\gbridge.exe" "sync" "$INSTDIR\gbridge.ico" "" "" "" "Sync Google with Outlook"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Status.lnk" "$INSTDIR\gbridge.exe" "status" "$INSTDIR\gbridge.ico" "" "" "" "Check sync status"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut — runs the setup wizard on first use
  CreateShortcut "$DESKTOP\GBridge.lnk" "$INSTDIR\gbridge.exe" "setup" "$INSTDIR\gbridge.ico" "" "" "" "GBridge — Sync Google with Outlook"

  ; Add to PATH
  EnVar::AddValue "PATH" "$INSTDIR"

  ; Registry for Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\gbridge.ico"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
  WriteRegStr HKLM "Software\${APPNAME}" "Install_Dir" "$INSTDIR"

SectionEnd

;--------------------------------
; Uninstaller

Section "Uninstall"
  ; Remove files
  Delete "$INSTDIR\gbridge.exe"
  Delete "$INSTDIR\gbridge.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; Remove shortcuts
  Delete "$SMPROGRAMS\${APPNAME}\*.*"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\GBridge.lnk"

  ; Remove from PATH
  EnVar::DeleteValue "PATH" "$INSTDIR"

  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKLM "Software\${APPNAME}"

  ; NOTE: We do NOT delete %APPDATA%\GBridge — user's sync data stays safe
  MessageBox MB_OK "GBridge has been uninstalled.$\n$\nYour sync data in $APPDATA\${APPNAME} was kept. Delete it manually if you want."

SectionEnd
