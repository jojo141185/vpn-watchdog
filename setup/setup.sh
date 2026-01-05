#!/bin/bash

# =============================================================================
# VPN WATCHDOG - SETUP MANAGER
# =============================================================================
# Syntax:
# ./setup.sh install
# ./setup.sh install --channel main
# =============================================================================

# --- CONFIGURATION ---
APP_NAME="vpn-watchdog"
BINARY_NAME="vpn-watchdog" 
INSTALL_DIR="/usr/local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vpn-watchdog"

# GITHUB CONFIG
REPO_USER="jojo141185"
REPO_NAME="vpn-watchdog"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default Channel
CHANNEL="stable"

# Parse Arguments
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    if [[ "${args[i]}" == "--channel" ]]; then
        CHANNEL="${args[i+1]}"
    fi
done

# Calculate Download URL based on Channel
if [ "$CHANNEL" == "stable" ]; then
    # Standard Latest Release
    DOWNLOAD_URL="https://github.com/$REPO_USER/$REPO_NAME/releases/latest/download/$BINARY_NAME"
    VERSION_MSG="Stable Release"
else
    # Rolling Release (latest-main or latest-develop)
    DOWNLOAD_URL="https://github.com/$REPO_USER/$REPO_NAME/releases/download/latest-$CHANNEL/$BINARY_NAME"
    VERSION_MSG="Dev Build ($CHANNEL)"
fi

print_header() {
    clear
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE}   VPN WATCHDOG - SETUP MANAGER${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo -e "Target: $VERSION_MSG"
}

ensure_sudo() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Note: Sudo privileges required for installation.${NC}"
        sudo -v
    fi
}

install_dependencies() {
    echo -e "\n${BLUE}[1/4] Checking system dependencies...${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq gir1.2-appindicator3-0.1 libappindicator3-1 python3-tk xapp
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y libappindicator-gtk3 python3-tkinter
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm libappindicator-gtk3 tk
    else
        echo -e "${RED}Warning: Manual dependency check required.${NC}"
    fi
}

fetch_binary() {
    echo -e "\n${BLUE}[2/4] Fetching binary...${NC}"
    
    # Try local first (only if no channel specified or explicit local install)
    if [ -f "./$BINARY_NAME" ] && [ "$CHANNEL" == "stable" ]; then
        echo -e "${GREEN}Local binary found. Installing local version.${NC}"
        cp "./$BINARY_NAME" "/tmp/$BINARY_NAME"
    else
        echo -e "${YELLOW}Downloading from GitHub ($CHANNEL)...${NC}"
        echo "URL: $DOWNLOAD_URL"
        
        # Use -L to follow redirects
        if curl -L --output "/tmp/$BINARY_NAME" --fail "$DOWNLOAD_URL"; then
            echo -e "${GREEN}Download successful.${NC}"
        else
            echo -e "${RED}ERROR: Download failed.${NC}"
            echo "Check if the release 'latest-$CHANNEL' exists on GitHub."
            exit 1
        fi
    fi
    chmod +x "/tmp/$BINARY_NAME"
}

install_files() {
    echo -e "\n${BLUE}[3/4] Installing...${NC}"
    ensure_sudo
    pkill -f "$BINARY_NAME" 2>/dev/null

    sudo cp "/tmp/$BINARY_NAME" "$INSTALL_DIR/$APP_NAME"
    sudo chmod +x "$INSTALL_DIR/$APP_NAME"

    mkdir -p "$DESKTOP_DIR"
    cat << EOF > "$DESKTOP_DIR/$APP_NAME.desktop"
[Desktop Entry]
Type=Application
Name=VPN Watchdog
Comment=Monitor VPN Connection security
Exec=$INSTALL_DIR/$APP_NAME
Icon=security-high
Terminal=false
Categories=Network;Utility;System;
EOF
    chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"
    rm -f "/tmp/$BINARY_NAME"
    echo -e "${GREEN}Installation complete!${NC}"
}

uninstall_app() {
    print_header
    echo -e "${RED}WARNING: Uninstalling${NC}"
    pkill -f "$APP_NAME"
    sudo rm -f "$INSTALL_DIR/$APP_NAME"
    rm -f "$DESKTOP_DIR/$APP_NAME.desktop"
    echo -e "${GREEN}Removed.${NC}"
}

# CLI Router
if [[ " $@ " =~ " install " ]] || [[ "$1" == "install" ]]; then
    print_header
    install_dependencies
    fetch_binary
    install_files
elif [[ " $@ " =~ " uninstall " ]] || [[ "$1" == "uninstall" ]]; then
    uninstall_app
else
    echo "Usage:"
    echo "  ./setup.sh install"
    echo "  ./setup.sh install --channel main"
    echo "  ./setup.sh install --channel develop"
    echo "  ./setup.sh uninstall"
fi