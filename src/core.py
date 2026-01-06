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

    def _get_windows_guid_map(self):
        """
        Returns a dict mapping Windows Interface GUIDs to Friendly Names using JSON.
        Robust against language settings and formatting.
        Example: {'{8A...}': 'NordLynx', ...}
        """
        guid_map = {}
        try:
            # Use ConvertTo-Json for reliable parsing
            ps_cmd = "Get-NetAdapter | Select-Object Name, InterfaceGuid | ConvertTo-Json"
            cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
            
            output = self._run_command(cmd)
            if output:
                try:
                    data = json.loads(output)
                    # Ensure data is a list (PowerShell returns a dict if only one adapter exists)
                    if isinstance(data, dict):
                        data = [data]
                    
                    for item in data:
                        name = item.get("Name")
                        guid = item.get("InterfaceGuid")
                        if name and guid:
                            guid_map[guid] = name
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON from Get-NetAdapter: {output}")
        except Exception as e:
            logger.error(f"Error mapping Windows GUIDs via JSON: {e}")
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
                # On Windows, netifaces uses the GUID as the interface ID
                # On Linux/macOS, it uses the name (e.g., 'eth0', 'en0')
                
                addrs = netifaces.ifaddresses(iface)
                ip = "No IP"
                
                # Try to get IPv4, fallback to IPv6 for display if IPv4 is missing
                if netifaces.AF_INET in addrs:
                    ip = addrs[netifaces.AF_INET][0]['addr']
                elif netifaces.AF_INET6 in addrs:
                     # IPv6 often contains %interface suffix, strip it for cleaner display
                    ip = addrs[netifaces.AF_INET6][0]['addr'].split('%')[0]
                
                # Determine Display Name
                display_name = iface
                if self.os_system == "Windows":
                    if iface in win_map:
                        display_name = win_map[iface]
                    else:
                        # Fallback try: check if win_map keys are slightly different (case sensitivity)
                        for guid, name in win_map.items():
                            if guid.lower() == iface.lower():
                                display_name = name
                                break
                
                interfaces.append({
                    "name": display_name,
                    "ip": ip,
                    "id": iface 
                })
        except Exception as e:
            logger.error(f"Error listing interfaces: {e}")
        return interfaces

    def _get_interface_for_ip(self, target_ip, is_ipv6=False):
        """
        Determines the name of the interface routing traffic to a specific IP.
        Returns the Friendly Name (Windows) or Interface Name (Linux/Mac).
        Returns None if no route is found or protocol is inactive.
        """
        try:
            # --- LINUX ---
            if self.os_system == "Linux":
                # 'ip route get' usually handles both v4 and v6 if the IP format is detected,
                # but explicit 'ip -6' can be safer on some legacy stacks.
                # We use standard 'ip route get' first.
                cmd = ["ip", "route", "get", target_ip]
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'dev\s+(\S+)', output)
                    if match:
                        return match.group(1)

            # --- MACOS ---
            elif self.os_system == "Darwin":
                cmd = ["route", "get", target_ip]
                if is_ipv6:
                    # macOS requires explicit flag for IPv6 route lookup
                    cmd = ["route", "get", "-inet6", target_ip]
                
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'interface:\s+(\S+)', output)
                    if match:
                        return match.group(1)

            # --- WINDOWS ---
            elif self.os_system == "Windows":
                # Powershell: Find-NetRoute -> JSON
                # Find-NetRoute handles IPv6 automatically if the RemoteIP is v6 format
                ps_cmd = f"Find-NetRoute -RemoteIP \"{target_ip}\" | Select-Object InterfaceAlias | ConvertTo-Json"
                output = self._run_command(["powershell", "-NoProfile", "-Command", ps_cmd])
                
                if output:
                    try:
                        data = json.loads(output)
                        # Handle List vs Dict (Single vs Multi route)
                        if isinstance(data, list):
                            return data[0].get("InterfaceAlias")
                        elif isinstance(data, dict):
                            return data.get("InterfaceAlias")
                    except json.JSONDecodeError:
                        # This can happen if output is empty or not JSON (e.g. error message)
                        pass

        except Exception as e:
            # Logging as debug because failing to find a route (e.g. no IPv6 stack) is a valid state
            logger.debug(f"Routing check failed for {target_ip} ({self.os_system}): {e}")
        
        return None

    def is_secure(self):
        # 1. Load config
        allowed_interfaces = self.cfg.get("valid_interfaces")
        
        if not allowed_interfaces:
            # If nothing configured, treated as unsafe logic usually, 
            # but logged as debug to avoid spam
            return False

        # 2. Check Routing for both Protocols
        # We check Cloudflare DNS for both IPv4 and IPv6 to see which interface carries the traffic.
        targets = [
            ("1.1.1.1", False),              # IPv4
            ("2606:4700:4700::1111", True)   # IPv6
        ]
        
        active_routes_found = False
        
        for ip, is_v6 in targets:
            active_iface = self._get_interface_for_ip(ip, is_v6)
            
            if active_iface:
                active_routes_found = True
                
                # Normalize names for comparison
                active_lower = active_iface.strip().lower()
                
                is_allowed = False
                for allowed in allowed_interfaces:
                    if allowed.strip().lower() == active_lower:
                        is_allowed = True
                        break
                
                # Log the check result for debugging
                logger.debug(f"Checking {ip} ({'IPv6' if is_v6 else 'IPv4'}) via '{active_iface}': {'ALLOWED' if is_allowed else 'BLOCKED'}")

                if not is_allowed:
                    # LEAK DETECTED!
                    # If ANY active protocol is using a non-allowed interface, the connection is unsafe.
                    logger.warning(f"UNSAFE: Traffic for {ip} is going through '{active_iface}' (Not in allowed list).")
                    return False
        
        if not active_routes_found:
            # If the command timed out or network is down (no routes for v4 OR v6), we assume UNSAFE/Unknown.
            # This prevents the 'green' status if network is actually dead but app is running.
            logger.warning("Could not determine any active routing interface (Network down?).")
            return False

        # If we reached here, at least one route was found, and ALL found routes were allowed.
        return True