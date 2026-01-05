#!/bin/bash

# =============================================================================
# VPN WATCHDOG - MACOS INSTALLER
# =============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_NAME="vpn-watchdog"
INSTALL_DIR="/Applications"

echo "======================================================"
echo "   VPN WATCHDOG - SETUP MANAGER (MACOS)"
echo "======================================================"

# 1. Check Binary
if [ ! -f "$DIR/$APP_NAME" ]; then
    echo "[ERROR] Binary '$APP_NAME' not found in current folder."
    exit 1
fi

# 2. Install (Copy to Applications)
echo "[INFO] Installing to $INSTALL_DIR..."
# We use sudo only if copying to /Applications fails (permissions)
cp "$DIR/$APP_NAME" "$INSTALL_DIR/$APP_NAME" || sudo cp "$DIR/$APP_NAME" "$INSTALL_DIR/$APP_NAME"

# 3. Permissions & Quarantine
echo "[INFO] Setting permissions..."
chmod +x "$INSTALL_DIR/$APP_NAME"

# Try to remove the "Quarantine" flag (fix for "App is damaged" or "Unknown Developer" error)
echo "[INFO] Whitelisting binary (Gatekeeper)..."
xattr -d com.apple.quarantine "$INSTALL_DIR/$APP_NAME" 2>/dev/null || true

echo ""
echo "[SUCCESS] Installation complete."
echo "You can run the app via Terminal: $INSTALL_DIR/$APP_NAME"
echo "To make it run nicely in the Dock, consider wrapping it in an Automator App."
echo ""