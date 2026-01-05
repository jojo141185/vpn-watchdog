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
BINARY_NAME="vpn-watchdog" 
INSTALL_DIR="/usr/local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vpn-watchdog"
AUTOSTART_DIR="$HOME/.config/autostart"

# GITHUB CONFIG
REPO_USER="jojo141185"
REPO_NAME="vpn-watchdog"
DOWNLOAD_URL="https://github.com/$REPO_USER/$REPO_NAME/releases/latest/download/$BINARY_NAME"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    clear
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE}   VPN WATCHDOG - SETUP MANAGER${NC}"
    echo -e "${BLUE}======================================================${NC}"
}

ensure_sudo() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Note: Sudo privileges required for installation.${NC}"
        sudo -v
    fi
}

# 1. INSTALL DEPENDENCIES
install_dependencies() {
    echo -e "\n${BLUE}[1/4] Checking system dependencies...${NC}"
    
    if command -v apt-get &> /dev/null; then
        echo "Detected: APT"
        sudo apt-get update -qq
        sudo apt-get install -y -qq gir1.2-appindicator3-0.1 libappindicator3-1 python3-tk xapp
    elif command -v dnf &> /dev/null; then
        echo "Detected: DNF"
        sudo dnf install -y libappindicator-gtk3 python3-tkinter
    elif command -v pacman &> /dev/null; then
        echo "Detected: Pacman"
        sudo pacman -S --noconfirm libappindicator-gtk3 tk
    else
        echo -e "${RED}Warning: No known package manager found.${NC}"
        echo "Please ensure 'libappindicator' and 'python-tk' are installed."
    fi
}

# 2. FETCH BINARY
fetch_binary() {
    echo -e "\n${BLUE}[2/4] Preparing installation...${NC}"
    
    if [ -f "./$BINARY_NAME" ]; then
        echo -e "${GREEN}Local binary found.${NC}"
        cp "./$BINARY_NAME" "/tmp/$BINARY_NAME"
    else
        echo -e "${YELLOW}No local file found. Downloading from GitHub...${NC}"
        echo "URL: $DOWNLOAD_URL"
        
        if curl --output /dev/null --silent --head --fail "$DOWNLOAD_URL"; then
            curl -L -o "/tmp/$BINARY_NAME" "$DOWNLOAD_URL" --progress-bar
            echo -e "${GREEN}Download successful.${NC}"
        else
            echo -e "${RED}ERROR: Could not download from GitHub.${NC}"
            echo "Ensure a Release exists and the file is named '$BINARY_NAME'."
            exit 1
        fi
    fi
    
    chmod +x "/tmp/$BINARY_NAME"
}

# 3. INSTALL FILES
install_files() {
    echo -e "\n${BLUE}[3/4] Installing application...${NC}"
    ensure_sudo

    pkill -f "$BINARY_NAME" 2>/dev/null

    echo "Copying to $INSTALL_DIR..."
    sudo cp "/tmp/$BINARY_NAME" "$INSTALL_DIR/$APP_NAME"
    sudo chmod +x "$INSTALL_DIR/$APP_NAME"

    echo "Creating menu entry..."
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

# 4. UNINSTALL
uninstall_app() {
    print_header
    echo -e "${RED}WARNING: Uninstalling${NC}"
    read -p "Do you really want to remove VPN Watchdog? (y/N): " confirm
    if [[ $confirm != [yY] && $confirm != [yY][eE][sS] ]]; then
        exit 0
    fi

    echo -e "\nStopping process..."
    pkill -f "$APP_NAME"

    echo "Deleting files..."
    sudo rm -f "$INSTALL_DIR/$APP_NAME"
    rm -f "$DESKTOP_DIR/$APP_NAME.desktop"
    rm -f "$AUTOSTART_DIR/$APP_NAME.desktop"

    echo "Deleting configuration..."
    rm -rf "$CONFIG_DIR"

    echo -e "${GREEN}VPN Watchdog removed successfully.${NC}"
}

# --- MENU ---
show_menu() {
    print_header
    echo "1) Install (or Update)"
    echo "2) Uninstall"
    echo "0) Exit"
    echo ""
    read -p "Choice: " choice

    case $choice in
        1)
            install_dependencies
            fetch_binary
            install_files
            echo -e "\n${GREEN}Done! You can find the app in your start menu.${NC}"
            ;;
        2)
            uninstall_app
            ;;
        0)
            exit 0
            ;;
        *)
            echo "Invalid choice."
            ;;
    esac
}

if [ "$1" == "install" ] || [ "$1" == "-i" ]; then
    install_dependencies
    fetch_binary
    install_files
elif [ "$1" == "remove" ] || [ "$1" == "uninstall" ] || [ "$1" == "-u" ]; then
    uninstall_app
else
    show_menu
fi