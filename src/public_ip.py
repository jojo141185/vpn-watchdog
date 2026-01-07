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
        url_v4 = self.cfg.get("public_custom_url")
        url_v6 = self.cfg.get("public_custom_url_v6")
        
        # Helper to run a single fetch
        def fetch_protocol(custom_url_override, proto_name, cached_data):
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
            
            # If we are checking "ipv6" but have no specific URL AND provider is NOT Smart, 
            # we skip to avoid duplicate v4 results (standard providers route via OS default).
            # The 'Smart' provider handles 'version' argument to select correct ipify endpoint.
            if provider_key != "custom" and provider_key != "smart" and not custom_url_override:
                if proto_name == "ipv6": 
                    return {"success": False, "error": "No IPv6 URL"}
            
            # Extract Cache info for Smart Provider
            cached_ip = cached_data.get("ip")
            cached_details = cached_data
            
            return provider.fetch_details(
                config=config_arg, 
                custom_url=custom_url_override,
                version=proto_name,
                cached_ip=cached_ip,
                cached_details=cached_details
            )

        # --- EXECUTE CHECKS ---
        # We pass the current cached data to allow the SmartProvider to optimize
        with self._lock:
            cache_v4 = self.last_result["ipv4"].copy()
            cache_v6 = self.last_result["ipv6"].copy()

        # 1. IPv4 (Primary)
        res_v4 = fetch_protocol(url_v4, "ipv4", cache_v4)
        
        # 2. IPv6 (Secondary)
        res_v6 = fetch_protocol(url_v6, "ipv6", cache_v6)

        # --- PROCESS RESULTS ---
        with self._lock:
            # Helper to process a result dict
            def update_internal(target_dict, data):
                if data["success"]:
                    target_dict["ip"] = data.get("ip")
                    target_dict["country"] = data.get("country", "??")
                    target_dict["isp"] = data.get("isp", "Unknown")
                    target_dict["error"] = data.get("error") # Might contain partial error (Geo failed)
                else:
                    target_dict["error"] = data.get("error")
                    # We do NOT clear IP/Country here if it was a transient network error,
                    # BUT if the error is "Not Configured" or similar, we should probably reflect that.
                    # For safety in VPN context: If check fails, we assume state is unknown/unsafe.
                    # So sticking with error is safer.

            update_internal(self.last_result["ipv4"], res_v4)
            update_internal(self.last_result["ipv6"], res_v6)
            
            # --- SECURITY EVALUATION ---
            strategy = self.cfg.get("public_check_strategy")
            target_country = self.cfg.get("target_country").upper().strip()
            home_isp = self.cfg.get("home_isp").lower().strip()
            home_dns = self.cfg.get("home_dyndns").strip()
            
            # Debug Log for Strategy
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"PublicIP: Eval Strategy='{strategy}', TargetCountry='{target_country}', HomeISP='{home_isp}'")
            
            # Resolve Home DynDNS if needed (once)
            home_ip_v4 = None
            home_ip_v6 = None
            
            if strategy == "ip_match" and home_dns:
                # Try resolve IPv4
                try:
                    if any(c.isalpha() for c in home_dns):
                        home_ip_v4 = socket.gethostbyname(home_dns)
                    else:
                        home_ip_v4 = home_dns # Already IP
                except: pass
                
                # Try resolve IPv6
                # We only try this if it's a hostname. If it's a literal IP string, checking if it is v6 is complex but less likely needed here.
                try:
                    if any(c.isalpha() for c in home_dns):
                        # getaddrinfo returns list of (family, socktype, proto, canonname, sockaddr)
                        # sockaddr for v6 is (address, port, ...)
                        infos = socket.getaddrinfo(home_dns, None, socket.AF_INET6)
                        if infos:
                            home_ip_v6 = infos[0][4][0]
                except: pass

            def is_entry_safe(entry, proto_label):
                if not entry["ip"]: return True # No connection = Secure (Fail Close)
                
                curr_c = entry.get("country", "??")
                curr_isp = entry.get("isp", "Unknown")
                curr_ip = entry.get("ip")
                
                safe = True
                reason = "OK"
                
                # Strategy: Country (Geo-Fence)
                if strategy == "country":
                    if target_country and curr_c and curr_c.upper() == target_country: 
                        safe = False
                        reason = f"Country Match ({target_country})"
                        
                # Strategy: ISP (Home ISP check)
                elif strategy == "isp":
                    if home_isp and curr_isp and home_isp in curr_isp.lower(): 
                        safe = False
                        reason = f"ISP Match ({home_isp})"                    
                
                # Strategy: Combined (Default)
                elif strategy == "combined":
                    c_match = (target_country and curr_c and curr_c.upper() == target_country)
                    i_match = (home_isp and curr_isp and home_isp in curr_isp.lower())
                    if c_match and i_match: 
                        safe = False
                        reason = "Combined Match (Country+ISP)"
                        
                # Strategy: IP / DynDNS Match
                elif strategy == "ip_match":
                    # Check against v4 resolved
                    if home_ip_v4 and curr_ip == home_ip_v4:
                        safe = False
                        reason = f"IP Match v4 ({home_ip_v4})"
                    # Check against v6 resolved
                    elif home_ip_v6 and curr_ip == home_ip_v6:
                        safe = False
                        reason = f"IP Match v6 ({home_ip_v6})"
                    elif not home_ip_v4 and not home_ip_v6:
                        # Fallback if resolution failed entirely but user wants IP match
                        pass
                
                # Detailed Comparison Log
                if logger.isEnabledFor(logging.DEBUG):
                    status = "UNSAFE" if not safe else "SAFE"
                    logger.debug(f"  [{proto_label}] {curr_ip} | {curr_c} | {curr_isp} -> {status} ({reason})")

                return safe

            safe_v4 = is_entry_safe(self.last_result["ipv4"], "v4")
            safe_v6 = is_entry_safe(self.last_result["ipv6"], "v6")
            
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