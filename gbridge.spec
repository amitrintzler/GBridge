# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for GBridge.

Bundles the entire application + Python runtime into a single
standalone executable. No Python installation required on the
target machine.

Build with:
    pyinstaller gbridge.spec
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["src/gbridge/__main__.py"],
    pathex=[],
    binaries=[],
    # Bundle the app icon so runtime features (toast notifications,
    # system tray — Phase 3) can reference it via utils.resources.
    datas=[("installer/windows/gbridge.ico", ".")],
    hiddenimports=[
        "gbridge",
        "gbridge.core",
        "gbridge.core.engine",
        "gbridge.core.hasher",
        "gbridge.core.ledger",
        "gbridge.google",
        "gbridge.google.auth",
        "gbridge.google.calendar",
        "gbridge.google.models",
        "gbridge.google.people",
        "gbridge.google.tasks",
        "gbridge.outlook",
        "gbridge.outlook.detect",
        "gbridge.config",
        "gbridge.config.defaults",
        "gbridge.config.settings",
        "gbridge.utils",
        "gbridge.utils.logger",
        "gbridge.utils.backoff",
        "gbridge.utils.resources",
        "gbridge.utils.notify",
        "gbridge.utils.scheduler",
        "gbridge.utils.tray",
        "gbridge.daemon",
        "gbridge.service",
        "gbridge.service.windows",
        "gbridge.service.macos",
        "gbridge.service.linux",
        "gbridge.gui",
        "gbridge.gui.wizard",
        # Google API dependencies
        "googleapiclient",
        "googleapiclient.discovery",
        "google.auth",
        "google.auth.transport.requests",
        "google.oauth2.credentials",
        "google_auth_oauthlib",
        "google_auth_oauthlib.flow",
        # Keyring backends
        "keyring",
        "keyring.backends",
        # Windows keyring backend
        "keyring.backends.Windows",
        # macOS keyring backend
        "keyring.backends.macOS",
        # Linux keyring backends
        "keyring.backends.SecretService",
        "secretstorage",
        "jeepney",
        # Phase 3 runtime: notifications + tray + scheduler
        "plyer",
        "plyer.platforms.win.notification",
        "plyer.platforms.macosx.notification",
        "plyer.platforms.linux.notification",
        "pystray",
        "pystray._win32",
        "pystray._darwin",
        "pystray._xorg",
        "PIL",
        "PIL.Image",
        "apscheduler",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.interval",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "distutils",
        "setuptools",
        "pip",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="gbridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console app — shows sync output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="installer/windows/gbridge.ico",
)
