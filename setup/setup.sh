#!/bin/bash

# =============================================================================
# VPN WATCHDOG - SETUP MANAGER
# =============================================================================
# Install, Update, and Uninstall script.
# Compatible with direct curl execution:
# bash <(curl -sL https://raw.githubusercontent.com/jojo141185/vpn-watchdog/main/setup/setup.sh) install
# =============================================================================

# --- CONFIGURATION ---
APP_NAME="vpn-watchdog"
# The binary name inside the ZIP is always consistent
BINARY_NAME="vpn-watchdog" 
INSTALL_DIR="/usr/local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vpn-watchdog"

# GITHUB CONFIG
REPO_USER="jojo141185"
REPO_NAME="vpn-watchdog"

# Default Channel
CHANNEL="stable"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse Arguments
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    if [[ "${args[i]}" == "--channel" ]]; then
        CHANNEL="${args[i+1]}"
    fi
done

# --- ARCHITECTURE DETECTION ---
detect_platform() {
    OS="linux" # Setup.sh assumes Linux context mostly
    ARCH=$(uname -m)
    
    # Normalize Arch to match GitHub Action Naming
    case $ARCH in
        x86_64) ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        armv7l) ARCH="armv7" ;; # Raspberry Pi 32bit (not built by default yet)
    esac
    
    PACKAGE_FILENAME="vpn-watchdog-${OS}-${ARCH}.zip"
    echo "Detected Platform: $OS ($ARCH)"
    echo "Target Package: $PACKAGE_FILENAME"
}

# --- DOWNLOAD URL CALCULATION ---
get_download_url() {
    if [ "$CHANNEL" == "stable" ]; then
        URL="https://github.com/$REPO_USER/$REPO_NAME/releases/latest/download/$PACKAGE_FILENAME"
        VERSION_MSG="Stable Release"
    else
        URL="https://github.com/$REPO_USER/$REPO_NAME/releases/download/latest-$CHANNEL/$PACKAGE_FILENAME"
        VERSION_MSG="Dev Build ($CHANNEL)"
    fi
}

print_header() {
    clear
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE}   VPN WATCHDOG - SETUP MANAGER${NC}"
    echo -e "${BLUE}======================================================${NC}"
    detect_platform
    get_download_url
    echo -e "Source: $VERSION_MSG"
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
        sudo apt-get install -y -qq gir1.2-appindicator3-0.1 libappindicator3-1 python3-tk xapp unzip
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y libappindicator-gtk3 python3-tkinter unzip
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm libappindicator-gtk3 tk unzip
    else
        echo -e "${RED}Warning: Manual dependency check required (need unzip, python-tk, libappindicator).${NC}"
    fi
}

fetch_and_unpack() {
    echo -e "\n${BLUE}[2/4] Fetching package...${NC}"
    TMP_DIR="/tmp/vpn-watchdog-install"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    
    ZIP_PATH="$TMP_DIR/$PACKAGE_FILENAME"
    
    # Check if we are running from an extracted folder (Local Install)
    if [ -f "./$BINARY_NAME" ] && [ "$CHANNEL" == "stable" ]; then
        echo -e "${GREEN}Local binary found. Skipping download.${NC}"
        cp "./$BINARY_NAME" "$TMP_DIR/$BINARY_NAME"
    else
        echo -e "${YELLOW}Downloading $PACKAGE_FILENAME...${NC}"
        echo "URL: $URL"
        
        if curl -L --output "$ZIP_PATH" --fail "$URL"; then
            echo -e "${GREEN}Download successful.${NC}"
            echo "Unzipping..."
            unzip -o -q "$ZIP_PATH" -d "$TMP_DIR"
        else
            echo -e "${RED}ERROR: Download failed.${NC}"
            echo "1. Check internet connection."
            echo "2. Check if a build for '$ARCH' exists in the release."
            exit 1
        fi
    fi
    
    # Verify binary exists after unzip
    if [ ! -f "$TMP_DIR/$BINARY_NAME" ]; then
        echo -e "${RED}Error: Binary not found in package!${NC}"
        ls -l "$TMP_DIR"
        exit 1
    fi
    
    chmod +x "$TMP_DIR/$BINARY_NAME"
}

install_files() {
    echo -e "\n${BLUE}[3/4] Installing...${NC}"
    ensure_sudo
    pkill -f "$BINARY_NAME" 2>/dev/null

    TMP_DIR="/tmp/vpn-watchdog-install"
    
    sudo cp "$TMP_DIR/$BINARY_NAME" "$INSTALL_DIR/$APP_NAME"
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
    
    # Cleanup
    rm -rf "$TMP_DIR"
    
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
    fetch_and_unpack
    install_files
elif [[ " $@ " =~ " uninstall " ]] || [[ "$1" == "uninstall" ]]; then
    uninstall_app
else
    echo "Usage:"
    echo "  ./setup.sh install"
    echo "  ./setup.sh install --channel main"
    echo "  ./setup.sh uninstall"
fi