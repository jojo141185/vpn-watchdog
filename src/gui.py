import tkinter as tk
from tkinter import ttk
import webbrowser
import logging
import platform
from PIL import Image, ImageDraw
from pystray import Icon as TrayIcon, Menu, MenuItem
import utils
from core import VPNChecker 
# Import dynamic version info
import version 

logger = logging.getLogger("VPNWatchdog")

# Constants
GITHUB_URL = "https://github.com/jojo141185/vpn-watchdog"
DONATE_URL = "https://github.com/sponsors/jojo141185" 
AUTHOR = "jojo141185"

class ScrollableFrame(ttk.Frame):
    """
    Helper widget providing a scrollable container.
    """
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # Create Canvas
        # Highlightthickness creates a visible border
        self.canvas = tk.Canvas(self, borderwidth=0, background="#ffffff", 
                                highlightthickness=1, highlightbackground="#a0a0a0")
        
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Inner Frame holding the content
        self.scrollable_content = tk.Frame(self.canvas, background="#ffffff")

        # Adjust scroll region when content size changes
        self.scrollable_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mousewheel binding (Cross-Platform)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel) # Windows/macOS
        self.canvas.bind_all("<Button-4>", self._on_linux_scroll_up)   # Linux
        self.canvas.bind_all("<Button-5>", self._on_linux_scroll_down) # Linux

    def _on_mousewheel(self, event):
        # Windows/macOS
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_linux_scroll_up(self, event):
        self.canvas.yview_scroll(-1, "units")
    
    def _on_linux_scroll_down(self, event):
        self.canvas.yview_scroll(1, "units")


