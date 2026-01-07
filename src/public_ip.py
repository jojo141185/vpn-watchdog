import threading
import socket
import logging
import providers

logger = logging.getLogger("VPNWatchdog")

class PublicIPChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self._lock = threading.Lock()
        
        # Internal State - Now supports dual stack results
        self.last_result = {
            "ipv4": {"ip": None, "country": "??", "isp": "Unknown", "error": None},
            "ipv6": {"ip": None, "country": "??", "isp": "Unknown", "error": None},
            "is_secure": None, # Aggregate security state
            "details": ""      # Short summary for logs
        }
        
        self.is_checking = False

    def get_state(self):
        """Returns the last known state (thread-safe)."""
        with self._lock:
            # Return deep copy to avoid thread race conditions on nested dicts
            import copy
            return copy.deepcopy(self.last_result)

    def has_valid_data(self):
        """
        Returns True if at least ONE check (v4 or v6) has returned data or a connection error.
        We don't wait for both if one fails due to missing connectivity.
        """
        with self._lock:
            v4 = self.last_result["ipv4"]
            v6 = self.last_result["ipv6"]
            
            has_v4 = (v4["ip"] is not None) or (v4["error"] is not None)
            has_v6 = (v6["ip"] is not None) or (v6["error"] is not None)
            
            # If provider is "custom", user might only have configured one URL.
            # So one valid result is enough to say "we tried".
            return has_v4 or has_v6

    def run_check_async(self):
        """Starts the check in a background thread."""
        if self.is_checking:
            return
        
        t = threading.Thread(target=self._perform_check, daemon=True)
        t.start()

    def _perform_check(self):
        self.is_checking = True
        
        provider_key = self.cfg.get("public_check_provider")
        provider = providers.get_provider(provider_key)
        
        # Get Configured URLs
        # Note: Standard providers usually use system routing. 
        # To strictly test v4 vs v6, one usually needs specific DNS endpoints (e.g. ipv6.google.com).
        # For "Custom", the user provides them. For others, we try our best or accept what we get.
        
        url_v4 = self.cfg.get("public_custom_url")
        url_v6 = self.cfg.get("public_custom_url_v6")
        
        # Helper to run a single fetch
        def fetch_protocol(custom_url_override, proto_name):
            # For custom provider, we pass the config dict
            config_arg = None
            if provider_key == "custom":
                config_arg = {
                    "url": custom_url_override, # Might be empty if not set
                    "key_ip": self.cfg.get("public_custom_key_ip"),
                    "key_country": self.cfg.get("public_custom_key_country"),
                    "key_isp": self.cfg.get("public_custom_key_isp")
                }
                if not custom_url_override:
                    return {"success": False, "error": "Not Configured"}
            
            # Perform Fetch
            # if provider_key is NOT custom, 'custom_url_override' forces the provider to use that URL
            # instead of its default, which is useful if the user (or we) want to use specific endpoints.
            
            # Logic: If it's a standard provider, we don't have separate URLs configured in GUI
            # unless we hardcode them. For now, if no custom URL is provided for a standard provider,
            # it runs once (system default).
            
            if provider_key != "custom" and not custom_url_override:
                # If we are checking "ipv6" but have no specific URL, we skip to avoid duplicate v4 results
                if proto_name == "ipv6": 
                    return {"success": False, "error": "No IPv6 URL"}
            
            if provider_key == "custom":
                 return provider.fetch_details(config=config_arg, custom_url=custom_url_override)
            else:
                 return provider.fetch_details(custom_url=custom_url_override)

        # --- EXECUTE CHECKS ---
        # 1. IPv4 (Primary)
        # If standard provider, this uses system default route.
        res_v4 = fetch_protocol(url_v4, "ipv4")
        
        # 2. IPv6 (Secondary)
        # Only run if configured (Custom) or if we add logic for standard providers later.
        res_v6 = fetch_protocol(url_v6, "ipv6")

        # --- PROCESS RESULTS ---
        with self._lock:
            # Helper to process a result dict
            def update_internal(target_dict, data):
                if data["success"]:
                    target_dict["ip"] = data.get("ip")
                    target_dict["country"] = data.get("country", "??")
                    target_dict["isp"] = data.get("isp", "Unknown")
                    target_dict["error"] = None
                else:
                    target_dict["error"] = data.get("error")
                    # Keep old data if transient error? No, clear it to indicate issue.
                    # target_dict["ip"] = None 

            update_internal(self.last_result["ipv4"], res_v4)
            update_internal(self.last_result["ipv6"], res_v6)
            
            # --- SECURITY EVALUATION ---
            strategy = self.cfg.get("public_check_strategy")
            target_country = self.cfg.get("target_country").upper().strip()
            home_isp = self.cfg.get("home_isp").lower().strip()
            home_dns = self.cfg.get("home_dyndns").strip()
            
            # Resolve Home DynDNS if needed (once)
            home_ip_resolved = None
            if strategy == "ip_match" and home_dns:
                try:
                    if any(c.isalpha() for c in home_dns):
                        home_ip_resolved = socket.gethostbyname(home_dns)
                    else:
                        home_ip_resolved = home_dns
                except: pass

            def is_entry_safe(entry):
                if not entry["ip"]: return True # No connection = Secure (Fail Close)
                
                curr_c = entry["country"]
                curr_isp = entry["isp"]
                curr_ip = entry["ip"]
                
                safe = True
                
                # --- Logic Definitions ---
                
                # Strategy: Country (Geo-Fence)
                # Unsafe if current country matches Home Country
                if strategy == "country":
                    if target_country and curr_c and curr_c.upper() == target_country: safe = False
                    
                # Strategy: ISP (Home ISP check)
                # Unsafe if current ISP contains Home ISP string
                elif strategy == "isp":
                    if home_isp and curr_isp and home_isp in curr_isp.lower(): safe = False
                    
                # Strategy: Combined (Default)
                # Unsafe if BOTH Country AND ISP match Home settings
                elif strategy == "combined":
                    c_match = (target_country and curr_c and curr_c.upper() == target_country)
                    i_match = (home_isp and curr_isp and home_isp in curr_isp.lower())
                    if c_match and i_match: safe = False

                # Strategy: IP / DynDNS Match
                # Unsafe if current IP matches the resolved IP of the DynDNS/Host
                elif strategy == "ip_match":
                    if home_ip_resolved and curr_ip == home_ip_resolved: safe = False
                    
                return safe

            safe_v4 = is_entry_safe(self.last_result["ipv4"])
            safe_v6 = is_entry_safe(self.last_result["ipv6"])
            
            # Aggregate: Unsafe if ANY active connection is unsafe
            self.last_result["is_secure"] = safe_v4 and safe_v6
            
            # Generate Summary
            summaries = []
            if self.last_result["ipv4"]["ip"]:
                inf = self.last_result["ipv4"]
                summaries.append(f"v4: {inf['country']}")
            if self.last_result["ipv6"]["ip"]:
                inf = self.last_result["ipv6"]
                summaries.append(f"v6: {inf['country']}")
                
            self.last_result["details"] = ", ".join(summaries) if summaries else "No Data"
            
            # Logging
            if not self.last_result["is_secure"]:
                logger.warning(f"Public Check LEAK: {summaries}")
            else:
                logger.info(f"Public Check: {summaries} -> SAFE")

        self.is_checking = False