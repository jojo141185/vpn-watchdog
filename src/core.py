import netifaces
import platform
import logging
import subprocess
import re


logger = logging.getLogger("VPNWatchdog")

class VPNChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.os_system = platform.system()
        # Default keywords for auto-detection suggestion
        self.default_keywords = ["nord", "tun", "tap", "wg", "ppp", "ipsec", "wireguard"]

    def _get_windows_guid_map(self):
        """
        Returns a dict mapping Windows Interface GUIDs to Friendly Names.
        Example: {'{8A...}': 'NordLynx', ...}
        """
        guid_map = {}
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-NetAdapter | Select-Object Name, InterfaceGuid"]
            # CREATE_NO_WINDOW prevents popup on Windows
            creation_flags = 0x08000000 if platform.system() == "Windows" else 0
            
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
            
            for line in result.stdout.splitlines():
                # Line format: "Name       InterfaceGuid"
                # We need to parse robustly.
                line = line.strip()
                if not line or "InterfaceGuid" in line or "----" in line:
                    continue
                
                # Split by regex to handle spaces in names
                # Assuming GUID is the last element and looks like {XXX...}
                match = re.search(r'^(.*)\s+(\{[a-fA-F0-9-]+\})$', line)
                if match:
                    name = match.group(1).strip()
                    guid = match.group(2).strip()
                    guid_map[guid] = name
        except Exception as e:
            logger.error(f"Error mapping Windows GUIDs: {e}")
        return guid_map

    def get_all_interfaces(self):
        """
        Returns a list of dicts: [{'name': 'eth0', 'ip': '192.168.1.5'}, ...]
        Used to populate the GUI list.
        """
        interfaces = []
        
        # Pre-fetch Windows Names if needed
        win_map = self._get_windows_guid_map() if self.os_system == "Windows" else {}

        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                # Get IPv4 address if available
                ip = "No IP"
                if netifaces.AF_INET in addrs:
                    ip = addrs[netifaces.AF_INET][0]['addr']
                
                # Determine Display Name
                display_name = iface
                if self.os_system == "Windows":
                    # netifaces returns GUID on Windows. Try to map it to friendly name.
                    if iface in win_map:
                        display_name = win_map[iface]
                
                interfaces.append({
                    "name": display_name,
                    "ip": ip,
                    "id": iface # internal ID (GUID on win, Name on lin/mac)
                })
        except Exception as e:
            logger.error(f"Error listing interfaces: {e}")
        return interfaces

    def get_active_route_interface_name(self):
        """
        Determines the name of the interface routing traffic to 1.1.1.1.
        Returns the Friendly Name (Windows) or Interface Name (Linux/Mac).
        """
        target_ip = "1.1.1.1"

        try:
            # --- LINUX ---
            if self.os_system == "Linux":
                res = subprocess.run(["ip", "route", "get", target_ip], capture_output=True, text=True)
                output = res.stdout.strip()
                # Find "dev <name>"
                match = re.search(r'dev\s+(\S+)', output)
                if match:
                    return match.group(1)

            # --- MACOS ---
            elif self.os_system == "Darwin":
                res = subprocess.run(["route", "get", target_ip], capture_output=True, text=True)
                output = res.stdout
                match = re.search(r'interface:\s+(\S+)', output)
                if match:
                    return match.group(1)

            # --- WINDOWS ---
            elif self.os_system == "Windows":
                # PowerShell: Find-NetRoute
                ps_cmd = f"Find-NetRoute -RemoteIP \"{target_ip}\" | Select-Object -ExpandProperty InterfaceAlias"
                creation_flags = 0x08000000
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                                     capture_output=True, text=True, creationflags=creation_flags)
                return res.stdout.strip()

        except Exception as e:
            logger.error(f"Routing check failed ({self.os_system}): {e}")
        
        return None

    def is_secure(self):
        # 1. Load config
        allowed_interfaces = self.cfg.get("valid_interfaces")
        
        if not allowed_interfaces:
            logger.debug("No allowed interfaces configured -> UNSAFE")
            return False

        # 2. Get active routing interface
        active_iface = self.get_active_route_interface_name()
        
        if not active_iface:
            logger.warning("Could not determine active routing interface.")
            return False

        logger.debug(f"Active Interface: '{active_iface}' | Allowed: {allowed_interfaces}")

        # 3. Compare (Case Insensitive)
        # Note: 'allowed_interfaces' stores Display Names (e.g., "NordLynx")
        active_lower = active_iface.lower()
        for allowed in allowed_interfaces:
            if allowed.lower() == active_lower:
                return True
        
        return False