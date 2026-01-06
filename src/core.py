import netifaces
import platform
import logging
import subprocess
import json
import re

logger = logging.getLogger("VPNWatchdog")

class VPNChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.os_system = platform.system()
        # Default keywords for auto-detection suggestion
        self.default_keywords = ["nord", "tun", "tap", "wg", "ppp", "ipsec", "wireguard"]
        
        # CACHE: Store Windows Friendly Names to avoid running PowerShell constantly
        self._guid_name_cache = {}
        self._cache_populated = False

    def _run_command(self, cmd_list, use_shell=False):
        """
        Helper to run subprocesses with a safety timeout to prevent hanging
        after system standby or network changes.
        """
        try:
            # Prevent console window flashing on Windows
            creation_flags = 0x08000000 if self.os_system == "Windows" else 0
            
            # Timeout is CRITICAL. Without it, 'ip route' or 'powershell' can hang indefinitely
            # if the network stack is unstable (e.g. after sleep), freezing the whole app.
            res = subprocess.run(
                cmd_list, 
                capture_output=True, 
                text=True, 
                creationflags=creation_flags, 
                shell=use_shell,
                timeout=3 # Seconds
            )
            return res.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {cmd_list}")
            return None
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return None

    def _refresh_windows_guid_map(self):
        """
        Refreshes the internal cache mapping GUIDs to Names via PowerShell.
        Only runs when necessary to save CPU.
        """
        if self.os_system != "Windows":
            return

        # logger.info("Refreshing Windows Interface Names (PowerShell)...")
        try:
            ps_cmd = "Get-NetAdapter | Select-Object Name, InterfaceGuid | ConvertTo-Json"
            cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
            
            output = self._run_command(cmd)
            if output:
                try:
                    data = json.loads(output)
                    # Ensure data is a list (PowerShell returns a dict if only one adapter exists)
                    if isinstance(data, dict):
                        data = [data]
                    
                    self._guid_name_cache = {} # Clear old cache
                    for item in data:
                        name = item.get("Name")
                        guid = item.get("InterfaceGuid")
                        if name and guid:
                            self._guid_name_cache[guid] = name
                    
                    self._cache_populated = True
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON from Get-NetAdapter")
        except Exception as e:
            logger.error(f"Error mapping Windows GUIDs: {e}")

    def _resolve_name(self, interface_id):
        """
        Resolves an interface ID (GUID/Name) to a friendly display name.
        Uses Caching on Windows.
        """
        if self.os_system != "Windows":
            return interface_id # Linux/Mac uses the name directly

        # Windows Logic
        # 1. Check Cache
        if interface_id in self._guid_name_cache:
            return self._guid_name_cache[interface_id]
        
        # 2. Lazy Load: If cache empty, populate it once
        if not self._cache_populated:
            self._refresh_windows_guid_map()
            if interface_id in self._guid_name_cache:
                return self._guid_name_cache[interface_id]
        
        # 3. Special Case: Localhost / Loopback often has no GUID map in Get-NetAdapter
        if interface_id == "{00000000-0000-0000-0000-000000000000}" or "loopback" in str(interface_id).lower():
            return "Local Loopback"

        return interface_id # Return GUID if resolution failed

    def get_all_interfaces(self):
        """
        Returns a list of dicts: [{'name': 'eth0', 'ip': '192.168.1.5'}, ...]
        Used to populate the GUI list. Forces a cache refresh on Windows.
        """
        interfaces = []
        
        # Force refresh when user opens settings to ensure new devices appear
        if self.os_system == "Windows":
            self._refresh_windows_guid_map()

        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                ip = "No IP"
                
                # Try to get IPv4, fallback to IPv6 for display if IPv4 is missing
                if netifaces.AF_INET in addrs:
                    ip = addrs[netifaces.AF_INET][0]['addr']
                elif netifaces.AF_INET6 in addrs:
                     # IPv6 often contains %interface suffix, strip it for cleaner display
                    ip = addrs[netifaces.AF_INET6][0]['addr'].split('%')[0]
                
                # Resolve Name
                display_name = self._resolve_name(iface)
                
                interfaces.append({
                    "name": display_name,
                    "ip": ip,
                    "id": iface 
                })
        except Exception as e:
            logger.error(f"Error listing interfaces: {e}")
        return interfaces

    # --- STRATEGY: PRECISION (OS Commands) ---
    def _get_active_routes_precision(self):
        """
        Method B: Checks specific routes using OS Commands (Slower on Windows, Precise on Linux/Mac).
        Checks routing for both IPv4 (1.1.1.1) and IPv6 (Cloudflare).
        """
        active_routes = []
        targets = [("1.1.1.1", False), ("2606:4700:4700::1111", True)]
        
        for ip, is_v6 in targets:
            iface = None
            
            # --- WINDOWS (PowerShell) ---
            if self.os_system == "Windows":
                # Find-NetRoute is precise but slow (spawns PowerShell)
                ps_cmd = f"Find-NetRoute -RemoteIP \"{ip}\" | Select-Object InterfaceAlias | ConvertTo-Json"
                output = self._run_command(["powershell", "-NoProfile", "-Command", ps_cmd])
                if output:
                    try:
                        data = json.loads(output)
                        if isinstance(data, list): iface = data[0].get("InterfaceAlias")
                        elif isinstance(data, dict): iface = data.get("InterfaceAlias")
                    except: pass
            
            # --- LINUX ---
            elif self.os_system == "Linux":
                cmd = ["ip", "route", "get", ip]
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'dev\s+(\S+)', output)
                    if match: iface = match.group(1)

            # --- MACOS ---
            elif self.os_system == "Darwin":
                cmd = ["route", "get", "-inet6", ip] if is_v6 else ["route", "get", ip]
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'interface:\s+(\S+)', output)
                    if match: iface = match.group(1)
            
            if iface:
                active_routes.append((iface, "IPv6" if is_v6 else "IPv4"))
                
        return active_routes

    # --- STRATEGY: PERFORMANCE (Netifaces) ---
    def _get_active_routes_performance(self):
        """
        Method A: Checks Default Gateway using netifaces (Fastest, Low CPU).
        Reads directly from memory without spawning subprocesses.
        """
        active_ids = []
        try:
            gws = netifaces.gateways()
            
            # The structure is: gws['default'][FAMILY_CONSTANT] = (IP, InterfaceID)
            if 'default' in gws:
                defaults = gws['default']
                
                # Check IPv4 (AF_INET)
                if netifaces.AF_INET in defaults:
                    # defaults[AF_INET] is a tuple/list: (IP, InterfaceID)
                    iface_id = defaults[netifaces.AF_INET][1]
                    active_ids.append((iface_id, "IPv4"))

                # Check IPv6 (AF_INET6)
                if netifaces.AF_INET6 in defaults:
                    iface_id = defaults[netifaces.AF_INET6][1]
                    active_ids.append((iface_id, "IPv6"))
                    
        except Exception as e:
            logger.error(f"Error reading gateways: {e}")
        
        # Resolve IDs to Friendly Names (especially for Windows)
        resolved_routes = []
        for iface_id, proto in active_ids:
            name = self._resolve_name(iface_id)
            resolved_routes.append((name, proto))
            
        return resolved_routes

    def is_secure(self):
        allowed_interfaces = self.cfg.get("valid_interfaces")
        
        if not allowed_interfaces:
            # If nothing configured, treated as unsafe logic usually, 
            # but logged as debug to avoid spam
            return False

        mode = self.cfg.get("detection_mode") # auto, performance, precision
        active_routes_found = []

        # === SELECT STRATEGY ===
        use_performance = False
        
        if mode == "performance":
            use_performance = True
        elif mode == "precision":
            use_performance = False
        else: 
            # AUTO MODE
            # Windows: Use Performance (Netifaces) to fix high CPU usage
            # Linux/Mac: Use Precision (OS Commands) as they are cheap and support split-tunneling better
            use_performance = (self.os_system == "Windows")

        if use_performance:
            active_routes_found = self._get_active_routes_performance()
        else:
            active_routes_found = self._get_active_routes_precision()

        # === VERIFICATION ===
        if not active_routes_found:
            # If the command timed out or network is down, we assume UNSAFE/Unknown
            logger.warning("No default gateway/route found (Network down?).")
            return False

        for iface_name, proto in active_routes_found:
            active_lower = iface_name.strip().lower()
            
            # Check if current interface is in allowed list
            is_allowed = False
            for allowed in allowed_interfaces:
                if allowed.strip().lower() == active_lower:
                    is_allowed = True
                    break
            
            # Debug log
            # logger.debug(f"{proto} via '{iface_name}': {'ALLOWED' if is_allowed else 'BLOCKED'}")

            if not is_allowed:
                # LEAK DETECTED!
                logger.warning(f"UNSAFE: {proto} traffic routing via '{iface_name}'")
                return False
        
        # If we reached here, at least one route was found, and ALL found routes were allowed.
        return True