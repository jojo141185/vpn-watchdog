import threading
import time
import datetime
import logging
import os
import sys

# =============================================================================
# CRITICAL FIX FOR GNOME / PYINSTALLER
# =============================================================================
# PyInstaller sets 'GSETTINGS_SCHEMA_DIR' to its internal temp directory.
# This causes crashes on GNOME (GLib-GIO-ERROR) because system schemas
# are missing or mismatched. We remove this variable so the app uses the
# system schemas (/usr/share/glib-2.0/schemas).
# =============================================================================
if getattr(sys, 'frozen', False):
    if 'GSETTINGS_SCHEMA_DIR' in os.environ:
        del os.environ['GSETTINGS_SCHEMA_DIR']

# Load Modules
from config import ConfigManager
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
        # Immediate check follows in loop

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
                    logger.warning("No interfaces configured. Waiting for configuration...")
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

                # The actual check
                is_secure = self.checker.is_secure()
                new_status = "safe" if is_secure else "unsafe"

                # UI Update only on change
                if new_status != self.status:
                    logger.info(f"Status change: {self.status} -> {new_status}")
                    self.status = new_status
                    self.gui.update_icon(self.status)
                
                # Check Interval
                interval = int(self.cfg.get("check_interval"))
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(5)

    def start(self):
        # 0. FIRST RUN CHECK
        if not self.cfg.get("valid_interfaces"):
            logger.info("First run or no interfaces selected. Opening Settings...")
            try:
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