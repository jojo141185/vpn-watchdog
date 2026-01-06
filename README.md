# 🛡️ VPN Watchdog

A modular, cross-platform system tray application that monitors your VPN connection security using multiple independent guards.

![License](https://img.shields.io/github/license/jojo141185/vpn-watchdog)
![Release](https://img.shields.io/github/v/release/jojo141185/vpn-watchdog)

**Supported Platforms:**
- 🐧 **Linux** (Ubuntu, Kubuntu, Fedora, etc.)
- 🪟 **Windows** (10/11)
- 🍎 **macOS**

## Features

- **Visual Feedback:**
  - 🟢 **Green:** Protected (All active checks passed).
  - 🔴 **Red:** Unsafe! (VPN dropped, IP leak, or DNS leak detected).
  - 🟡 **Yellow:** Monitoring paused.
  - **Country Overlay:** Shows your current public IP country code directly on the icon.
- **Dashboard:**
  - Real-time Status Overview of all modules.
  - Live Logs viewer.
- **3 Independent Detection Modules:**
  1.  **Routing Guard:** Monitors local network interfaces.
  2.  **Connectivity Guard:** Monitors Public IP, ISP, and Location.
  3.  **DNS Guard:** Checks for DNS Leaks (DNS servers belonging to home ISP).

## How it works (The 3 Guards)

The app combines three security layers. You can enable/disable each independently in Settings.

### 1. Routing Guard (Local Interface)
Ensures that your operating system is routing traffic through the correct network adapter (e.g., `tun0`, `NordLynx`).
*   **Performance Mode (Windows):** Reads the Default Gateway from memory (Zero CPU load).
*   **Precision Mode (Linux/Mac):** Queries Kernel Routing Table for exact paths.
*   **Why use it?** Immediate detection if the VPN client crashes or disconnects locally.

### 2. Connectivity Guard (Public IP)
Verifies how the internet "sees" you by querying an external API (e.g., ipwho.is).
*   **Strategies:**
    *   **Geo-Fence:** Alerts if your country matches your "Home Country" (e.g., DE).
    *   **ISP Blacklist:** Alerts if your detected ISP matches your "Home ISP" (e.g., Telekom).
    *   **DynDNS Match:** Resolves your home DynDNS and alerts if your public IP matches it (Proof you are not tunneling).
*   **Why use it?** Essential for **Router-based VPNs** where the local PC interface stays "Ethernet" but the public IP should change.

### 3. DNS Guard (Leak Protection)
Performs a DNS Leak Test (similar to dnsleaktest.com) in the background.
*   **Mechanism:** Resolves random subdomains to identify which DNS servers answer the query.
*   **Alert:** Turns RED if a DNS server owned by your "Home ISP" is detected.
*   **Why use it?** Prevents your ISP from logging your browsing history even if the VPN is active.

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
sudo apt install python3-tk gir1.2-appindicator3-0.1 libappindicator3-1 python3-pil.imagetk
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

## License
MIT License