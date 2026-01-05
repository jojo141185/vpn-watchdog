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
  - 🟢 **Green:** Protected (Traffic flows through VPN).
  - 🔴 **Red:** Unsafe! (VPN dropped or traffic bypasses tunnel).
  - 🟡 **Yellow:** Monitoring paused.
- **Robust Checks:**
  - Uses direct Kernel Routing checks (`ip route`, PowerShell `Find-NetRoute`) instead of simple IP comparison.
  - Detects if traffic bypasses the VPN interface (Split Tunneling leaks).
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

## How it works
The app checks your system's routing table every 5 seconds.
1. It identifies the interface used for Internet traffic (Default Gateway).
2. It compares this interface against the "Valid Interfaces" list you selected in Settings.
3. If the active interface matches one of your selected VPN adapters (e.g., `tun0`, `NordLynx`), it shows Green.
4. If traffic flows through your physical Ethernet/WiFi adapter (`eth0`, `wlan0`), it shows Red.

## License
MIT License