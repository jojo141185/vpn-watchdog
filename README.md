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
- **High Performance & Configurable:**
  - Choose between **Performance Mode** (Zero CPU load via memory readout) and **Precision Mode** (Exact Kernel Routing checks).
  - Defaults to the best strategy for your OS automatically.
- **Robust Checks:**
  - **Dual-Stack Monitoring:** Checks routing for both **IPv4** and **IPv6**. If your VPN supports IPv4 but your OS leaks traffic via IPv6, the app will detect it.
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
The app runs a check every 5 seconds. You can configure the **Detection Method** in settings:

1.  **Auto (Recommended):**
    *   **Windows:** Uses *Performance Mode* (to avoid high CPU usage caused by PowerShell).
    *   **Linux/macOS:** Uses *Precision Mode* (native kernel commands are fast and precise).

2.  **Performance Mode:**
    *   Reads the **Default Gateway** directly from memory using the `netifaces` library.
    *   Extremely fast (< 0.1ms), Zero CPU load.
    *   Ideal for Windows.

3.  **Precision Mode:**
    *   Queries the Kernel Routing Table for specific targets (`1.1.1.1` and IPv6 `2606:4700:4700::1111`).
    *   Detects Split-Tunneling configurations more accurately.
    *   Uses `ip route` (Linux), `route get` (macOS), or `Find-NetRoute` (Windows/PowerShell).

**Verification Process:**
*   **Dual-Stack:** It validates interfaces for **IPv4** AND **IPv6**. If IPv6 is enabled but bypassing the VPN (Leak), it alerts you.
*   **Status Decision:**
    *   **GREEN:** Active routes found, and **ALL** interfaces used for Internet traffic match your "Valid Interfaces" list.
    *   **RED:** Traffic is flowing through a non-allowed interface (e.g., direct Wi-Fi/Ethernet).
    *   **RED (Fail-Safe):** If no route/gateway is found (e.g., network cable unplugged), it defaults to a warning state.

## License
MIT License