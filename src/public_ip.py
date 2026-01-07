import threading
import socket
import logging
import providers

logger = logging.getLogger("VPNWatchdog")

class PublicIPChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self._lock = threading.Lock()
        
        # Internal State
        self.last_result = {
            "ipv4": None,
            "country": "??",
            "isp": "Unknown",
            "is_secure": None, # Undefined until proven otherwise
            "error": None
        }
        
        self.is_checking = False

    def get_state(self):
        """Returns the last known state (thread-safe)."""
        with self._lock:
            return self.last_result.copy()

    def run_check_async(self):
        """Starts the check in a background thread."""
        if self.is_checking:
            return
        
        t = threading.Thread(target=self._perform_check, daemon=True)
        t.start()

    def _perform_check(self):
        self.is_checking = True
        
        # 1. Get Configured Provider
        provider_key = self.cfg.get("public_check_provider")
        custom_url = self.cfg.get("public_custom_url")
        provider = providers.get_provider(provider_key)
        
        # 2. Fetch Data
        data = provider.fetch_details(custom_url=custom_url)
        
        with self._lock:
            if not data["success"]:
                self.last_result["error"] = data["error"]
                self.is_checking = False
                logger.debug(f"Public IP Fetch failed: {data['error']}")
                return

            # Extract Info
            current_ip = data.get("ip", "0.0.0.0")
            current_country = data.get("country", "??")
            current_isp = data.get("isp", "Unknown")

            self.last_result["ipv4"] = current_ip
            self.last_result["country"] = current_country
            self.last_result["isp"] = current_isp
            self.last_result["error"] = None

            # 3. Evaluate Security based on Strategy
            strategy = self.cfg.get("public_check_strategy")
            is_safe = True
            
            # --- Logic Definitions ---
            
            # Strategy: Country (Geo-Fence)
            # Unsafe if current country matches Home Country
            if strategy == "country":
                target = self.cfg.get("target_country").upper().strip()
                if target and current_country and current_country.upper() == target:
                    is_safe = False
                    logger.warning(f"Public Check: Country match detected! (Home: {target}, Current: {current_country})")

            # Strategy: ISP (Home ISP check)
            # Unsafe if current ISP contains Home ISP string
            elif strategy == "isp":
                home_isp = self.cfg.get("home_isp").lower().strip()
                if home_isp and current_isp and home_isp in current_isp.lower():
                    is_safe = False
                    logger.warning(f"Public Check: ISP match detected! (Home: {home_isp}, Current: {current_isp})")

            # Strategy: Combined (Default)
            # Unsafe if BOTH Country AND ISP match Home settings
            elif strategy == "combined":
                target_c = self.cfg.get("target_country").upper().strip()
                home_i = self.cfg.get("home_isp").lower().strip()
                
                c_match = (target_c and current_country and current_country.upper() == target_c)
                i_match = (home_i and current_isp and home_i in current_isp.lower())
                
                if c_match and i_match:
                    is_safe = False
                    logger.warning(f"Public Check: Full Home Match! ({target_c} + {home_i})")
                elif c_match or i_match:
                    # Optional: Log warning if only one matches but keep it safe?
                    # Request said "Default Setting", usually implying strong correlation.
                    # We stick to AND logic here as per description "Vergleicht beides".
                    pass

            # Strategy: IP / DynDNS Match
            # Unsafe if current IP matches the resolved IP of the DynDNS/Host
            elif strategy == "ip_match":
                home_dns = self.cfg.get("home_dyndns").strip()
                if home_dns:
                    try:
                        # Check if input is IP or Hostname
                        home_ip = home_dns # assume IP
                        # crude check for hostname
                        if any(c.isalpha() for c in home_dns):
                            home_ip = socket.gethostbyname(home_dns)
                        
                        if home_ip == current_ip:
                            is_safe = False
                            logger.warning(f"Public Check: Public IP matches Home IP! ({current_ip})")
                    except Exception as e:
                        logger.error(f"DynDNS Resolution failed: {e}")

            self.last_result["is_secure"] = is_safe
            
            # Reduce log spam: log only on change or warning could be better, but info is good for now
            log_sym = "SAFE" if is_safe else "UNSAFE"
            logger.info(f"Public Check: {current_country} - {current_isp} -> {log_sym}")

        self.is_checking = False