import tkinter as tk
from tkinter import ttk, font
import webbrowser
import logging
import platform
import queue
import socket
import threading
import os
from collections import deque
from PIL import Image, ImageDraw, ImageFont
from pystray import Icon as TrayIcon, Menu, MenuItem
import utils
from core import VPNChecker 
import version 
import providers

# Safe Import for ImageTk
try:
    from PIL import ImageTk
    HAS_IMAGETK = True
except ImportError:
    HAS_IMAGETK = False

logger = logging.getLogger("VPNWatchdog")

GITHUB_URL = "https://github.com/jojo141185/vpn-watchdog"
DONATE_URL = "https://github.com/sponsors/jojo141185" 
AUTHOR = "jojo141185"

# --- HELPER: ICON GENERATOR (Fallback) ---
def generate_icon_image(color_name="gray", country_code=None, size=64):
    """Generates a PIL Image for Tray and Window Icons (Fallback)."""
    width, height = size, size
    colors = { 
        "green": (0, 255, 0, 255), 
        "red": (255, 0, 0, 255), 
        "yellow": (255, 255, 0, 255), 
        "gray": (128, 128, 128, 255) 
    }
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    padding = size // 16
    fill = colors.get(color_name, colors["gray"])
    dc.ellipse((padding, padding, width-padding, height-padding), fill=fill)
    
    if color_name == "green": 
        s = size // 3
        dc.rectangle((s, s, size-s, size-s), fill="white")

    if country_code and country_code != "??":
        try: 
            font_size = int(size * 0.4)
            fnt = ImageFont.truetype("arial.ttf", font_size)
        except IOError: 
            fnt = ImageFont.load_default()
        text = country_code.upper()[:2]
        try:
            bbox = dc.textbbox((0,0), text, font=fnt)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (width - w) / 2
            y = (height - h) / 2
            dc.text((x+1, y+1), text, fill="black", font=fnt)
            dc.text((x, y), text, fill="white", font=fnt)
        except AttributeError: 
            dc.text((size//4, size//4), text, fill="white")
            
    return image

# --- HELPER: SET WINDOW ICON (Static) ---
def set_window_icon(root):
    """Tries to load 'icon.png' for the window titlebar."""
    if not HAS_IMAGETK: return None
    
    # Paths to search for icon.png
    candidates = [
        os.path.join(os.path.dirname(__file__), 'icon.png'), # Same dir as script
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icon.png'), # Root dir
        'icon.png' # CWD
    ]
    
    found_path = None
    for p in candidates:
        if os.path.exists(p):
            found_path = p
            break
    
    try:
        if found_path:
            img = Image.open(found_path)
            photo = ImageTk.PhotoImage(img, master=root)
            root.iconphoto(False, photo)
            return photo # Keep ref
        else:
            # Fallback to generated gray circle
            gen = generate_icon_image("gray", size=32)
            photo = ImageTk.PhotoImage(gen, master=root)
            root.iconphoto(False, photo)
            return photo
    except Exception as e:
        logger.warning(f"Could not load window icon: {e}")
        return None

# --- LOGGING HANDLER ---
class ListLogHandler(logging.Handler):
    def __init__(self, buffer, callback=None):
        super().__init__()
        self.buffer = buffer # deque object
        self.callback = callback

    def emit(self, record):
        log_entry = {
            "time": self.format(record),
            "level": record.levelname,
            "raw": record.message
        }
        self.buffer.append(log_entry)
        if self.callback:
            self.callback()

# --- COMPONENT: SCROLLABLE FRAME ---
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, background="#ffffff", 
                                highlightthickness=1, highlightbackground="#a0a0a0")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_content = tk.Frame(self.canvas, background="#ffffff")
        self.scrollable_content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel) 
        self.canvas.bind_all("<Button-4>", self._on_linux_scroll_up)   
        self.canvas.bind_all("<Button-5>", self._on_linux_scroll_down) 

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    def _on_linux_scroll_up(self, event):
        self.canvas.yview_scroll(-1, "units")
    def _on_linux_scroll_down(self, event):
        self.canvas.yview_scroll(1, "units")

