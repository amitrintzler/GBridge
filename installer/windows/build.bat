@echo off
REM Build GBridge Windows installer
REM Run this from the project root: installer\windows\build.bat
REM
REM Prerequisites (dev machine only, NOT end users):
REM   pip install pyinstaller nsis
REM
REM Output: dist/GBridge-Setup.exe

echo === Building GBridge for Windows ===
echo.

REM Step 1: Build standalone exe with PyInstaller
echo [1/2] Building standalone executable...
pyinstaller gbridge.spec --distpath dist\windows --workpath build\windows --clean -y
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)
echo       Done: dist\windows\gbridge.exe
echo.

REM Step 2: Build NSIS installer
echo [2/2] Building installer with NSIS...
makensis /DVERSION=0.2.0 installer\windows\gbridge.nsi
if errorlevel 1 (
    echo ERROR: NSIS build failed
    exit /b 1
)
echo       Done: dist\GBridge-Setup.exe
echo.

echo === Build complete ===
echo.
echo Give your users: dist\GBridge-Setup.exe
echo They double-click it, GBridge installs, done.
