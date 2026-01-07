import requests
import logging

logger = logging.getLogger("VPNWatchdog")

class IPProvider:
    """Base class for IP Information Providers."""
    def get_name(self):
        return "Unknown"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, version=None, cached_ip=None, cached_details=None, config=None):
        """
        Fetches details.
        
        Args:
            timeout (int): Request timeout.
            custom_url (str): Override URL (used for v4/v6 specific checks).
            target_ip (str): If provided, fetch info for this IP (server-side lookup).
            version (str): "ipv4" or "ipv6" - used by SmartProvider to select correct endpoint.
            cached_ip (str): The previously detected IP (to avoid Geo-Lookup if unchanged).
            cached_details (dict): The previously detected Geo-Data.
            config (dict): Config dictionary (used by CustomProvider).
            
        Returns:
            dict: { "ip": str, "country": str, "isp": str, "success": bool, "error": str/None }
        """
        raise NotImplementedError

# --- 1. CORE IP DETECTOR (No Geo) ---
class IpifyProvider(IPProvider):
    def get_name(self):
        return "ipify (IP Only / No Geo)"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, version=None, **kwargs):
        # ipify is used primarily for IP detection.
        if custom_url:
            url = custom_url
        else:
            if version == "ipv6":
                url = "https://api6.ipify.org?format=json"
            elif version == "ipv4":
                url = "https://api.ipify.org?format=json"
            else:
                url = "https://api64.ipify.org?format=json"

        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ip": data.get("ip"),
                    "country": "??", # ipify does not provide Geo
                    "isp": "Unknown",
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"ipify HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# --- 2. GEO PROVIDERS ---

