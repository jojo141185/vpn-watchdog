#!/bin/bash

# =============================================================================
# VPN WATCHDOG - MACOS INSTALLER
# =============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_NAME="vpn-watchdog"
INSTALL_DIR="/Applications"
TARGET_PATH="$INSTALL_DIR/$APP_NAME"
CONFIG_DIR="$HOME/.config/vpn-watchdog"
AUTOSTART_PLIST="$HOME/Library/LaunchAgents/com.vpnwatchdog.plist"

echo "======================================================"
echo "   VPN WATCHDOG - SETUP MANAGER (MACOS)"
echo "======================================================"

# 1. Check Source Binary
if [ ! -f "$DIR/$APP_NAME" ]; then
    echo "[ERROR] Binary '$APP_NAME' not found in current folder."
    exit 1
fi

# 2. Check Existing Installation
if [ -f "$TARGET_PATH" ]; then
    echo ""
    echo "[INFO] Existing installation detected!"
    echo "  Binary:    $TARGET_PATH"
    echo "  Config:    $CONFIG_DIR"
    echo "  Autostart: $AUTOSTART_PLIST"
    echo ""
    echo "What do you want to do?"
    echo "  [1] Update / Re-Install (Default)"
    echo "  [2] Uninstall completely"
    echo ""
    read -p "Select option [1-2]: " choice
    
    if [ "$choice" == "2" ]; then
        echo ""
        echo "[INFO] Uninstalling..."
        
        # Stop App
        pkill -f "$APP_NAME"
        
        # Remove Binary
        echo "  - Removing App..."
        rm -f "$TARGET_PATH" || sudo rm -f "$TARGET_PATH"
        
        # Remove Autostart
        echo "  - Removing LaunchAgent..."
        rm -f "$AUTOSTART_PLIST"
        
        # Determine if we should remove config (Optional)
        echo ""
        echo "[INFO] Configuration kept at: $CONFIG_DIR"
        echo ""
        echo "[SUCCESS] Uninstalled."
        exit 0
    fi
fi

# 3. Install (Copy to Applications)
echo ""
echo "[INFO] Installing to $INSTALL_DIR..."

# Stop App if running (Update case)
pkill -f "$APP_NAME" 2>/dev/null

# We use sudo only if copying to /Applications fails (permissions)
cp "$DIR/$APP_NAME" "$TARGET_PATH" || sudo cp "$DIR/$APP_NAME" "$TARGET_PATH"

# 4. Permissions & Quarantine
echo "[INFO] Setting permissions..."
chmod +x "$TARGET_PATH"

# Try to remove the "Quarantine" flag (fix for "App is damaged" or "Unknown Developer" error)
echo "[INFO] Whitelisting binary (Gatekeeper)..."
xattr -d com.apple.quarantine "$TARGET_PATH" 2>/dev/null || true

echo ""
echo "[SUCCESS] Installation complete."
echo "You can run the app via Terminal: $TARGET_PATH"
echo "To make it run nicely in the Dock, consider wrapping it in an Automator App."
echo ""