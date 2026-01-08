#!/bin/bash

# =============================================================================
# VPN WATCHDOG - UNIVERSAL SETUP MANAGER
# =============================================================================
# Install, Update, and Uninstall script.
# Supported Platforms: Linux, macOS (Darwin), Windows (Git Bash/MinGW)
#
# Usage (Interactive):
#   ./setup.sh
#
# Usage (CLI / Automation):
#   ./setup.sh install
#   ./setup.sh install --channel main
#   ./setup.sh uninstall
#
# Direct Download & Run:
#   bash <(curl -sL https://raw.githubusercontent.com/jojo141185/vpn-watchdog/main/setup/setup.sh) install
# =============================================================================

# --- CONFIGURATION ---
APP_NAME="vpn-watchdog"
BINARY_NAME="vpn-watchdog" # Will be adjusted for Windows later
REPO_USER="jojo141185"
REPO_NAME="vpn-watchdog"

# Default Channel
CHANNEL="stable"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- DETECT SYSTEM & ARCHITECTURE ---
detect_system() {
    RAW_OS=$(uname -s)
    RAW_ARCH=$(uname -m)

    # 1. Detect OS
    case "$RAW_OS" in
        Linux*)     OS="linux";;
        Darwin*)    OS="darwin";;
        MINGW*|CYGWIN*|MSYS*) OS="windows";;
        *)          echo -e "${RED}Unsupported OS: $RAW_OS${NC}"; exit 1;;
    esac

    # 2. Detect Architecture (Normalize to 'amd64' or 'arm64')
    case "$RAW_ARCH" in
        x86_64)  ARCH="amd64";;
        amd64)   ARCH="amd64";;
        aarch64) ARCH="arm64";;
        arm64)   ARCH="arm64";;
        *)       echo -e "${RED}Unsupported Architecture: $RAW_ARCH${NC}"; exit 1;;
    esac

    # 3. Adjust Paths & Extensions based on OS
    if [ "$OS" == "linux" ]; then
        INSTALL_DIR="/usr/local/bin"
        DESKTOP_DIR="$HOME/.local/share/applications"
        CONFIG_DIR="$HOME/.config/vpn-watchdog"
        AUTOSTART_DIR="$HOME/.config/autostart"
        BINARY_EXT=""
        NEEDS_SUDO=true
    elif [ "$OS" == "darwin" ]; then
        INSTALL_DIR="/Applications"
        # macOS doesn't use XDG desktop files, but we set a dummy path
        DESKTOP_DIR="$HOME/Desktop" 
        CONFIG_DIR="$HOME/.config/vpn-watchdog"
        AUTOSTART_DIR="$HOME/Library/LaunchAgents"
        BINARY_EXT=""
        NEEDS_SUDO=true 
    elif [ "$OS" == "windows" ]; then
        # In Git Bash, $HOME usually maps to C:\Users\Username
        INSTALL_DIR="$HOME/AppData/Local/VPNWatchdog"
        DESKTOP_DIR="$HOME/Desktop" 
        CONFIG_DIR="$HOME/.config/vpn-watchdog"
        AUTOSTART_DIR="$HOME/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
        BINARY_EXT=".exe"
        NEEDS_SUDO=false 
    fi

    FULL_BINARY_NAME="${BINARY_NAME}${BINARY_EXT}"
    TARGET_PATH="$INSTALL_DIR/$FULL_BINARY_NAME"
    PACKAGE_FILENAME="vpn-watchdog-${OS}-${ARCH}.zip"
}

# --- PARSE ARGUMENTS ---
args=("$@")
CMD_ARG=""
SHOW_HELP=false

for ((i=0; i<${#args[@]}; i++)); do
    case "${args[i]}" in
        --channel)
            CHANNEL="${args[i+1]}"
            ((i++))
            ;;
        install)
            CMD_ARG="install"
            ;;
        uninstall)
            CMD_ARG="uninstall"
            ;;
        --help|-h)
            SHOW_HELP=true
            ;;
        -*)
            echo -e "${RED}Unknown option: ${args[i]}${NC}"
            SHOW_HELP=true
            ;;
    esac