# --- STATUS DASHBOARD ---
class StatusWindow:
    def __init__(self, checker, log_buffer, on_close_callback=None):
        self.checker = checker
        self.log_buffer = log_buffer
        self.on_close_callback = on_close_callback
        self.is_running = True # Flag to stop update loop
        
        self.root = tk.Tk()
        self.root.title("VPN Watchdog - Status Dashboard")
        w, h = 800, 600
        ws, hs = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{int((ws-w)/2)}+{int((hs-h)/2)}")
        
        # Set Static Icon
        self._icon_ref = set_window_icon(self.root)
        
        style = ttk.Style()
        style.theme_use('clam')
        
        # Tabs
        tabs = ttk.Notebook(self.root)
        self.tab_overview = ttk.Frame(tabs)
        self.tab_logs = ttk.Frame(tabs)
        tabs.add(self.tab_overview, text="Status Overview")
        tabs.add(self.tab_logs, text="Live Logs")
        tabs.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.build_overview()
        self.build_logs()
        
        # Start Update Loop
        self.update_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def build_overview(self):
        pad = 10
        self.frm_global = ttk.LabelFrame(self.tab_overview, text=" Global Protection ", padding=pad)
        self.frm_global.pack(fill="x", padx=pad, pady=pad)
        self.lbl_global = ttk.Label(self.frm_global, text="UNKNOWN", font=("Segoe UI", 16, "bold"))
        self.lbl_global.pack(anchor="center")

        container = ttk.Frame(self.tab_overview)
        container.pack(fill="both", expand=True, padx=pad)
        
        self.card_route = self.create_status_card(container, "Routing Interface")
        self.card_route["frame"].pack(side="left", fill="both", expand=True, padx=5)
        
        self.card_conn = self.create_status_card(container, "Public IP & Geo")
        self.card_conn["frame"].pack(side="left", fill="both", expand=True, padx=5)
        
        self.card_dns = self.create_status_card(container, "DNS Leaks")
        self.card_dns["frame"].pack(side="left", fill="both", expand=True, padx=5)

    def create_status_card(self, parent, title):
        frm = ttk.LabelFrame(parent, text=f" {title} ", padding=10)
        
        head = ttk.Frame(frm)
        head.pack(fill="x", pady=(0, 10))
        lbl_icon = ttk.Label(head, text="⚪", font=("Segoe UI", 24))
        lbl_icon.pack(side="left", padx=(0, 10))
        lbl_status = ttk.Label(head, text="Disabled", font=("Segoe UI", 12, "bold"))
        lbl_status.pack(side="left", anchor="center")
        
        details_frame = ttk.Frame(frm)
        details_frame.pack(fill="both", expand=True)
        details_frame.columnconfigure(1, weight=1)
        
        return {
            "frame": frm, "icon": lbl_icon, "status": lbl_status, 
            "details_frame": details_frame, "rows": []
        }

    def set_card_details(self, card, data_dict):
        for w in card["details_frame"].winfo_children():
            w.destroy()
        if not data_dict: return

        row_idx = 0
        for key, val in data_dict.items():
            ttk.Label(card["details_frame"], text=f"{key}:", font=("Arial", 9, "bold"), foreground="#555").grid(row=row_idx, column=0, sticky="nw", pady=2)
            ttk.Label(card["details_frame"], text=str(val), font=("Arial", 9), wraplength=130).grid(row=row_idx, column=1, sticky="nw", padx=5, pady=2)
            row_idx += 1

    def build_logs(self):
        frm_filter = ttk.Frame(self.tab_logs)
        frm_filter.pack(fill="x", padx=5, pady=5)
        ttk.Label(frm_filter, text="Min Level:").pack(side="left")
        self.var_filter = tk.StringVar(value="INFO")
        cb_filter = ttk.Combobox(frm_filter, textvariable=self.var_filter, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly", width=10)
        cb_filter.pack(side="left", padx=5)
        cb_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_logs())
        ttk.Button(frm_filter, text="Refresh", command=self.refresh_logs).pack(side="right")

        self.txt_log = tk.Text(self.tab_logs, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)
        scr = ttk.Scrollbar(self.txt_log, command=self.txt_log.yview)
        self.txt_log['yscrollcommand'] = scr.set
        scr.pack(side="right", fill="y")
        self.refresh_logs()

    def refresh_logs(self):
        if not self.is_running: return # Safety check
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
        min_lvl = levels.get(self.var_filter.get(), 20)
        logs = list(self.log_buffer)
        
        for entry in logs:
            lvl_val = levels.get(entry["level"], 20)
            if lvl_val >= min_lvl:
                line = f"[{entry['level']}] {entry['time']} - {entry['raw']}\n"
                self.txt_log.insert("end", line)
        
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def notify_new_log(self):
        if self.is_running:
            self.root.after_idle(self.refresh_logs)

    def update_ui(self):
        if not self.is_running: return # Stop loop if closed

        # 2. Update Data
        data = self.checker.get_dashboard_data()
        
        # Global
        g_secure = data["secure"]
        self.lbl_global.configure(text="SECURE" if g_secure else "VULNERABLE", foreground="green" if g_secure else "red")
        
        def update_vis(card, info):
            if not info["enabled"]:
                card["icon"].configure(text="⚪", foreground="gray")
                card["status"].configure(text="Disabled", foreground="gray")
                self.set_card_details(card, None)
            elif info["secure"]:
                card["icon"].configure(text="🟢", foreground="green")
                card["status"].configure(text="Secure", foreground="green")
            else:
                card["icon"].configure(text="🔴", foreground="red")
                card["status"].configure(text="UNSAFE", foreground="red")
        
        # Routing
        r = data["routing"]
        update_vis(self.card_route, r)
        if r["enabled"]:
            self.set_card_details(self.card_route, {"Details": r["details"]})
        
        # Public
        p = data["public"]
        update_vis(self.card_conn, p)
        if p["enabled"]:
            pd = p["data"]
            details = {
                "IP": pd.get("ipv4", "N/A"),
                "Country": pd.get("country", "??"),
                "ISP": pd.get("isp", "N/A")
            }
            if pd.get("error"): details["Error"] = pd.get("error")
            self.set_card_details(self.card_conn, details)

        # DNS
        d = data["dns"]
        update_vis(self.card_dns, d)
        if d["enabled"]:
            dd = d["data"]
            count = dd.get("count", 0)
            details = {"Servers Found": count}
            if count > 0 and dd.get("servers"):
                first = dd.get("servers")[0]
                details["DNS IP"] = first.get("ip")
                details["DNS ASN"] = first.get("asn")
            if dd.get("error"): details["Error"] = dd.get("error")
            self.set_card_details(self.card_dns, details)

        self.root.after(2000, self.update_ui) 

    def on_close(self):
        self.is_running = False
        self.root.destroy()
        if self.on_close_callback:
            self.on_close_callback()

