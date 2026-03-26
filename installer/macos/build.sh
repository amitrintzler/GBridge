#!/bin/bash
# Build GBridge macOS installer (.dmg)
# Run from project root: bash installer/macos/build.sh
#
# Prerequisites (dev machine only):
#   pip install pyinstaller
#   brew install create-dmg  (optional, for .dmg)
#
# Output: dist/GBridge.dmg

set -e

echo "=== Building GBridge for macOS ==="
echo

# Step 1: Build standalone app with PyInstaller
echo "[1/2] Building standalone executable..."
pyinstaller gbridge.spec \
    --distpath dist/macos \
    --workpath build/macos \
    --clean -y
echo "      Done: dist/macos/gbridge"
echo

# Step 2: Create .app bundle structure
echo "[2/2] Creating .app bundle..."
APP_DIR="dist/macos/GBridge.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cp dist/macos/gbridge "$APP_DIR/Contents/MacOS/gbridge"
chmod +x "$APP_DIR/Contents/MacOS/gbridge"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>GBridge</string>
    <key>CFBundleDisplayName</key>
    <string>GBridge</string>
    <key>CFBundleIdentifier</key>
    <string>com.amitrintzler.gbridge</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleExecutable</key>
    <string>gbridge</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# Create DMG if create-dmg is available
if command -v create-dmg &> /dev/null; then
    create-dmg \
        --volname "GBridge" \
        --window-size 600 400 \
        --app-drop-link 400 200 \
        "dist/GBridge.dmg" \
        "$APP_DIR"
    echo "      Done: dist/GBridge.dmg"
else
    echo "      create-dmg not found — .app bundle created at: $APP_DIR"
    echo "      Install create-dmg for .dmg: brew install create-dmg"
fi

echo
echo "=== Build complete ==="
