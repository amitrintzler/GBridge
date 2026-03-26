#!/bin/bash
# Build GBridge Linux packages (.deb + .rpm)
# Run from project root: bash installer/linux/build.sh
#
# Prerequisites (dev machine only):
#   pip install pyinstaller
#   gem install fpm   (for .deb/.rpm packaging)
#
# Output: dist/gbridge_0.1.0_amd64.deb, dist/gbridge-0.1.0.x86_64.rpm

set -e

VERSION="0.1.0"

echo "=== Building GBridge for Linux ==="
echo

# Step 1: Build standalone binary with PyInstaller
echo "[1/3] Building standalone executable..."
pyinstaller gbridge.spec \
    --distpath dist/linux \
    --workpath build/linux \
    --clean -y
echo "      Done: dist/linux/gbridge"
echo

# Step 2: Create staging directory
echo "[2/3] Staging files..."
STAGING="build/linux/staging"
rm -rf "$STAGING"
mkdir -p "$STAGING/usr/local/bin"
mkdir -p "$STAGING/usr/share/applications"

cp dist/linux/gbridge "$STAGING/usr/local/bin/gbridge"
chmod +x "$STAGING/usr/local/bin/gbridge"

# Desktop entry for Linux desktop environments
cat > "$STAGING/usr/share/applications/gbridge.desktop" << 'DESKTOP'
[Desktop Entry]
Name=GBridge
Comment=Sync Google Contacts, Calendar, and Tasks with Outlook
Exec=gbridge setup
Terminal=true
Type=Application
Categories=Office;Network;
DESKTOP

echo "      Done"
echo

# Step 3: Build packages with fpm
echo "[3/3] Building packages..."

if command -v fpm &> /dev/null; then
    # .deb package (Ubuntu/Debian)
    fpm -s dir -t deb \
        -n gbridge \
        -v "$VERSION" \
        --description "Sync Google Contacts, Calendar, and Tasks with Outlook" \
        --maintainer "Amit Rintzler" \
        --url "https://github.com/amitrintzler/GBridge" \
        --license "MIT" \
        -C "$STAGING" \
        -p "dist/gbridge_${VERSION}_amd64.deb" \
        .
    echo "      Done: dist/gbridge_${VERSION}_amd64.deb"

    # .rpm package (Fedora/RHEL)
    fpm -s dir -t rpm \
        -n gbridge \
        -v "$VERSION" \
        --description "Sync Google Contacts, Calendar, and Tasks with Outlook" \
        --maintainer "Amit Rintzler" \
        --url "https://github.com/amitrintzler/GBridge" \
        --license "MIT" \
        -C "$STAGING" \
        -p "dist/gbridge-${VERSION}.x86_64.rpm" \
        .
    echo "      Done: dist/gbridge-${VERSION}.x86_64.rpm"
else
    echo "      fpm not found — binary built at: dist/linux/gbridge"
    echo "      Install fpm for packages: gem install fpm"
fi

echo
echo "=== Build complete ==="