class SettingsDialog:
    def __init__(self, config_manager):
        self.cfg = config_manager
        # Use a fresh checker instance here to force-refresh list if needed
        self.checker = VPNChecker(self.cfg) 
        
        self.root = tk.Tk()
        self.root.title("VPN Watchdog Settings")
        
        # Slightly taller to accommodate new options
        w, h = 550, 650
        ws, hs = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{int((ws-w)/2)}+{int((hs-h)/2)}")
        
        style = ttk.Style()
        style.theme_use('clam')

        # --- TABS ---
        tab_control = ttk.Notebook(self.root)
        
        self.tab_general = ttk.Frame(tab_control)
        self.tab_interfaces = ttk.Frame(tab_control)
        self.tab_about = ttk.Frame(tab_control)
        
        tab_control.add(self.tab_general, text='General')
        tab_control.add(self.tab_interfaces, text='VPN Interfaces')
        tab_control.add(self.tab_about, text='About')
        
        tab_control.pack(expand=1, fill="both", padx=10, pady=10)

        self.build_general_tab()
        self.build_interfaces_tab()
        self.build_about_tab()

        # --- FOOTER ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Save & Close", command=self.save_and_close).pack(side="right")

        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        
        # Handle manual close via X button
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.root.mainloop()

    # --- TAB 1: GENERAL ---
    def build_general_tab(self):
        content = ttk.Frame(self.tab_general, padding=15)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="System Configuration", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

        # 1. Autostart
        grp_sys = ttk.LabelFrame(content, text=" Startup ", padding=15)
        grp_sys.pack(fill="x", pady=5)
        
        self.var_autostart = tk.BooleanVar(value=utils.is_autostart_enabled())
        ttk.Checkbutton(grp_sys, text="Start automatically with System", 
                        variable=self.var_autostart).pack(anchor="w")

        # 2. Advanced Detection Settings
        grp_adv = ttk.LabelFrame(content, text=" Advanced ", padding=15)
        grp_adv.pack(fill="x", pady=10)

        ttk.Label(grp_adv, text="Detection Method:").pack(anchor="w")
        self.var_mode = tk.StringVar(value=self.cfg.get("detection_mode"))
        
        # Map config values to display names
        modes = {
            "Auto (Recommended)": "auto",
            "Performance (Fastest)": "performance",
            "Precision (Slower)": "precision"
        }
        # Invert dict for lookups
        self.modes_map = {v: k for k, v in modes.items()}
        self.modes_rev = modes
        
        cb_mode = ttk.Combobox(grp_adv, textvariable=self.var_mode, 
                               values=list(modes.keys()), state="readonly")
        
        # Set current selection correctly based on config value
        current_val = self.cfg.get("detection_mode")
        if current_val in self.modes_map:
            cb_mode.set(self.modes_map[current_val])
        else:
            cb_mode.set("Auto (Recommended)")
            
        cb_mode.pack(fill="x", pady=5)
        
        ttk.Label(grp_adv, text="Use 'Performance' on Windows to reduce CPU load.\nUse 'Precision' on Linux/Mac for best accuracy.", 
                  font=("Arial", 8), foreground="gray").pack(anchor="w")

        # 3. Logging
        grp_log = ttk.LabelFrame(content, text=" Debugging ", padding=15)
        grp_log.pack(fill="x", pady=10)
        
        ttk.Label(grp_log, text="Log Level (Terminal Output):").pack(anchor="w")
        self.var_log = tk.StringVar(value=self.cfg.get("log_level"))
        cb_log = ttk.Combobox(grp_log, textvariable=self.var_log, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly")
        cb_log.pack(fill="x", pady=5)

    # --- TAB 2: INTERFACES ---
    def build_interfaces_tab(self):
        content = ttk.Frame(self.tab_interfaces, padding=15)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Detected Network Devices", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(content, text="Select the interfaces that belong to your VPN connection.", font=("Arial", 9), foreground="gray").pack(anchor="w", pady=(0, 10))

        self.scroll_container = ScrollableFrame(content)
        self.scroll_container.pack(fill="both", expand=True, pady=5)
        
        self.iface_list_area = self.scroll_container.scrollable_content
        
        self.refresh_interfaces()

        ttk.Button(content, text="Refresh Device List", command=self.refresh_interfaces).pack(pady=10)

    def refresh_interfaces(self):
        for widget in self.iface_list_area.winfo_children():
            widget.destroy()

        all_ifaces = self.checker.get_all_interfaces()
        saved_valid = self.cfg.get("valid_interfaces")
        
        first_run = len(saved_valid) == 0
        default_keywords = self.checker.default_keywords

        self.iface_vars = {} 

        # Sort interfaces by name
        all_ifaces.sort(key=lambda x: str(x['name']))

        # Styles
        bg_color = "#ffffff"
        style = ttk.Style()
        style.configure("White.TCheckbutton", background=bg_color)
        style.configure("White.TFrame", background=bg_color)
        style.configure("White.TLabel", background=bg_color)

        for iface in all_ifaces:
            name = iface['name'] # Display Name
            ip = iface['ip']
            
            is_checked = False
            if first_run:
                if any(k in name.lower() for k in default_keywords):
                    is_checked = True
            else:
                if name in saved_valid:
                    is_checked = True

            var = tk.BooleanVar(value=is_checked)
            self.iface_vars[name] = var
            
            row = ttk.Frame(self.iface_list_area, style="White.TFrame")
            row.pack(fill="x", pady=2, anchor="w")
            
            cb = ttk.Checkbutton(row, text=f"{name}", variable=var, style="White.TCheckbutton")
            cb.pack(side="left")
            
            info_text = f"({ip})"
            # If name looks like a GUID, maybe show it's unresolved
            if "{" in name and "}" in name:
                info_text += " [Unresolved ID]"
            
            lbl_ip = ttk.Label(row, text=info_text, foreground="gray", font=("Arial", 8), style="White.TLabel")
            lbl_ip.pack(side="left", padx=5)

        self.iface_list_area.update_idletasks()
        self.scroll_container.canvas.configure(scrollregion=self.scroll_container.canvas.bbox("all"))

    # --- TAB 3: ABOUT ---
    def build_about_tab(self):
        content = ttk.Frame(self.tab_about, padding=20)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="VPN Watchdog", font=("Segoe UI", 18, "bold")).pack(pady=(10, 5))
        
        # Display Version / Tag
        ttk.Label(content, text=f"Version: {version.BUILD_TAG}", foreground="gray").pack()
        ttk.Label(content, text=f"by {AUTHOR}", foreground="gray").pack(pady=(0, 20))

        # Links
        btn_repo = ttk.Button(content, text="GitHub Repository", command=lambda: webbrowser.open(GITHUB_URL))
        btn_repo.pack(fill="x", pady=5)
        
        btn_donate = ttk.Button(content, text="☕ Donate / Support", command=lambda: webbrowser.open(DONATE_URL))
        btn_donate.pack(fill="x", pady=5)

        # Build Details (Commit Hash & Date)
        details_text = (
            f"Build Date: {version.BUILD_DATE}\n"
            f"Commit: {version.COMMIT_HASH}\n"
            f"Python: {platform.python_version()} | OS: {platform.system()}"
        )
        ttk.Label(content, text=details_text, font=("Courier", 8), foreground="gray", justify="center").pack(side="bottom", pady=20)
    
    def on_close(self):
        # Just destroy the window, do NOT exit app
        self.root.destroy()

    # --- SAVE ---
    def save_and_close(self):
        if self.var_autostart.get():
            utils.enable_autostart()
        else:
            utils.disable_autostart()
        
        # Save Detection Mode
        display_val = self.var_mode.get() # e.g. "Auto (Recommended)"
        config_val = self.modes_rev.get(display_val, "auto")
        self.cfg.set("detection_mode", config_val)
        
        self.cfg.set("log_level", self.var_log.get())
        
        selected_interfaces = []
        for name, var in self.iface_vars.items():
            if var.get():
                selected_interfaces.append(name)
        
        self.cfg.set("valid_interfaces", selected_interfaces)
        
        logger.info(f"Settings saved. Mode: {config_val}, Valid interfaces: {selected_interfaces}")
        self.root.destroy()


