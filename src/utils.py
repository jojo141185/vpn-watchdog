import os
import sys
import platform
import logging

logger = logging.getLogger("VPNWatchdog")

# --- C-LEVEL SILENCER ---
# Suppresses GTK/C-level warnings in the terminal
class CLevelSilencer:
    def __enter__(self):
        # On Windows, dup2 can be problematic or unnecessary for GTK warnings
        if platform.system() == "Windows":
            return
        
        try:
            self.save_stderr = os.dup(sys.stderr.fileno())
            self.devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(self.devnull, sys.stderr.fileno())
        except Exception:
            # Fallback if no console is attached
            self.save_stderr = None

    def __exit__(self, exc_type, exc_value, traceback):
        if platform.system() == "Windows" or self.save_stderr is None:
            return
            
        try:
            os.dup2(self.save_stderr, sys.stderr.fileno())
            os.close(self.devnull)
        except Exception:
            pass

# --- AUTOSTART LOGIC ---
def get_autostart_path():
    system = platform.system()
    if system == "Linux":
        return os.path.expanduser("~/.config/autostart/vpn-watchdog.desktop")
    elif system == "Windows":
        return os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup\vpn-watchdog.lnk')
    elif system == "Darwin": # macOS
        return os.path.expanduser("~/Library/LaunchAgents/com.vpnwatchdog.plist")
    return None

def enable_autostart():
    path = get_autostart_path()
    if not path: return

    # Get path to executable
    if getattr(sys, 'frozen', False):
        # PyInstaller Executable
        exec_cmd = sys.executable
    else:
        # Python Script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        main_script = os.path.join(base_dir, "main.py")
        exec_cmd = f"{sys.executable} {main_script}"

    # --- LINUX ---
    if platform.system() == "Linux":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Name=VPN Watchdog
Exec={exec_cmd}
Icon=security-high
Comment=Monitor VPN Connection
X-GNOME-Autostart-enabled=true
Terminal=false
"""
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, 0o755)
        logger.info(f"Linux Autostart enabled: {path}")

    # --- WINDOWS ---
    elif platform.system() == "Windows":
        import subprocess
        vbs = f"""
        Set oWS = WScript.CreateObject("WScript.Shell")
        Set oLink = oWS.CreateShortcut("{path}")
        oLink.TargetPath = "{exec_cmd}"
        oLink.WorkingDirectory = "{os.path.dirname(exec_cmd)}"
        oLink.Save
        """
        vbs_path = os.path.join(os.getenv('TEMP'), "create_shortcut.vbs")
        with open(vbs_path, "w") as f:
            f.write(vbs)
        subprocess.call(['cscript', '//Nologo', vbs_path])
        os.remove(vbs_path)
        logger.info("Windows Autostart enabled.")

    # --- MACOS ---
    elif platform.system() == "Darwin":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # MacOS LaunchAgent Plist
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vpnwatchdog.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exec_cmd}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        with open(path, "w") as f:
            f.write(plist_content)
        logger.info(f"macOS Autostart enabled: {path}")

def disable_autostart():
    path = get_autostart_path()
    if path and os.path.exists(path):
        os.remove(path)
        logger.info("Autostart removed.")

def is_autostart_enabled():
    path = get_autostart_path()
    return path and os.path.exists(path)