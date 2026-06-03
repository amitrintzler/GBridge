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
    <string>0.2.1</string>
    <key>CFBundleShortVersionString</key>
    <string>0.2.1</string>
    <key>CFBundleExecutable</key>
    <string>gbridge</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# Create the .dmg.  Prefer create-dmg (nicer layout with an Applications
# drop-link) when present, but ALWAYS fall back to hdiutil — which ships with
# every macOS install — so a .dmg is produced even without Homebrew.
DMG_PATH="dist/GBridge.dmg"
rm -f "$DMG_PATH"

if command -v create-dmg &> /dev/null; then
    echo "      Using create-dmg..."
    create-dmg \
        --volname "GBridge" \
        --window-size 600 400 \
        --icon-size 100 \
        --app-drop-link 400 200 \
        "$DMG_PATH" \
        "$APP_DIR"
else
    echo "      create-dmg not found — using built-in hdiutil..."
    # Stage just the .app (and an Applications symlink) into a clean folder.
    STAGE="$(mktemp -d)"
    cp -R "$APP_DIR" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create \
        -volname "GBridge" \
        -srcfolder "$STAGE" \
        -ov -format UDZO \
        "$DMG_PATH"
    rm -rf "$STAGE"
fi

echo "      Done: $DMG_PATH"
echo
echo "=== Build complete ==="
echo
echo "Test it:"
echo "  open $DMG_PATH         # mount and inspect"
echo "  Drag GBridge.app to Applications, then in Terminal:"
echo "  /Applications/GBridge.app/Contents/MacOS/gbridge setup"