class TrayApp:
    def __init__(self, app_logic, config_manager):
        self.logic = app_logic
        self.cfg = config_manager
        self.icon = TrayIcon("VPN Watchdog", self.create_image("gray"), "Initializing", menu=None)
        self.update_menu() 

    def create_image(self, color_name):
        width, height = 256, 256
        colors = { "green": (0, 255, 0, 255), "red": (255, 0, 0, 255), "yellow": (255, 255, 0, 255), "gray": (128, 128, 128, 255) }
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((32, 32, 224, 224), fill=colors.get(color_name, colors["gray"]))
        if color_name == "green": dc.rectangle((104, 104, 152, 152), fill="white")
        return image

    def update_menu(self):
        menu_items = [
            MenuItem(f'Status: {self.logic.status.upper()}', lambda i, it: None, enabled=False),
            Menu.SEPARATOR
        ]

        if self.logic.paused:
            menu_items.append(MenuItem('RESUME Protection', lambda i, it: self.logic.resume()))
        else:
            submenu = Menu(
                MenuItem('5 Minutes', lambda i, it: self.logic.pause(5)),
                MenuItem('10 Minutes', lambda i, it: self.logic.pause(10)),
                MenuItem('1 Hour', lambda i, it: self.logic.pause(60)),
                MenuItem('12 Hours', lambda i, it: self.logic.pause(720)),
            )
            menu_items.append(MenuItem('PAUSE Monitoring', submenu))

        menu_items.append(Menu.SEPARATOR)
        menu_items.append(MenuItem('Settings & Info', lambda i, it: self.logic.open_settings()))
        menu_items.append(MenuItem('Exit', lambda i, it: self.logic.stop()))
        
        self.icon.menu = Menu(*menu_items)

    def update_icon(self, status, pause_until=None):
        color = "gray"
        if status == "safe": color = "green"
        elif status == "unsafe": color = "red"
        elif status == "paused": color = "yellow"
        
        self.icon.icon = self.create_image(color)
        
        if status == "paused":
             rem = pause_until.strftime('%H:%M') if pause_until else "?"
             self.icon.title = f"Paused until {rem}"
        else:
             self.icon.title = f"VPN Watchdog: {status.upper()}"
        
        if status == "unsafe":
             self.icon.notify("VPN ALERT", "Secure connection lost!")
             
        self.update_menu()

    def run(self):
        self.icon.run()
    
    def stop(self):
        self.icon.stop()