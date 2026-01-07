import netifaces
import platform
import logging
import subprocess
import json
import re
import time
from public_ip import PublicIPChecker
from dns_leak import DnsLeakChecker

logger = logging.getLogger("VPNWatchdog")

class VPNChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.os_system = platform.system()
        self.default_keywords = ["nord", "tun", "tap", "wg", "ppp", "ipsec", "wireguard"]
        
        # Sub-Modules
        self.public_checker = PublicIPChecker(self.cfg)
        self.dns_checker = DnsLeakChecker(self.cfg)
        
        # State Tracking
        self._guid_name_cache = {}
        self._cache_populated = False
        
        # Initialization Flag
        self.initial_check_done = False
        
        # Timers
        self.last_public_check = 0
        self.last_dns_check = 0

        # Latest Aggregated State (Safe Defaults)
        self.current_state = {
            "status": "initializing", # safe, unsafe, scanning, initializing
            "global_secure": True,
            "summary_details": "Init",
            "country": "??",
            "routing": {"secure": True, "details": "Init", "enabled": False},
            "public": {"secure": True, "data": {}, "enabled": False},
            "dns": {"secure": True, "data": {}, "enabled": False}
        }

    def _run_command(self, cmd_list, use_shell=False):
        try:
            creation_flags = 0x08000000 if self.os_system == "Windows" else 0
            res = subprocess.run(
                cmd_list, capture_output=True, text=True, 
                creationflags=creation_flags, shell=use_shell, timeout=3 
            )
            return res.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {cmd_list}")
            return None
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return None

    def _refresh_windows_guid_map(self):
        if self.os_system != "Windows": return
        try:
            ps_cmd = "Get-NetAdapter | Select-Object Name, InterfaceGuid | ConvertTo-Json"
            cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
            output = self._run_command(cmd)
            if output:
                try:
                    data = json.loads(output)
                    if isinstance(data, dict): data = [data]
                    self._guid_name_cache = {} 
                    for item in data:
                        name = item.get("Name")
                        guid = item.get("InterfaceGuid")
                        if name and guid:
                            self._guid_name_cache[guid] = name
                    self._cache_populated = True
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    def _resolve_name(self, interface_id):
        if self.os_system != "Windows": return interface_id 
        if interface_id in self._guid_name_cache: return self._guid_name_cache[interface_id]
        if not self._cache_populated:
            self._refresh_windows_guid_map()
            if interface_id in self._guid_name_cache: return self._guid_name_cache[interface_id]
        if interface_id == "{00000000-0000-0000-0000-000000000000}" or "loopback" in str(interface_id).lower():
            return "Local Loopback"
        return interface_id

    def get_all_interfaces(self):
        interfaces = []
        if self.os_system == "Windows": self._refresh_windows_guid_map()
        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                ip = "No IP"
                if netifaces.AF_INET in addrs: ip = addrs[netifaces.AF_INET][0]['addr']
                elif netifaces.AF_INET6 in addrs: ip = addrs[netifaces.AF_INET6][0]['addr'].split('%')[0]
                display_name = self._resolve_name(iface)
                interfaces.append({ "name": display_name, "ip": ip, "id": iface })
        except Exception as e:
            logger.error(f"Error listing interfaces: {e}")
        return interfaces

    # --- ROUTING CHECKS ---
    def _get_active_routes_precision(self):
        active_routes = []
        targets = [("1.1.1.1", False), ("2606:4700:4700::1111", True)]
        for ip, is_v6 in targets:
            iface = None
            if self.os_system == "Windows":
                ps_cmd = f"Find-NetRoute -RemoteIP \"{ip}\" | Select-Object InterfaceAlias | ConvertTo-Json"
                output = self._run_command(["powershell", "-NoProfile", "-Command", ps_cmd])
                if output:
                    try:
                        data = json.loads(output)
                        if isinstance(data, list): iface = data[0].get("InterfaceAlias")
                        elif isinstance(data, dict): iface = data.get("InterfaceAlias")
                    except: pass
            elif self.os_system == "Linux":
                cmd = ["ip", "route", "get", ip]
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'dev\s+(\S+)', output)
                    if match: iface = match.group(1)
            elif self.os_system == "Darwin":
                cmd = ["route", "get", "-inet6", ip] if is_v6 else ["route", "get", ip]
                output = self._run_command(cmd)
                if output:
                    match = re.search(r'interface:\s+(\S+)', output)
                    if match: iface = match.group(1)
            
            if iface: active_routes.append((iface, "IPv6" if is_v6 else "IPv4"))
        return active_routes

    def _get_active_routes_performance(self):
        active_ids = []
        try:
            gws = netifaces.gateways()
            if 'default' in gws:
                defaults = gws['default']
                if netifaces.AF_INET in defaults: active_ids.append((defaults[netifaces.AF_INET][1], "IPv4"))
                if netifaces.AF_INET6 in defaults: active_ids.append((defaults[netifaces.AF_INET6][1], "IPv6"))
        except Exception: pass
        
        resolved_routes = []
        for iface_id, proto in active_ids:
            name = self._resolve_name(iface_id)
            resolved_routes.append((name, proto))
        return resolved_routes

    # --- MAIN CHECK ROUTINE ---
    def check_status(self):
        """
        Orchestrates all checks. Updates and returns the single unified state object.
        """
        now = time.time()

        # 1. LOCAL ROUTING CHECK
        local_secure = None, # Undefined until proven otherwise
        local_details = "OK"
        active_routes_str = []
        
        rt_en = self.cfg.get("routing_check_enabled")
        if rt_en:
            allowed_interfaces = self.cfg.get("valid_interfaces")
            if not allowed_interfaces:
                local_secure = False
                local_details = "Not Configured"
            else:
                mode = self.cfg.get("detection_mode")
                use_perf = (mode == "performance") or (mode == "auto" and self.os_system == "Windows")
                
                if use_perf: routes = self._get_active_routes_performance()
                else: routes = self._get_active_routes_precision()

                if not routes:
                    local_secure = False
                    local_details = "No Network"
                else:
                    for iface, proto in routes:
                        active_routes_str.append(f"{iface} ({proto})")
                        active_lower = iface.strip().lower()
                        if not any(a.strip().lower() == active_lower for a in allowed_interfaces):
                            local_secure = False
                            local_details = f"Leak: {iface} ({proto})"
            
            if local_secure and active_routes_str:
                local_details = ", ".join(active_routes_str)
        else:
            local_details = "Disabled"
        
        # 2. PUBLIC CHECK (Async Trigger)
        pb_en = self.cfg.get("public_check_enabled")
        if pb_en:
            interval = int(self.cfg.get("public_check_interval"))
            # Triggers immediately on first run because last_public_check is initialized to 0
            if now - self.last_public_check > interval:
                self.public_checker.run_check_async()
                self.last_public_check = now
        
        p_state = self.public_checker.get_state()
        public_secure = p_state["is_secure"]
        
        # Determine "Main" country for Icon display (prefer v4, else v6)
        main_country = p_state["ipv4"].get("country")
        if not main_country or main_country == "??":
            main_country = p_state["ipv6"].get("country", "??")
        
        # 3. DNS CHECK (Async Trigger)
        dns_en = self.cfg.get("dns_check_enabled")
        if dns_en:
            interval = int(self.cfg.get("dns_check_interval"))
            # Triggers immediately on first run
            if now - self.last_dns_check > interval:
                self.dns_checker.run_check_async()
                self.last_dns_check = now
                
        d_state = self.dns_checker.get_state()
        dns_secure = d_state["is_secure"]

        # --- INITIALIZATION & SECURITY LOGIC ---
        
        # A. Check for known failures (FAIL-FAST)
        # If any enabled module reports insecure, we are globally insecure immediately.
        is_globally_secure = True
        
        if rt_en and local_secure is False: is_globally_secure = False
        if pb_en and public_secure is False: is_globally_secure = False
        if dns_en and dns_secure is False: is_globally_secure = False
        
        # B. Check for pending initialization
        # Only relevant if we are currently considered "secure" (no known errors yet).
        init_pending = False
        if is_globally_secure:
            if pb_en and not self.public_checker.has_valid_data():
                init_pending = True
            if dns_en and not self.dns_checker.has_valid_data():
                init_pending = True

        # C. Determine Display Status
        effective_status = "safe"
        
        if not is_globally_secure:
            effective_status = "unsafe"
        elif init_pending:
            effective_status = "scanning"
        else:
            effective_status = "safe"

        # D. Update State Object
        if not (rt_en or pb_en or dns_en):
            is_globally_secure = True
            effective_status = "safe"

        if not init_pending:
            self.initial_check_done = True
        
        # --- DETAILED DEBUG LOGGING ---
        # Only log if logLevel is DEBUG to avoid spam, but provide deep insight when requested.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- CHECK REPORT ---")
            
            # Routing Report
            r_stat = "DISABLED"
            if rt_en: r_stat = "SECURE" if local_secure else "UNSAFE"
            if local_secure is None and rt_en: r_stat = "PENDING"
            logger.debug(f"Routing: {r_stat} (Details: {local_details})")
            
            # Public Report
            p_stat = "DISABLED"
            if pb_en: 
                p_stat = "SECURE" if public_secure else "UNSAFE"
                # Show why unsafe
                if not public_secure:
                    # Retrieve the specific reasons calculated inside public_ip logic if available
                    # otherwise reconstruct summary
                    reasons = []
                    if p_state["ipv4"].get("reason"): reasons.append(f"v4: {p_state['ipv4']['reason']}")
                    if p_state["ipv6"].get("reason"): reasons.append(f"v6: {p_state['ipv6']['reason']}")
                    
                    if reasons:
                        p_stat += f" [Reason: {', '.join(reasons)}]"
            
            if public_secure is None and pb_en: p_stat = "PENDING"
            logger.debug(f"Public:  {p_stat}")
            
            # DNS Report
            d_stat = "DISABLED"
            if dns_en: d_stat = "SECURE" if dns_secure else "UNSAFE"
            if dns_secure is None and dns_en: d_stat = "PENDING"
            
            # List DNS ASNs
            dns_asns = []
            if d_state.get("servers"):
                dns_asns = [s.get("asn", "Unknown") for s in d_state.get("servers")]
            
            logger.debug(f"DNS:     {d_stat} (Servers: {len(dns_asns)} {dns_asns})")
            
            # Global Result
            logger.debug(f"GLOBAL:  {effective_status.upper()} (Scanning: {init_pending})")
            logger.debug("--------------------")

        self.current_state = {
            "status": effective_status,
            "global_secure": is_globally_secure, 
            "summary_details": local_details,
            "country": main_country,
            "routing": {
                "enabled": rt_en,
                "secure": local_secure,
                "details": local_details
            },
            "public": {
                "enabled": pb_en,
                "secure": public_secure,
                "data": p_state
            },
            "dns": {
                "enabled": dns_en,
                "secure": dns_secure,
                "data": d_state
            }
        }
        
        return self.current_state

    def get_dashboard_data(self):
        """Used by the GUI to get full details."""
        return self.current_state