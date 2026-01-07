import json
import os
import logging

# Uses standard ~/.config location on Linux/Mac. 
# On Windows, this resolves to C:\Users\User\.config\vpn-watchdog, which works fine.
CONFIG_FILE = os.path.expanduser("~/.config/vpn-watchdog/config.json")

DEFAULT_CONFIG = {
    "log_level": "INFO",
    "check_interval": 5,           # Global Loop Interval (Seconds)
    
    # --- Module 1: Routing Guard (Interfaces) ---
    "routing_check_enabled": True,
    "valid_interfaces": [], 
    "detection_mode": "auto",      # auto, performance, precision
    
    # --- Module 2: Connectivity Guard (Public IP) ---
    "public_check_enabled": False,
    "public_check_interval": 60,   
    "public_check_provider": "smart", # smart (Recommended), ipwhois, ipapi, custom
    
    # Custom Provider Settings
    "public_custom_url": "",       # Primary / IPv4
    "public_custom_url_v6": "",    # IPv6 Specific
    "public_custom_key_ip": "ip",           
    "public_custom_key_country": "country", 
    "public_custom_key_isp": "isp",         
    
    "public_check_strategy": "combined", # country, isp, combined, ip_match
    
    # Strategy Parameters
    "target_country": "",          # e.g. "DE" (Home Country)
    "home_isp": "",                # e.g. "Telekom" (Home ISP)
    "home_dyndns": "",             # e.g. "myhome.dyndns.org" or static IP

    # --- Module 3: DNS Leak Guard ---
    "dns_check_enabled": False,
    "dns_check_interval": 120,     # Default 2 mins (API intensive)
    "dns_alert_on_home_isp": True  # Alert if DNS server belongs to Home ISP
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()
        self.apply_logging()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception as e:
                print(f"Error loading config: {e}")

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)
        self.apply_logging()

    def get(self, key):
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def apply_logging(self):
        level_str = self.config.get("log_level", "INFO")
        level = getattr(logging, level_str.upper(), logging.INFO)
        
        # Configure logging (force=True reconfigures if already set)
        logging.basicConfig(
            level=level,
            format='[%(levelname)s] %(asctime)s - %(message)s',
            datefmt='%H:%M:%S',
            force=True 
        )