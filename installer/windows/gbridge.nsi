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
  !define VERSION "0.1.0"
!endif
!define HELPURL "https://github.com/amitrintzler/GBridge"
!define INSTALLSIZE 50000  ; ~50MB estimate

Name "${APPNAME}"
OutFile "..\..\dist\GBridge-Setup.exe"
InstallDir "$PROGRAMFILES\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "Install_Dir"
RequestExecutionLevel admin

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

  ; Create config directory for the user
  CreateDirectory "$APPDATA\${APPNAME}"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Setup Wizard.lnk" "$INSTDIR\gbridge.exe" "setup" "" "" "" "" "Set up GBridge (first time)"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Sync.lnk" "$INSTDIR\gbridge.exe" "sync" "" "" "" "" "Sync Google with Outlook"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\GBridge Status.lnk" "$INSTDIR\gbridge.exe" "status" "" "" "" "" "Check sync status"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut — runs the setup wizard on first use
  CreateShortcut "$DESKTOP\GBridge.lnk" "$INSTDIR\gbridge.exe" "setup" "" "" "" "" "GBridge — Sync Google with Outlook"

  ; Add to PATH
  EnVar::AddValue "PATH" "$INSTDIR"

  ; Registry for Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
  WriteRegStr HKLM "Software\${APPNAME}" "Install_Dir" "$INSTDIR"

SectionEnd

;--------------------------------
; Uninstaller

Section "Uninstall"
  ; Remove files
  Delete "$INSTDIR\gbridge.exe"
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