class FreeIpApiProvider(IPProvider):
    def get_name(self):
        return "FreeIPAPI.com"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, **kwargs):
        base_url = "https://free.freeipapi.com/api/json"
        url = f"{base_url}/{target_ip}" if target_ip else base_url
        
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ip": data.get("ipAddress"),
                    "country": data.get("countryCode"),
                    "isp": data.get("asnOrganization") or "Unknown",
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"FreeIPAPI HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class IpApiCoProvider(IPProvider):
    def get_name(self):
        return "ipapi.co"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, **kwargs):
        base_url = "https://ipapi.co"
        url = f"{base_url}/{target_ip}/json/" if target_ip else f"{base_url}/json/"
        
        # ipapi.co requires User-Agent usually
        headers = {'User-Agent': 'VPNWatchdog/1.0'}
        
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    return {"success": False, "error": data.get("reason", "API Error")}
                    
                return {
                    "ip": data.get("ip"),
                    "country": data.get("country_code"),
                    "isp": data.get("org") or "Unknown",
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"ipapi.co HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class IpApiComProvider(IPProvider):
    def get_name(self):
        return "ip-api.com (No SSL)"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, **kwargs):
        base = "http://ip-api.com/json/" # Note: HTTP only for free tier
        fields = "?fields=status,message,query,countryCode,isp"
        url = f"{base}{target_ip}{fields}" if target_ip else f"{base}{fields}"
        
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "fail":
                    return {"success": False, "error": data.get("message")}
                
                return {
                    "ip": data.get("query"),
                    "country": data.get("countryCode"),
                    "isp": data.get("isp"),
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"ip-api.com HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class IpWhoIsProvider(IPProvider):
    def get_name(self):
        return "ipwho.is"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, **kwargs):
        base_url = "http://ipwho.is/"
        if target_ip:
            url = f"{base_url}{target_ip}?output=json"
        else:
            url = f"{base_url}?output=json"
            
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("success", True):
                    return {"success": False, "error": data.get("message", "API Error")}
                
                return {
                    "ip": data.get("ip"),
                    "country": data.get("country_code"),
                    "isp": data.get("connection", {}).get("isp") or data.get("isp"),
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class CustomProvider(IPProvider):
    def get_name(self):
        return "Custom API"

    def fetch_details(self, timeout=5, config=None, custom_url=None, target_ip=None, **kwargs):
        if not config:
            return {"success": False, "error": "No config provided"}
            
        url = custom_url if custom_url else config.get("url")
        key_ip = config.get("key_ip", "ip")
        key_country = config.get("key_country", "country")
        key_isp = config.get("key_isp", "isp")

        if not url:
            return {"success": False, "error": "No URL set"}
        
        if target_ip and "{ip}" in url:
            url = url.replace("{ip}", target_ip)
        
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                
                ip_val = data.get(key_ip)
                country_val = data.get(key_country)
                isp_val = data.get(key_isp)

                if not ip_val:
                     return {"success": False, "error": f"IP not found using key '{key_ip}'"}

                return {
                    "ip": ip_val,
                    "country": country_val or "??",
                    "isp": isp_val or "Unknown",
                    "success": True,
                    "error": None
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# --- 3. SMART HYBRID PROVIDER ---

class SmartProvider(IPProvider):
    def get_name(self):
        return "Smart Hybrid (Recommended)"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None, version=None, cached_ip=None, cached_details=None, **kwargs):
        """
        Logic:
        1. Get IP from ipify (Very stable, supports v4/v6 separation).
        2. Check if IP changed.
        3. If same: Return cached Geo details.
        4. If changed: Fetch details from FreeIPAPI -> Fallback ipapi.co -> Fallback ip-api.com
        """
        
        # Step 1: Detect IP using ipify
        ip_detector = IpifyProvider()
        ip_result = ip_detector.fetch_details(timeout=timeout, version=version)
        
        if not ip_result["success"]:
            return ip_result # Propagate error (e.g. no internet)

        detected_ip = ip_result["ip"]

        # Step 2: Compare with Cache
        # If we have a cached IP, and it matches the detected one, and we have valid details...
        if cached_ip and cached_details and detected_ip == cached_ip:
            # Check if cached details didn't have an error previously
            if not cached_details.get("error"):
                # logger.debug(f"SmartProvider ({version}): IP unchanged ({detected_ip}). Using cached Geo.")
                return {
                    "ip": detected_ip,
                    "country": cached_details.get("country"),
                    "isp": cached_details.get("isp"),
                    "success": True,
                    "error": None
                }
        
        # Step 3: Fetch Geo Data (IP changed or first run)
        logger.info(f"SmartProvider ({version}): New IP detected ({detected_ip}). Fetching Geo Data...")
        
        # List of Geo Providers in order of preference
        geo_providers = [
            FreeIpApiProvider(),
            IpApiCoProvider(),
            IpApiComProvider() # HTTP fallback
        ]
        
        last_error = "No providers available"
        
        for provider in geo_providers:
            # logger.debug(f"SmartProvider: Querying {provider.get_name()}...")
            res = provider.fetch_details(timeout=timeout, target_ip=detected_ip)
            
            if res["success"]:
                # Success!
                return res
            else:
                last_error = res["error"]
                logger.warning(f"SmartProvider: {provider.get_name()} failed ({last_error}). Trying fallback...")
                
        # If all failed, we still have the IP from ipify, but no Geo.
        return {
            "ip": detected_ip,
            "country": "??",
            "isp": "Unknown (Geo Lookup Failed)",
            "success": True,
            "error": f"Geo Failed: {last_error}" 
        }

# Registry - Contains all available providers for the GUI dropdown
PROVIDERS = {
    "smart": SmartProvider(),
    "ipwhois": IpWhoIsProvider(),
    "freeipapi": FreeIpApiProvider(),
    "ipapico": IpApiCoProvider(),
    "ipify": IpifyProvider(), # IP Only
    "ipapi": IpApiComProvider(), # Legacy / ip-api.com
    "custom": CustomProvider()
}

def get_provider(key):
    return PROVIDERS.get(key, PROVIDERS["smart"])

def get_provider_display_names():
    return {k: v.get_name() for k, v in PROVIDERS.items()}