done

# --- CALCULATE DOWNLOAD URL ---
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
    detect_system 
    get_download_url
    echo -e "Platform: ${GREEN}$OS ($ARCH)${NC}"
    echo "------------------------------------------------------"
}

ensure_permissions() {
    if [ "$NEEDS_SUDO" = true ] && [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Note: Admin/Sudo privileges required for installation.${NC}"
    fi
}

# 1. INSTALL DEPENDENCIES
install_dependencies() {
    echo -e "\n${BLUE}[1/4] Checking system dependencies...${NC}"
    
    if [ "$OS" == "linux" ]; then
        if command -v apt-get &> /dev/null; then
            echo "Detected: APT"
            
            # Fix potentially broken packages first
            echo "Attempting to fix broken packages..."
            sudo apt-get install -f -y -qq
            
            sudo apt-get update -qq
            
            # 1. Install Base Packages (Safe, non-conflicting)
            echo "Installing core dependencies..."
            sudo apt-get install -y -qq \
                python3-tk \
                python3-pil.imagetk \
                unzip \
                libcanberra-gtk-module \
                libcanberra-gtk3-module

            # 2. Try Install Ayatana (Modern Standard for Ubuntu 22.04+)
            echo "Checking for Ayatana AppIndicator (Modern)..."
            if sudo apt-get install -y -qq gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1; then
                echo "Ayatana installed successfully."
            else
                echo -e "${YELLOW}Ayatana not found or conflict. Attempting Legacy AppIndicator...${NC}"
                # 3. Fallback to Legacy (Ubuntu 20.04 and older)
                sudo apt-get install -y -qq gir1.2-appindicator3-0.1 libappindicator3-1
            fi

        elif command -v dnf &> /dev/null; then
            echo "Detected: DNF"
            # Fedora usually maps libappindicator to ayatana automatically, but we ensure gtk3 support
            sudo dnf install -y libappindicator-gtk3 libayatana-appindicator-gtk3 python3-tkinter python3-pillow-tk unzip
        elif command -v pacman &> /dev/null; then
            echo "Detected: Pacman"
            sudo pacman -S --noconfirm libappindicator-gtk3 libayatana-appindicator python-gobject tk python-pillow unzip
        else
            echo -e "${RED}Warning: Manual dependency check required.${NC}"
        fi
    elif [ "$OS" == "darwin" ]; then
        # macOS check
        if ! command -v unzip &> /dev/null; then
            echo -e "${RED}Error: 'unzip' is missing.${NC}"
            exit 1
        fi
        echo "macOS dependencies look good."
    elif [ "$OS" == "windows" ]; then
        if ! command -v powershell &> /dev/null; then
            echo -e "${RED}Error: PowerShell is required for Windows installation.${NC}"
            exit 1
        fi
        if ! command -v unzip &> /dev/null; then
             echo -e "${YELLOW}Warning: 'unzip' not found.${NC}"
        fi
    fi
}

# 2. FETCH BINARY
fetch_and_unpack() {
    echo -e "\n${BLUE}[2/4] Fetching package...${NC}"
    TMP_DIR="/tmp/vpn-watchdog-install"
    # On Windows (Git Bash), /tmp might behave differently, let's allow override
    if [ "$OS" == "windows" ]; then TMP_DIR="./tmp_install"; fi

    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    
    ZIP_PATH="$TMP_DIR/$PACKAGE_FILENAME"
    
    # Check for local file first
    if [ -f "./$FULL_BINARY_NAME" ] && [ "$CHANNEL" == "stable" ]; then
        echo -e "${GREEN}Local binary found. Skipping download.${NC}"
        cp "./$FULL_BINARY_NAME" "$TMP_DIR/$FULL_BINARY_NAME"
    else
        echo -e "${YELLOW}Downloading $PACKAGE_FILENAME...${NC}"
        echo "URL: $URL"
        
        if curl -L --output "$ZIP_PATH" --fail "$URL"; then
            echo -e "${GREEN}Download successful.${NC}"
            echo "Unzipping..."
            unzip -o -q "$ZIP_PATH" -d "$TMP_DIR"
        else
            echo -e "${RED}ERROR: Download failed.${NC}"
            exit 1
        fi
    fi
    
    # Verify binary exists inside
    if [ ! -f "$TMP_DIR/$FULL_BINARY_NAME" ]; then
        echo -e "${RED}Error: Binary '$FULL_BINARY_NAME' not found in package!${NC}"
        ls -l "$TMP_DIR"
        exit 1
    fi
    
    chmod +x "$TMP_DIR/$FULL_BINARY_NAME"
}

# 3. INSTALLATION ROUTINES
install_linux() {
    ensure_permissions

    # Stop existing
    if pgrep -f "$FULL_BINARY_NAME" > /dev/null; then
        echo "Stopping running instance..."
        pkill -f "$FULL_BINARY_NAME"
        sleep 2
        pkill -9 -f "$FULL_BINARY_NAME" 2>/dev/null
    fi

    echo "Installing binary to $TARGET_PATH..."
    sudo install -m 755 "$TMP_DIR/$FULL_BINARY_NAME" "$TARGET_PATH"

    echo "Creating Desktop Entry..."
    mkdir -p "$DESKTOP_DIR"
    cat << EOF > "$DESKTOP_DIR/$APP_NAME.desktop"
[Desktop Entry]
Type=Application
Name=VPN Watchdog
Comment=Monitor VPN Connection security
Exec=$TARGET_PATH
Icon=security-high
Terminal=false
Categories=Network;Utility;System;
EOF
    chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"
}

install_macos() {
    echo "Installing to $INSTALL_DIR..."
    
    # Kill existing
    pkill -f "$FULL_BINARY_NAME" 2>/dev/null
    
    # Copy (Try without sudo first, then with sudo)
    cp "$TMP_DIR/$FULL_BINARY_NAME" "$TARGET_PATH" || sudo cp "$TMP_DIR/$FULL_BINARY_NAME" "$TARGET_PATH"
    
    # Set Executable
    chmod +x "$TARGET_PATH"
    
    # Remove Quarantine (Gatekeeper)
    echo "Whitelisting binary (Gatekeeper)..."
    xattr -d com.apple.quarantine "$TARGET_PATH" 2>/dev/null || true
}

install_windows() {

    # Windows installation logic (via Git Bash)
    taskkill //IM "$FULL_BINARY_NAME" //F 2>/dev/null
    
    echo "Creating directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    
    echo "Copying binary..."
    cp "$TMP_DIR/$FULL_BINARY_NAME" "$TARGET_PATH"
    
    # Create Shortcut
    WIN_TARGET=$(cygpath -w "$TARGET_PATH")
    WIN_LINK_PATH=$(cygpath -w "$USERPROFILE/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/VPN Watchdog.lnk")
    
    echo "Creating Start Menu Shortcut..."
    powershell -Command "\$WshShell = New-Object -comObject WScript.Shell; \$Shortcut = \$WshShell.CreateShortcut('$WIN_LINK_PATH'); \$Shortcut.TargetPath = '$WIN_TARGET'; \$Shortcut.WorkingDirectory = '$(cygpath -w "$INSTALL_DIR")'; \$Shortcut.Save()"
}

install_files() {
    echo -e "\n${BLUE}[3/4] Installing for $OS...${NC}"
    
    if [ "$OS" == "linux" ]; then
        install_linux
    elif [ "$OS" == "darwin" ]; then
        install_macos
    elif [ "$OS" == "windows" ]; then
        install_windows
    fi
    
    # Cleanup
    rm -rf "$TMP_DIR"
    echo -e "${GREEN}Installation complete!${NC}"
    echo "Target: $TARGET_PATH"
}

# 4. UNINSTALL
uninstall_app() {
    echo -e "\n${BLUE}Uninstalling VPN Watchdog...${NC}"
    
    # 1. Stop Process
    echo "Stopping process..."
    if [ "$OS" == "windows" ]; then
        taskkill //IM "$FULL_BINARY_NAME" //F 2>/dev/null
    else
        pkill -f "$FULL_BINARY_NAME"
    fi
    
    # 2. Remove Binary
    echo "Removing Binary: $TARGET_PATH"
    if [ "$OS" == "linux" ] || [ "$OS" == "darwin" ]; then
        sudo rm -f "$TARGET_PATH"
    else
        rm -f "$TARGET_PATH"
    fi
    
    # 3. Remove Shortcuts / Desktop Files
    if [ "$OS" == "linux" ]; then
        echo "Removing Desktop Entry: $DESKTOP_DIR/$APP_NAME.desktop"
        rm -f "$DESKTOP_DIR/$APP_NAME.desktop"
        echo "Removing Autostart: $AUTOSTART_DIR/$APP_NAME.desktop"
        rm -f "$AUTOSTART_DIR/$APP_NAME.desktop"
        
    elif [ "$OS" == "windows" ]; then
        LINK="$USERPROFILE/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/VPN Watchdog.lnk"
        STARTUP_LINK="$AUTOSTART_DIR/vpn-watchdog.lnk"
        echo "Removing Shortcuts..."
        rm -f "$LINK"
        rm -f "$STARTUP_LINK"
        rm -rf "$INSTALL_DIR"
    fi

    # 4. Config (Optional - Ask user?)
    # For now, we print location but usually keep config to be nice
    echo -e "${YELLOW}Note: Configuration files were kept at:${NC}"
    echo "  $CONFIG_DIR"
    echo "To remove them, run: rm -rf \"$CONFIG_DIR\""
    
    echo -e "${GREEN}Uninstalled.${NC}"
}

# --- MAIN MENU / ROUTER ---

run_install() {
    install_dependencies
    fetch_and_unpack
    install_files
}

# --- HELP / USAGE ---
show_usage() {
    echo -e "${BLUE}VPN WATCHDOG - USAGE GUIDE${NC}"
    echo "------------------------------------------------------"
    echo "Interactive Mode:"
    echo "  ./setup.sh                (Starts the menu if no args given)"
    echo ""
    echo "CLI / Automation Mode:"
    echo "  ./setup.sh install        (Standard Installation)"
    echo "  ./setup.sh install --channel main  (Install from specific branch)"
    echo "  ./setup.sh uninstall      (Remove application and shortcuts)"
    echo ""
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  --channel NAME            Specify branch (stable, main, dev)"
    echo "------------------------------------------------------"
    exit 0
}

detect_system # Set OS and ARCH and paths

if [ "$SHOW_HELP" = true ]; then
    show_usage
fi

if [ -n "$CMD_ARG" ]; then
    # CLI Mode
    print_header
    if [ "$CMD_ARG" == "install" ]; then
        run_install
    elif [ "$CMD_ARG" == "uninstall" ]; then
        uninstall_app
    fi
elif [ "$#" -gt 0 ]; then
    # No command or no valid command arg given
    echo -e "${RED}Error: Unknown command '$1'${NC}"
    show_usage
else
    # Interactive Mode (Menu)
    print_header
    
    if [ -f "$TARGET_PATH" ]; then
        echo -e "${YELLOW}EXISTING INSTALLATION DETECTED!${NC}"
        echo "------------------------------------------------------"
        echo "Locations:"
        echo "  Binary:    $TARGET_PATH"
        echo "  Config:    $CONFIG_DIR"
        echo "  Autostart: $AUTOSTART_DIR (If enabled)"
        echo "------------------------------------------------------"
        echo ""
        echo "What do you want to do?"
        echo "  [1] Update / Re-Install (Default)"
        echo "  [2] Uninstall completely"
        echo "  [3] Cancel"
        echo ""
        read -p "Select option [1-3]: " CHOICE
        
        case "$CHOICE" in
            1|"")
                echo "Starting Installation / Update..."
                run_install
                ;;
            2)
                uninstall_app
                ;;
            3)
                echo "Aborted."
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option: $CHOICE. Aborting.${NC}"
                exit 1
                ;;
        esac
    else
        echo "No existing installation found."
        echo "Starting fresh installation..."
        echo ""
        read -p "Press ENTER to continue or Ctrl+C to cancel..."
        run_install
    fi
fi