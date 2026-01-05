#!/bin/bash

# =============================================================================
# VPN WATCHDOG - UNIVERSAL SETUP MANAGER
# =============================================================================
# Install, Update, and Uninstall script.
# Supported Platforms: Linux, macOS (Darwin), Windows (Git Bash/MinGW)
#
# Usage:
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
        BINARY_EXT=""
        NEEDS_SUDO=true
    elif [ "$OS" == "darwin" ]; then
        INSTALL_DIR="/Applications"
        # macOS doesn't use XDG desktop files, but we set a dummy path
        DESKTOP_DIR="$HOME/Desktop" 
        BINARY_EXT=""
        # Sudo needed if writing to /Applications sometimes, but usually user-writable? 
        # Standard /Applications requires root or admin.
        NEEDS_SUDO=true 
    elif [ "$OS" == "windows" ]; then
        # In Git Bash, $HOME usually maps to C:\Users\Username
        # We use a local appdata folder logic
        INSTALL_DIR="$HOME/AppData/Local/VPNWatchdog"
        DESKTOP_DIR="$HOME/Desktop" # Simplified
        BINARY_EXT=".exe"
        NEEDS_SUDO=false # Windows (Git Bash) usually doesn't have sudo
    fi

    FULL_BINARY_NAME="${BINARY_NAME}${BINARY_EXT}"
    PACKAGE_FILENAME="vpn-watchdog-${OS}-${ARCH}.zip"
}

# --- PARSE ARGUMENTS ---
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    if [[ "${args[i]}" == "--channel" ]]; then
        CHANNEL="${args[i+1]}"
    fi
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
    detect_system # Run detection here
    get_download_url
    echo -e "Platform: ${GREEN}$OS ($ARCH)${NC}"
    echo -e "Target:   ${YELLOW}$VERSION_MSG${NC}"
    echo -e "Install:  $INSTALL_DIR/$FULL_BINARY_NAME"
    echo "------------------------------------------------------"
}

ensure_permissions() {
    if [ "$NEEDS_SUDO" = true ] && [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Note: Admin/Sudo privileges required for installation.${NC}"
        # Only invoke sudo if not root. 
        # We don't use 'sudo -v' blindly because it might hang in non-interactive shells.
        # Instead, we rely on sudo calls in install_files.
    fi
}

# 1. INSTALL DEPENDENCIES
install_dependencies() {
    echo -e "\n${BLUE}[1/4] Checking system dependencies...${NC}"
    
    if [ "$OS" == "linux" ]; then
        if command -v apt-get &> /dev/null; then
            echo "Detected: APT"
            sudo apt-get update -qq
            # INSTALL BOTH: Legacy and Ayatana (Modern) to cover all bases
            sudo apt-get install -y -qq \
                gir1.2-appindicator3-0.1 \
                libappindicator3-1 \
                gir1.2-ayatanaappindicator3-0.1 \
                libayatana-appindicator3-1 \
                python3-tk xapp unzip
        elif command -v dnf &> /dev/null; then
            echo "Detected: DNF"
            # Fedora usually maps libappindicator to ayatana automatically, but we ensure gtk3 support
            sudo dnf install -y libappindicator-gtk3 libayatana-appindicator-gtk3 python3-tkinter unzip
        elif command -v pacman &> /dev/null; then
            echo "Detected: Pacman"
            sudo pacman -S --noconfirm libappindicator-gtk3 libayatana-appindicator python-gobject tk unzip
        else
            echo -e "${RED}Warning: Manual dependency check required.${NC}"
        fi
    elif [ "$OS" == "darwin" ]; then
        # macOS check
        if ! command -v unzip &> /dev/null; then
            echo -e "${RED}Error: 'unzip' is missing.${NC}"
            exit 1
        fi
        echo "macOS dependencies look good (assuming standard libs)."
    elif [ "$OS" == "windows" ]; then
        if ! command -v powershell &> /dev/null; then
            echo -e "${RED}Error: PowerShell is required for Windows installation.${NC}"
            exit 1
        fi
        if ! command -v unzip &> /dev/null; then
             echo -e "${YELLOW}Warning: 'unzip' not found. Ensure you can extract the files.${NC}"
             # Windows often has tar/unzip in Git Bash, so we proceed.
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
    
    # Check for local file first (same folder as script)
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
            echo "1. Check internet connection."
            echo "2. Check if a build for '$OS-$ARCH' exists."
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
    TARGET_PATH="$INSTALL_DIR/$FULL_BINARY_NAME"

    # Stop existing
    if pgrep -f "$FULL_BINARY_NAME" > /dev/null; then
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
    # macOS installation logic (similar to setup.command)
    TARGET_PATH="$INSTALL_DIR/$FULL_BINARY_NAME"
    
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
    
    echo -e "${YELLOW}Note: You can run it via Terminal: $TARGET_PATH${NC}"
}

install_windows() {
    # Windows installation logic (via Git Bash)
    TARGET_PATH="$INSTALL_DIR/$FULL_BINARY_NAME"
    
    # Kill process (using windows command taskkill)
    taskkill //IM "$FULL_BINARY_NAME" //F 2>/dev/null
    
    echo "Creating directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    
    echo "Copying binary..."
    cp "$TMP_DIR/$FULL_BINARY_NAME" "$TARGET_PATH"
    
    # Create Shortcut using PowerShell
    # We need to translate unix paths to windows paths for PowerShell
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
}

# 4. UNINSTALL
uninstall_app() {
    print_header
    echo -e "${RED}WARNING: Uninstalling${NC}"
    
    if [ "$OS" == "linux" ]; then
        pkill -f "$FULL_BINARY_NAME"
        sudo rm -f "$INSTALL_DIR/$FULL_BINARY_NAME"
        rm -f "$DESKTOP_DIR/$APP_NAME.desktop"
        
    elif [ "$OS" == "darwin" ]; then
        pkill -f "$FULL_BINARY_NAME"
        rm -f "$INSTALL_DIR/$FULL_BINARY_NAME" || sudo rm -f "$INSTALL_DIR/$FULL_BINARY_NAME"
        
    elif [ "$OS" == "windows" ]; then
        taskkill //IM "$FULL_BINARY_NAME" //F 2>/dev/null
        rm -f "$INSTALL_DIR/$FULL_BINARY_NAME"
        rm -f "$USERPROFILE/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/VPN Watchdog.lnk"
    fi
    
    echo -e "${GREEN}Removed.${NC}"
}

# --- CLI ROUTER ---
if [[ " $@ " =~ " install " ]] || [[ "$1" == "install" ]]; then
    print_header
    install_dependencies
    fetch_and_unpack
    install_files
elif [[ " $@ " =~ " uninstall " ]] || [[ "$1" == "uninstall" ]]; then
    detect_system # Need to know OS to uninstall correctly
    uninstall_app
else
    echo "Usage:"
    echo "  ./setup.sh install"
    echo "  ./setup.sh install --channel main"
    echo "  ./setup.sh uninstall"
fi