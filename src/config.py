import json
import os
import logging

# Uses standard ~/.config location on Linux/Mac. 
# On Windows, this resolves to C:\Users\User\.config\vpn-watchdog, which works fine.
CONFIG_FILE = os.path.expanduser("~/.config/vpn-watchdog/config.json")

DEFAULT_CONFIG = {
    "log_level": "INFO",
    "valid_interfaces": [], # Stores interfaces checked by the user
    "check_interval": 5
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