import threading
import time
import datetime
import logging
import os
import sys

# =============================================================================
# CRITICAL FIX FOR LINUX / GNOME / PYINSTALLER
# =============================================================================
if getattr(sys, 'frozen', False):
    if 'GSETTINGS_SCHEMA_DIR' in os.environ: del os.environ['GSETTINGS_SCHEMA_DIR']
    if 'XDG_DATA_DIRS' in os.environ:
        meipass = sys._MEIPASS
        paths = os.environ['XDG_DATA_DIRS'].split(os.pathsep)
        clean_paths = [p for p in paths if not p.startswith(meipass)]
        os.environ['XDG_DATA_DIRS'] = os.pathsep.join(clean_paths)

from config import ConfigManager
import utils 
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
        self.gui = TrayApp(self, self.cfg)
        self.settings_open = False
        
        # Loop timers
        self.last_check_time = 0

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
        if self.settings_open: return
        self.settings_open = True
        try: SettingsDialog(self.cfg)
        except Exception as e: logger.error(f"Error in Settings: {e}")
        finally: self.settings_open = False

    def monitor_loop(self):
        logger.info("Loop started.")
        time.sleep(2)

        while self.running:
            try:
                # 1. Config Check
                valid_ifaces = self.cfg.get("valid_interfaces")
                if not valid_ifaces and not self.settings_open:
                     if self.status != "initializing":
                         self.status = "initializing"
                         self.gui.update_icon("paused")
                         self.gui.icon.notify("VPN Watchdog", "Please configure network interfaces.")
                     time.sleep(5)
                     continue
                
                if not valid_ifaces:
                    time.sleep(1)
                    continue

                # 2. Pause Logic
                if self.paused:
                    if datetime.datetime.now() > self.pause_until: self.resume()
                    else:
                        time.sleep(1)
                        continue

                # 3. Time Check (Local Interval)
                # We loop every 1s to allow responsive GUI/Pause, but only check at interval
                now = time.time()
                interval = int(self.cfg.get("check_interval"))
                if now - self.last_check_time < interval:
                    time.sleep(1)
                    continue
                
                self.last_check_time = now

                # 4. Perform Checks
                # check_status() handles local + public logic internally
                result = self.checker.check_status()
                
                is_secure = result["secure"]
                country = result.get("country", "??")
                
                new_status = "safe" if is_secure else "unsafe"

                if new_status != self.status:
                    logger.info(f"Status change: {self.status} -> {new_status} ({result['details']})")
                    self.status = new_status
                    try: self.gui.update_icon(self.status, country=country)
                    except Exception as e: logger.error(f"Failed to update Icon: {e}")
                else:
                    # Update icon anyway if country changed or just to refresh tooltip
                    try: self.gui.update_icon(self.status, country=country)
                    except: pass
                
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(5)

    def start(self):
        t = threading.Thread(target=self.monitor_loop, daemon=True)
        t.start()
        if not self.cfg.get("valid_interfaces"):
             logger.info("First run detected. Please open settings from Tray.")
        try: self.gui.run()
        except KeyboardInterrupt: self.stop()

if __name__ == "__main__":
    Application().start()