# 🛡️ VPN Watchdog

A lightweight, cross-platform system tray application that monitors your VPN connection security.

![License](https://img.shields.io/github/license/jojo141185/vpn-watchdog)
![Release](https://img.shields.io/github/v/release/jojo141185/vpn-watchdog)

**Supported Platforms:**
- 🐧 **Linux** (Ubuntu, Kubuntu, Fedora, etc.)
- 🪟 **Windows** (10/11)
- 🍎 **macOS**

## Features

- **Visual Feedback:**
  - 🟢 **Green:** Protected (All active traffic flows through VPN).
  - 🔴 **Red:** Unsafe! (VPN dropped or traffic bypasses tunnel).
  - 🟡 **Yellow:** Monitoring paused.
- **Robust Checks:**
  - **Dual-Stack Monitoring:** Checks routing for both **IPv4** and **IPv6**. If your VPN supports IPv4 but your OS leaks traffic via IPv6, the app will detect it.
  - **Kernel Routing Table:** Uses direct OS commands (`ip route`, PowerShell `Find-NetRoute`, macOS `route get`) instead of unreliable IP comparisons.
  - **Fail-Safe:** If the network hangs or detection times out (e.g., after Sleep Mode), it defaults to "Unsafe" to warn you.
- **GUI Config:** Interface selection via Checkboxes.
- **Auto-Pause:** Pause monitoring for 5m, 10m, 1h, 12h via Context Menu.
- **Autostart:** Automatically starts with your system (Linux .desktop, Windows Registry/Startup, Mac LaunchAgent).

## Installation

### 🐧 Linux (Easy Install)
Run this command to download and install the latest version automatically:

```bash
bash <(curl -sL https://raw.githubusercontent.com/jojo141185/vpn-watchdog/main/setup/setup.sh) install
```

### 🪟 Windows & 🍎 macOS
1. Go to the [Releases Page](https://github.com/jojo141185/vpn-watchdog/releases).
2. Download the executable for your system (`vpn-watchdog-windows.exe` or `vpn-watchdog-macos`).
3. Run it.

## Development / Building from Source

### Prerequisites
- Python 3.8+
- `pip`

**Linux specific:**
```bash
sudo apt install python3-tk gir1.2-appindicator3-0.1 libappindicator3-1
```

### Setup
1. Clone repository:
   ```bash
   git clone https://github.com/jojo141185/vpn-watchdog.git
   cd vpn-watchdog
   ```
2. Create virtual environment:
   ```bash
   python3 -m venv venv --system-site-packages
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running Locally
```bash
python3 src/main.py
```

### Building Binaries (PyInstaller)
To create a standalone executable:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --clean --name="vpn-watchdog" src/main.py
```
The output file will be in the `dist/` folder.

## How it works (Detection Logic)
The app runs a check every 5 seconds to ensure your traffic is secure. Here is the exact logic:

1.  **Dual-Stack Probe:**
    The app queries the operating system for the active routing interface for two specific targets:
    *   **IPv4:** `1.1.1.1` (Cloudflare)
    *   **IPv6:** `2606:4700:4700::1111` (Cloudflare)

2.  **OS-Specific Commands:**
    *   **Windows:** Uses PowerShell `Find-NetRoute` (exported as JSON for reliability) to handle complex routing tables correctly.
    *   **Linux:** Uses `ip route get`.
    *   **macOS:** Uses `route get` (with `-inet6` flag for IPv6).

3.  **Verification:**
    *   It compares the detected interfaces against your **"Valid Interfaces"** list.
    *   If **IPv6** is enabled on your PC but not tunneled by the VPN (IPv6 Leak), the app detects traffic flowing through your physical card (e.g., `Ethernet`) and immediately turns **RED**.
    *   If a protocol is disabled on your system (e.g., no IPv6 address), it is ignored to prevent false alarms.

4.  **Status Decision:**
    *   **GREEN:** At least one active route was found, and **ALL** active routes match your allowed VPN interfaces.
    *   **RED:** Traffic is flowing through a non-allowed interface (e.g., direct Wi-Fi/Ethernet).
    *   **RED (Fail-Safe):** If the check times out (system hang) or no routes are found (network down), it defaults to unsafe/warning.

## License
MIT License