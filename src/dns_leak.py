import threading
import requests
import logging
import socket
import json
import time
from random import randint

logger = logging.getLogger("VPNWatchdog")

class DnsLeakChecker:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self._lock = threading.Lock()
        
        self.last_result = {
            "servers": [], # List of detected DNS servers (IP, Country, ISP)
            "count": 0,
            "is_secure": None, # Undefined until proven otherwise
            "error": None
        }
        self.is_checking = False

    def get_state(self):
        with self._lock:
            return self.last_result.copy()

    def run_check_async(self):
        if self.is_checking: return
        t = threading.Thread(target=self._perform_check, daemon=True)
        t.start()

    def _perform_check(self):
        self.is_checking = True
        # logger.info("Starting DNS Leak Test...") # Reduced verbosity
        
        try:
            # 1. Get unique ID
            resp = requests.get("https://bash.ws/id", timeout=10)
            if resp.status_code != 200:
                raise Exception("Could not fetch Leak ID")
            
            leak_id = resp.text.strip()
            
            # 2. Trigger Resolution (The Leak Trick)
            # We resolve 10 subdomains. The OS will query the configured DNS server.
            for i in range(0, 10):
                domain = f"{i}.{leak_id}.bash.ws"
                try:
                    socket.gethostbyname(domain)
                except socket.error:
                    pass 
                time.sleep(0.1) 

            # 3. Fetch Results
            url = f"https://bash.ws/dnsleak/test/{leak_id}?json"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            detected_servers = []
            
            for entry in data:
                if entry.get('type') == 'dns':
                    server_info = {
                        "ip": entry.get("ip"),
                        "country": entry.get("country_name"),
                        "asn": entry.get("asn", "Unknown") # ASN usually contains ISP name
                    }
                    detected_servers.append(server_info)

            # 4. Analyze Security
            is_safe = True
            alert_on_home = self.cfg.get("dns_alert_on_home_isp")
            home_isp = self.cfg.get("home_isp").lower().strip()
            
            if not detected_servers:
                logger.warning("DNS Check: No servers detected (Timeout or Blocked?)")
            
            # Logic Update: If alert is on but no Home ISP configured, we can't check.
            if alert_on_home and not home_isp:
                logger.warning("DNS Guard: 'Alert on Home ISP' enabled, but no 'Home ISP' configured in Connectivity settings!")
                # We keep is_safe = True because we can't prove it's unsafe without config.
            
            elif alert_on_home and home_isp:
                for srv in detected_servers:
                    # Check ASN/ISP string
                    isp_str = srv["asn"].lower()
                    if home_isp in isp_str:
                        is_safe = False
                        logger.warning(f"DNS LEAK: Detected Home ISP DNS: {srv['ip']} ({srv['asn']})")

            with self._lock:
                self.last_result["servers"] = detected_servers
                self.last_result["count"] = len(detected_servers)
                self.last_result["is_secure"] = is_safe
                self.last_result["error"] = None
            
            # Log result
            srv_count = len(detected_servers)
            status_str = "SAFE" if is_safe else "LEAK"
            logger.info(f"DNS Check: {srv_count} servers detected -> {status_str}")

        except Exception as e:
            logger.error(f"DNS Check failed: {e}")
            with self._lock:
                self.last_result["error"] = str(e)
        
        self.is_checking = False