# --- SETTINGS DIALOG ---
class SettingsDialog:
    def __init__(self, config_manager, on_close_callback=None):
        self.cfg = config_manager
        self.checker = VPNChecker(self.cfg) 
        self.on_close_callback = on_close_callback
        
        self.root = tk.Tk()
        self.root.title("VPN Watchdog Settings")
        
        # Shared Variables
        self.var_home_isp = tk.StringVar(value=self.cfg.get("home_isp"))
        self.var_dyndns = tk.StringVar(value=self.cfg.get("home_dyndns"))
        
        # Set Static Icon
        self._icon_ref = set_window_icon(self.root)

        w, h = 600, 800 
        ws, hs = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{int((ws-w)/2)}+{int((hs-h)/2)}")
        style = ttk.Style()
        style.theme_use('clam')

        tab_control = ttk.Notebook(self.root)
        self.tab_general = ttk.Frame(tab_control)
        self.tab_routing = ttk.Frame(tab_control)
        self.tab_public = ttk.Frame(tab_control)
        self.tab_dns = ttk.Frame(tab_control)
        self.tab_about = ttk.Frame(tab_control)
        
        tab_control.add(self.tab_general, text='General')
        tab_control.add(self.tab_routing, text='Routing')
        tab_control.add(self.tab_public, text='Connectivity')
        tab_control.add(self.tab_dns, text='DNS Leak')
        tab_control.add(self.tab_about, text='About')
        
        tab_control.pack(expand=1, fill="both", padx=10, pady=10)

        self.build_general_tab()
        self.build_routing_tab()
        self.build_public_tab()
        self.build_dns_tab()
        self.build_about_tab()

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_frame, text="Save & Close", command=self.save_and_close).pack(side="right")

        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    # (Same build methods as before, just ensuring icon_ref is kept)
    def build_general_tab(self):
        content = ttk.Frame(self.tab_general, padding=15)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="System Configuration", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        grp_sys = ttk.LabelFrame(content, text=" Startup ", padding=15)
        grp_sys.pack(fill="x", pady=5)
        self.var_autostart = tk.BooleanVar(value=utils.is_autostart_enabled())
        ttk.Checkbutton(grp_sys, text="Start automatically with System", variable=self.var_autostart).pack(anchor="w")
        grp_log = ttk.LabelFrame(content, text=" Debugging ", padding=15)
        grp_log.pack(fill="x", pady=10)
        ttk.Label(grp_log, text="Log Level:").pack(anchor="w")
        self.var_log = tk.StringVar(value=self.cfg.get("log_level"))
        cb_log = ttk.Combobox(grp_log, textvariable=self.var_log, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly")
        cb_log.pack(fill="x", pady=5)

    def build_routing_tab(self):
        content = ttk.Frame(self.tab_routing, padding=15)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Local Interface Monitoring", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.var_route_enable = tk.BooleanVar(value=self.cfg.get("routing_check_enabled"))
        ttk.Checkbutton(content, text="Enable Interface Check", variable=self.var_route_enable).pack(anchor="w", pady=5)
        grp_set = ttk.LabelFrame(content, text=" Configuration ", padding=15)
        grp_set.pack(fill="x", pady=5)
        ttk.Label(grp_set, text="Interval (sec):").pack(side="left")
        self.var_interval = tk.StringVar(value=str(self.cfg.get("check_interval")))
        ttk.Entry(grp_set, textvariable=self.var_interval, width=5).pack(side="left", padx=10)
        ttk.Label(grp_set, text="Method:").pack(side="left", padx=(10, 5))
        self.var_detect_mode = tk.StringVar(value=self.cfg.get("detection_mode"))
        modes = {"Auto": "auto", "Performance": "performance", "Precision": "precision"}
        self.modes_map = {v: k for k, v in modes.items()}
        self.modes_rev = modes
        cb_det = ttk.Combobox(grp_set, textvariable=self.var_detect_mode, values=list(modes.keys()), state="readonly")
        cb_det.set(self.modes_map.get(self.cfg.get("detection_mode"), "Auto"))
        cb_det.pack(side="left")
        ttk.Label(content, text="Valid VPN Interfaces:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(15, 5))
        self.scroll_container = ScrollableFrame(content)
        self.scroll_container.pack(fill="both", expand=True, pady=5)
        self.iface_list_area = self.scroll_container.scrollable_content
        self.refresh_interfaces()
        ttk.Button(content, text="Refresh Device List", command=self.refresh_interfaces).pack(pady=10)

    def refresh_interfaces(self):
        for widget in self.iface_list_area.winfo_children(): widget.destroy()
        all_ifaces = self.checker.get_all_interfaces()
        saved_valid = self.cfg.get("valid_interfaces")
        first_run = len(saved_valid) == 0
        default_keywords = self.checker.default_keywords
        self.iface_vars = {} 
        all_ifaces.sort(key=lambda x: str(x['name']))
        style = ttk.Style()
        style.configure("White.TCheckbutton", background="#ffffff")
        style.configure("White.TFrame", background="#ffffff")
        style.configure("White.TLabel", background="#ffffff")
        for iface in all_ifaces:
            name = iface['name']
            ip = iface['ip']
            is_checked = any(k in name.lower() for k in default_keywords) if first_run else (name in saved_valid)
            var = tk.BooleanVar(value=is_checked)
            self.iface_vars[name] = var
            row = ttk.Frame(self.iface_list_area, style="White.TFrame")
            row.pack(fill="x", pady=2, anchor="w")
            ttk.Checkbutton(row, text=f"{name}", variable=var, style="White.TCheckbutton").pack(side="left")
            info_text = f"({ip})" + (" [Unresolved ID]" if "{" in name else "")
            ttk.Label(row, text=info_text, foreground="gray", font=("Arial", 8), style="White.TLabel").pack(side="left", padx=5)
        self.iface_list_area.update_idletasks()
        self.scroll_container.canvas.configure(scrollregion=self.scroll_container.canvas.bbox("all"))

    def build_public_tab(self):
        content = ttk.Frame(self.tab_public, padding=15)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Public Connectivity Check", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.var_pub_enable = tk.BooleanVar(value=self.cfg.get("public_check_enabled"))
        ttk.Checkbutton(content, text="Enable Connectivity Check", variable=self.var_pub_enable, command=self.toggle_public_options).pack(anchor="w", pady=5)
        grp_gen = ttk.LabelFrame(content, text=" Configuration ", padding=15)
        grp_gen.pack(fill="x", pady=5)
        ttk.Label(grp_gen, text="Interval (sec):").pack(side="left")
        self.var_pub_interval = tk.StringVar(value=str(self.cfg.get("public_check_interval")))
        self.ent_pub_int = ttk.Entry(grp_gen, textvariable=self.var_pub_interval, width=5)
        self.ent_pub_int.pack(side="left", padx=10)
        ttk.Label(grp_gen, text="Provider:").pack(side="left", padx=(10, 5))
        self.var_pub_prov = tk.StringVar(value=self.cfg.get("public_check_provider"))
        prov_map = providers.get_provider_display_names()
        self.prov_rev = {v: k for k, v in prov_map.items()}
        self.cb_prov = ttk.Combobox(grp_gen, textvariable=self.var_pub_prov, values=list(prov_map.values()), state="readonly")
        self.cb_prov.set(prov_map.get(self.cfg.get("public_check_provider"), "ipwho.is"))
        self.cb_prov.pack(side="left", fill="x", expand=True)
        self.cb_prov.bind("<<ComboboxSelected>>", self.update_provider_fields)
        
        self.frm_custom = ttk.Frame(content)
        self.frm_custom.pack(fill="x", pady=5)
        ttk.Label(self.frm_custom, text="Custom API URL:").pack(anchor="w")
        self.var_cust_url = tk.StringVar(value=self.cfg.get("public_custom_url"))
        ttk.Entry(self.frm_custom, textvariable=self.var_cust_url).pack(fill="x", pady=2)
        frm_keys = ttk.Frame(self.frm_custom)
        frm_keys.pack(fill="x", pady=2)
        ttk.Label(frm_keys, text="JSON Keys -> IP:").pack(side="left")
        self.var_key_ip = tk.StringVar(value=self.cfg.get("public_custom_key_ip"))
        ttk.Entry(frm_keys, textvariable=self.var_key_ip, width=8).pack(side="left", padx=5)
        ttk.Label(frm_keys, text="Country:").pack(side="left")
        self.var_key_country = tk.StringVar(value=self.cfg.get("public_custom_key_country"))
        ttk.Entry(frm_keys, textvariable=self.var_key_country, width=8).pack(side="left", padx=5)
        ttk.Label(frm_keys, text="ISP:").pack(side="left")
        self.var_key_isp = tk.StringVar(value=self.cfg.get("public_custom_key_isp"))
        ttk.Entry(frm_keys, textvariable=self.var_key_isp, width=8).pack(side="left", padx=5)

        grp_strat = ttk.LabelFrame(content, text=" Detection Logic ", padding=15)
        grp_strat.pack(fill="x", pady=10)
        ttk.Label(grp_strat, text="Alert Strategy:").pack(anchor="w")
        self.var_pub_strat = tk.StringVar(value=self.cfg.get("public_check_strategy"))
        strats = { "My Local Country (Geo-Fence)": "country", "My Local ISP-Name": "isp", "ISP + Country (Combined)": "combined", "DynDNS / IP Match": "ip_match" }
        self.strats_rev = strats
        self.strats_map = {v: k for k, v in strats.items()}
        self.cb_strat = ttk.Combobox(grp_strat, textvariable=self.var_pub_strat, values=list(strats.keys()), state="readonly")
        self.cb_strat.set(self.strats_map.get(self.cfg.get("public_check_strategy"), "ISP + Country (Combined)"))
        self.cb_strat.pack(fill="x", pady=5)
        self.cb_strat.bind("<<ComboboxSelected>>", self.update_public_inputs)

        self.frm_params = ttk.LabelFrame(content, text=" Required Inputs ", padding=15)
        self.frm_params.pack(fill="x", pady=5)
        self.row_country = ttk.Frame(self.frm_params)
        ttk.Label(self.row_country, text="My Local Country Code (e.g. DE):").pack(anchor="w")
        self.var_target_country = tk.StringVar(value=self.cfg.get("target_country"))
        ttk.Entry(self.row_country, textvariable=self.var_target_country).pack(fill="x")
        
        # ISP Row
        self.row_isp = ttk.Frame(self.frm_params)
        ttk.Label(self.row_isp, text="My Local ISP Name (e.g. Telekom):").pack(anchor="w")
        ttk.Entry(self.row_isp, textvariable=self.var_home_isp).pack(fill="x") # Shared Variable

        # DNS/IP Row with Auto Detect
        self.row_dns = ttk.Frame(self.frm_params)
        ttk.Label(self.row_dns, text="Home DynDNS or IP (e.g. home.ddns.net):").pack(anchor="w")
        frm_dns_inner = ttk.Frame(self.row_dns)
        frm_dns_inner.pack(fill="x")
        ttk.Entry(frm_dns_inner, textvariable=self.var_dyndns).pack(side="left", fill="x", expand=True)
        ttk.Button(frm_dns_inner, text="Detect ISP", command=self.auto_detect_isp).pack(side="left", padx=5)

        self.toggle_public_options()
        self.update_public_inputs()
        self.update_provider_fields()

    def auto_detect_isp(self):
        host = self.var_dyndns.get().strip()
        if not host: return
        def run_detect():
            try:
                target_ip = socket.gethostbyname(host)
                provider = providers.get_provider("ipwhois")
                data = provider.fetch_details(target_ip=target_ip)
                if data["success"] and data.get("isp"):
                    self.var_home_isp.set(data.get("isp"))
            except Exception: pass
        threading.Thread(target=run_detect, daemon=True).start()

    def update_provider_fields(self, event=None):
        key = self.prov_rev.get(self.cb_prov.get(), "ipwhois")
        if key == "custom": self.frm_custom.pack(fill="x", pady=5, after=self.cb_prov.master)
        else: self.frm_custom.pack_forget()

    def update_public_inputs(self, event=None):
        self.row_country.pack_forget(); self.row_isp.pack_forget(); self.row_dns.pack_forget()
        strat = self.strats_rev.get(self.cb_strat.get(), "combined")
        if strat == "country": self.row_country.pack(fill="x", pady=2)
        elif strat == "isp": self.row_isp.pack(fill="x", pady=2)
        elif strat == "combined": self.row_country.pack(fill="x", pady=2); self.row_isp.pack(fill="x", pady=2)
        elif strat == "ip_match": self.row_dns.pack(fill="x", pady=2)

    def toggle_public_options(self):
        state = "normal" if self.var_pub_enable.get() else "disabled"
        self.ent_pub_int.configure(state=state)
        self.cb_prov.configure(state="readonly" if state=="normal" else "disabled")
        self.cb_strat.configure(state="readonly" if state=="normal" else "disabled")

    def build_dns_tab(self):
        content = ttk.Frame(self.tab_dns, padding=15)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="DNS Leak Protection", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.var_dns_enable = tk.BooleanVar(value=self.cfg.get("dns_check_enabled"))
        ttk.Checkbutton(content, text="Enable DNS Leak Check", variable=self.var_dns_enable, command=self.toggle_dns_options).pack(anchor="w", pady=5)
        grp_conf = ttk.LabelFrame(content, text=" Configuration ", padding=15)
        grp_conf.pack(fill="x", pady=5)
        ttk.Label(grp_conf, text="Interval (sec):").pack(side="left")
        self.var_dns_int = tk.StringVar(value=str(self.cfg.get("dns_check_interval")))
        self.ent_dns_int = ttk.Entry(grp_conf, textvariable=self.var_dns_int, width=5)
        self.ent_dns_int.pack(side="left", padx=10)
        self.var_dns_alert = tk.BooleanVar(value=self.cfg.get("dns_alert_on_home_isp"))
        self.chk_dns_alert = ttk.Checkbutton(content, text="Alert if DNS Server belongs to Home ISP", variable=self.var_dns_alert)
        self.chk_dns_alert.pack(anchor="w", pady=10)
        ttk.Label(content, text="My Local ISP Name (Shared with Connectivity):").pack(anchor="w")
        self.ent_dns_isp = ttk.Entry(content, textvariable=self.var_home_isp) # Shared Variable
        self.ent_dns_isp.pack(fill="x", pady=5)
        self.toggle_dns_options()

    def toggle_dns_options(self):
        state = "normal" if self.var_dns_enable.get() else "disabled"
        self.ent_dns_int.configure(state=state)
        self.chk_dns_alert.configure(state=state)
        self.ent_dns_isp.configure(state=state)

    def build_about_tab(self):
        content = ttk.Frame(self.tab_about, padding=20)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="VPN Watchdog", font=("Segoe UI", 18, "bold")).pack(pady=(10, 5))
        ttk.Label(content, text=f"Version: {version.BUILD_TAG}", foreground="gray").pack()
        ttk.Label(content, text=f"by {AUTHOR}", foreground="gray").pack(pady=(0, 20))
        ttk.Button(content, text="GitHub Repository", command=lambda: webbrowser.open(GITHUB_URL)).pack(fill="x", pady=5)
        ttk.Button(content, text="☕ Donate / Support", command=lambda: webbrowser.open(DONATE_URL)).pack(fill="x", pady=5)
        details = f"Build Date: {version.BUILD_DATE}\nCommit: {version.COMMIT_HASH}\nPython: {platform.python_version()} | OS: {platform.system()}"
        ttk.Label(content, text=details, font=("Courier", 8), foreground="gray", justify="center").pack(side="bottom", pady=20)
    
    def on_close(self):
        self.root.destroy()
        if self.on_close_callback:
            self.on_close_callback()

    def save_and_close(self):
        if self.var_autostart.get(): utils.enable_autostart()
        else: utils.disable_autostart()
        self.cfg.set("log_level", self.var_log.get())
        self.cfg.set("routing_check_enabled", self.var_route_enable.get())
        self.cfg.set("check_interval", int(self.var_interval.get()))
        self.cfg.set("detection_mode", self.modes_rev.get(self.var_detect_mode.get(), "auto"))
        selected = [name for name, var in self.iface_vars.items() if var.get()]
        self.cfg.set("valid_interfaces", selected)
        self.cfg.set("public_check_enabled", self.var_pub_enable.get())
        self.cfg.set("public_check_interval", int(self.var_pub_interval.get()))
        self.cfg.set("public_check_provider", self.prov_rev.get(self.cb_prov.get(), "ipwhois"))
        self.cfg.set("public_check_strategy", self.strats_rev.get(self.cb_strat.get(), "combined"))
        self.cfg.set("public_custom_url", self.var_cust_url.get())
        self.cfg.set("public_custom_key_ip", self.var_key_ip.get())
        self.cfg.set("public_custom_key_country", self.var_key_country.get())
        self.cfg.set("public_custom_key_isp", self.var_key_isp.get())
        self.cfg.set("target_country", self.var_target_country.get())
        self.cfg.set("home_isp", self.var_home_isp.get())
        self.cfg.set("home_dyndns", self.var_dyndns.get())
        self.cfg.set("dns_check_enabled", self.var_dns_enable.get())
        self.cfg.set("dns_check_interval", int(self.var_dns_int.get()))
        self.cfg.set("dns_alert_on_home_isp", self.var_dns_alert.get())
        logger.info("Settings saved.")
        self.root.destroy()
        if self.on_close_callback:
            self.on_close_callback()


class TrayApp:
    def __init__(self, app_logic, config_manager):
        self.logic = app_logic
        self.cfg = config_manager
        self.icon = TrayIcon("VPN Watchdog", generate_icon_image("gray"), "Initializing", menu=None)
        
        self.log_buffer = deque(maxlen=500)
        self.status_window = None
        
        handler = ListLogHandler(self.log_buffer, callback=self.on_new_log)
        formatter = logging.Formatter('%(asctime)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        self.update_menu() 

    def on_new_log(self):
        if self.status_window:
            try:
                self.status_window.notify_new_log()
            except Exception:
                pass

    def on_window_closed(self):
        # Callback when Settings/Dashboard closes to allow reopening
        self.logic.settings_open = False # Only for SettingsDialog actually
        # For StatusWindow:
        self.status_window = None

    def open_dashboard(self):
        if self.status_window:
            try: self.status_window.root.lift()
            except tk.TclError: self.status_window = StatusWindow(self.logic.checker, self.log_buffer, on_close_callback=self.on_window_closed)
        else:
            self.status_window = StatusWindow(self.logic.checker, self.log_buffer, on_close_callback=self.on_window_closed)

    def update_menu(self):
        menu_items = [
            MenuItem(f'Status: {self.logic.status.upper()}', lambda i, it: None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Status Dashboard', lambda i, it: self.open_dashboard()),
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
        menu_items.append(MenuItem('Settings', lambda i, it: self.logic.open_settings()))
        menu_items.append(MenuItem('Exit', lambda i, it: self.logic.stop()))
        self.icon.menu = Menu(*menu_items)

    def update_icon(self, status, pause_until=None, country="??"):
        color = "gray"
        if status == "safe": color = "green"
        elif status == "unsafe": color = "red"
        elif status == "paused": color = "yellow"
        self.icon.icon = generate_icon_image(color, country)
        title = f"VPN Watchdog: {status.upper()}"
        state = self.logic.checker.current_state 
        details = []
        if status == "paused":
             rem = pause_until.strftime('%H:%M') if pause_until else "?"
             details.append(f"Paused until {rem}")
        else:
             if state["routing"]["enabled"]:
                 details.append(f"Local: {'OK' if state['routing']['secure'] else 'LEAK'}")
             if state["public"]["enabled"]:
                 d = state["public"]["data"]
                 details.append(f"Pub: {d.get('ipv4')} ({d.get('country')})")
             if state["dns"]["enabled"]:
                 details.append(f"DNS: {'OK' if state['dns']['secure'] else 'LEAK'}")
        if details: title += "\n" + "\n".join(details)
        if len(title) > 120: title = title[:117] + "..."
        self.icon.title = title
        if status == "unsafe": self.icon.notify("VPN ALERT", "Secure connection lost!")
        self.update_menu()

    def run(self):
        self.icon.run()
    def stop(self):
        self.icon.stop()