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
        
        # Flags
        self.settings_open = False

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
    
    def open_settings(self):
        """Safely opens settings avoiding multiple instances"""
        if self.settings_open:
            return
        
        logger.info("Opening Settings...")
        self.settings_open = True
        try:
            # This blocks the thread calling it, so we usually run it in a separate thread if called from loop
            # BUT: Tkinter usually wants main thread. Since pystray controls main, 
            # we open this and it will block until closed. This is fine for settings.
            SettingsDialog(self.cfg)
        except Exception as e:
            logger.error(f"Error in Settings: {e}")
        finally:
            self.settings_open = False

    def monitor_loop(self):
        logger.info("Loop started.")
        
        # Initial wait to let GUI settle
        time.sleep(2)

        while self.running:
            try:
                # 1. Check if configured
                valid_ifaces = self.cfg.get("valid_interfaces")
                
                # FIRST RUN LOGIC:
                # If no interfaces are set, we assume first run.
                # We trigger the settings dialog ONCE.
                if not valid_ifaces and not self.settings_open:
                     logger.info("No config detected. Triggering settings...")
                     # Use pystray's menu action mechanism or just run it?
                     # Since we are in a background thread, running GUI directly is dangerous for Tkinter.
                     # However, creating a new Tk root in a thread works on Windows usually, 
                     # but let's just warn and wait for user to click tray icon.
                     self.status = "initializing"
                     self.gui.update_icon("paused") # Use pause icon to indicate 'idle'
                     self.gui.icon.notify("VPN Watchdog", "Please configure network interfaces via the Tray Menu.")
                     time.sleep(10) # Remind every 10s
                     continue
                
                if not valid_ifaces:
                    time.sleep(1)
                    continue

                if self.paused:
                    if datetime.datetime.now() > self.pause_until:
                        self.resume()
                    else:
                        time.sleep(1)
                        continue

                # The actual check (High Performance via netifaces)
                is_secure = self.checker.is_secure()
                new_status = "safe" if is_secure else "unsafe"

                if new_status != self.status:
                    logger.info(f"Status change: {self.status} -> {new_status}")
                    self.status = new_status
                    try:
                        self.gui.update_icon(self.status)
                    except Exception as e:
                        logger.error(f"Failed to update Icon: {e}")
                
                # Check Interval
                interval = int(self.cfg.get("check_interval"))
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(5)

    def start(self):
        # Start Background Thread
        t = threading.Thread(target=self.monitor_loop, daemon=True)
        t.start()
        
        # Check config on start - if missing, we just launch the tray.
        # The Monitor Loop will notify the user to open settings.
        # This prevents the process exit issue.
        if not self.cfg.get("valid_interfaces"):
             logger.info("First run detected. Please open settings from Tray.")

        # GUI blocks Main Thread
        try:
            self.gui.run()
        except KeyboardInterrupt:
            self.stop()

if __name__ == "__main__":
    Application().start()