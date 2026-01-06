import threading
import time
import datetime
import logging
import os
import sys

# =============================================================================
# CRITICAL FIX FOR LINUX / GNOME / PYINSTALLER
# =============================================================================
# PyInstaller bundles glib schemas (from the build OS) which are often 
# incompatible with the target host system (causing GLib-GIO-ERROR).
# We must force the app to ignore bundled schemas and use the system ones.
# =============================================================================
if getattr(sys, 'frozen', False):
    # 1. Remove GSETTINGS_SCHEMA_DIR so it defaults to system paths
    if 'GSETTINGS_SCHEMA_DIR' in os.environ:
        del os.environ['GSETTINGS_SCHEMA_DIR']
    
    # 2. Clean XDG_DATA_DIRS
    # PyInstaller prepends its temp directory (sys._MEIPASS) to XDG_DATA_DIRS.
    # This makes GLib look for schemas in the temp folder first.
    # We filter out the temp path to force lookups in /usr/share and ~/.local/share.
    if 'XDG_DATA_DIRS' in os.environ:
        meipass = sys._MEIPASS
        # Split paths, filter out the PyInstaller temp dir, join back
        paths = os.environ['XDG_DATA_DIRS'].split(os.pathsep)
        clean_paths = [p for p in paths if not p.startswith(meipass)]
        os.environ['XDG_DATA_DIRS'] = os.pathsep.join(clean_paths)

# Load Modules
from config import ConfigManager
# Import utils first to init backend before GUI imports
import utils 

# --- INIT LINUX BACKEND (Ayatana/AppIndicator) ---
# Must be called before importing pystray/gui via core
utils.setup_linux_backend()

from core import VPNChecker
from gui import TrayApp, SettingsDialog

logger = logging.getLogger("VPNWatchdog")

class Application:
    def __init__(self):
        self.cfg = ConfigManager()
        self.checker = VPNChecker(self.cfg)
        
        self.running = True
        self.paused = False
        self.pause_until = None
        self.status = "initializing"
        
        # GUI Instance
        self.gui = TrayApp(self, self.cfg)

    def pause(self, minutes):
        self.paused = True
        self.pause_until = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        self.status = "paused"
        logger.info(f"Paused for {minutes} minutes.")
        self.gui.update_icon(self.status, self.pause_until)

    def resume(self):
        self.paused = False
        self.pause_until = None
        logger.info("Monitoring resumed.")

    def stop(self):
        self.running = False
        self.gui.stop()
        os._exit(0)

    def monitor_loop(self):
        logger.info("Loop started.")
        while self.running:
            try:
                # 1. Safety Check: If no interfaces are configured
                valid_ifaces = self.cfg.get("valid_interfaces")
                if not valid_ifaces:
                    # Don't spam logs, just wait
                    if self.status != "initializing":
                        self.status = "initializing"
                        self.gui.update_icon(self.status)
                    time.sleep(2)
                    continue

                if self.paused:
                    if datetime.datetime.now() > self.pause_until:
                        self.resume()
                    else:
                        time.sleep(1)
                        continue

                # The actual check (Now includes Timeouts in core.py)
                is_secure = self.checker.is_secure()
                new_status = "safe" if is_secure else "unsafe"

                # UI Update only on change
                if new_status != self.status:
                    logger.info(f"Status change: {self.status} -> {new_status}")
                    self.status = new_status
                    # Wrap GUI update in try/except to prevent thread crashes
                    try:
                        self.gui.update_icon(self.status)
                    except Exception as e:
                        logger.error(f"Failed to update Icon: {e}")
                
                # Check Interval
                interval = int(self.cfg.get("check_interval"))
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                # Wait a bit before retrying to prevent CPU spikes in error loops
                time.sleep(5)

    def start(self):
        # 0. FIRST RUN CHECK
        if not self.cfg.get("valid_interfaces"):
            logger.info("First run or no interfaces selected. Opening Settings...")
            try:
                # Just catch any potential GUI startup errors
                SettingsDialog(self.cfg)
            except Exception as e:
                logger.error(f"Could not start Settings Dialog: {e}")

        # Start Background Thread
        t = threading.Thread(target=self.monitor_loop, daemon=True)
        t.start()
        
        # GUI blocks Main Thread
        try:
            self.gui.run()
        except KeyboardInterrupt:
            self.stop()

if __name__ == "__main__":
    Application().start()