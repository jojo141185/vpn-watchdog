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
    # 1. Clear GSettings path to avoid conflicts with host system
    if 'GSETTINGS_SCHEMA_DIR' in os.environ: 
        del os.environ['GSETTINGS_SCHEMA_DIR']
    
    # 2. Fix XDG Data Dirs (remove PyInstaller temp path from it to avoid pollution)
    if 'XDG_DATA_DIRS' in os.environ:
        meipass = sys._MEIPASS
        paths = os.environ['XDG_DATA_DIRS'].split(os.pathsep)
        clean_paths = [p for p in paths if not p.startswith(meipass)]
        os.environ['XDG_DATA_DIRS'] = os.pathsep.join(clean_paths)

    # 3. FIX FOR GI REPOSITORY / TYPELIBS (AyatanaAppIndicator)
    # PyInstaller creates a 'girepository-1.0' folder inside _MEIPASS when collecting components.
    # We must explicitly tell PyGObject where to find these .typelib files.
    base_path = sys._MEIPASS
    gi_typelib_path = os.path.join(base_path, 'girepository-1.0')
    
    if os.path.exists(gi_typelib_path):
        current_path = os.environ.get('GI_TYPELIB_PATH', '')
        if current_path:
            os.environ['GI_TYPELIB_PATH'] = f"{gi_typelib_path}{os.pathsep}{current_path}"
        else:
            os.environ['GI_TYPELIB_PATH'] = gi_typelib_path

# --- IMPORT CONFIGURATION & GI VERSION FIX ---
# It is critical to require versions BEFORE importing Gtk/AppIndicator modules.
# This suppresses warnings and helps PyInstaller hooks find the right libs.
import utils 

if sys.platform == "linux":
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        # Try to explicitly version Ayatana first (Modern)
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
        except ValueError:
            # Fallback to Legacy if necessary
            try:
                gi.require_version('AppIndicator3', '0.1')
            except ValueError:
                pass
    except ImportError:
        pass

# Ensure correct backend setup
utils.setup_linux_backend()

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
        self.gui = TrayApp(self, self.cfg)
        self.settings_open = False
        
        # Loop timers
        self.last_check_time = 0
        
        # FLICKER PREVENTION: Track last visual state
        self.last_visual_state = {
            "status": None,
            "country": None
        }

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
        # Force redraw next loop
        self.last_visual_state["status"] = None

    def stop(self):
        self.running = False
        self.gui.stop()
        os._exit(0)
    
    def open_settings(self):
        if self.settings_open: return
        self.settings_open = True
        try: 
            SettingsDialog(self.cfg) # Blocks execution until window closes
            
            # This code runs after settings window is closed
            logger.info("Settings closed. Forcing immediate re-check...")
            self.checker.force_checks()
            self.last_check_time = 0 # Force main loop update
            
        except Exception as e: 
            logger.error(f"Error in Settings: {e}")
        finally: 
            self.settings_open = False

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
                now = time.time()
                interval = int(self.cfg.get("check_interval"))
                
                # OPTIMIZATION: If we are scanning (gray icon), we poll faster (every 1s)
                # to update the icon immediately when API results arrive.
                # Since 'status' is now determined by core, we check self.status which is updated below.
                if self.status == "scanning" or self.status == "initializing":
                    interval = 1
                    
                if now - self.last_check_time < interval:
                    time.sleep(0.5) 
                    continue
                
                self.last_check_time = now

                # 4. Perform Checks
                # The result is now the single unified state object
                state_obj = self.checker.check_status()
                
                new_status = state_obj.get("status", "unsafe") # safe, unsafe, scanning
                country = state_obj.get("country", "??")
                details = state_obj.get("summary_details", "")

                # 5. UI Update Logic (Anti-Flicker)
                has_changed = (new_status != self.status)
                visual_changed = (new_status != self.last_visual_state["status"] or country != self.last_visual_state["country"])
                
                if has_changed:
                    logger.info(f"Status change: {self.status} -> {new_status} ({details})")
                    self.status = new_status
                    
                    # Notify only if status actually changed (e.g. Safe -> Unsafe)
                    try:
                        self.gui.update_icon(self.status, country=country, notify=True)
                        # Update tracker
                        self.last_visual_state["status"] = self.status
                        self.last_visual_state["country"] = country
                    except Exception as e: logger.error(f"Failed to update Icon (Notify): {e}")

                elif visual_changed:
                    # No status change (e.g. Safe -> Safe) but Country changed or initial render
                    try: 
                        self.gui.update_icon(self.status, country=country, notify=False)
                        self.last_visual_state["status"] = self.status
                        self.last_visual_state["country"] = country
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