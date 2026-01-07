import requests
import logging

logger = logging.getLogger("VPNWatchdog")

class IPProvider:
    """Base class for IP Information Providers."""
    def get_name(self):
        return "Unknown"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None):
        """
        Fetches details.
        custom_url: If provided, overrides internal URL logic (used for v4/v6 specific checks).
        target_ip: Optional string. If provided, fetches details for this IP (server-side lookup).
        """
        raise NotImplementedError

class IpWhoIsProvider(IPProvider):
    def get_name(self):
        return "ipwho.is (Free, No SSL)"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None):
        # ipwho.is supports /ip?output=json or just /?output=json
        # Note: ipwho.is does not explicitly support forcing v6 via a separate free subdomain easily,
        # but if custom_url is passed (e.g. from a user config), we use it.
        
        if custom_url:
            url = custom_url
        else:
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

class IpApiProvider(IPProvider):
    def get_name(self):
        return "ip-api.com (Free, No SSL)"

    def fetch_details(self, timeout=5, custom_url=None, target_ip=None):
        # ip-api.com free endpoint: /json/{ip} or /json/
        if custom_url:
            url = custom_url
        else:
            base = "http://ip-api.com/json/"
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
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

class CustomProvider(IPProvider):
    def get_name(self):
        return "Custom API (Configurable)"

    def fetch_details(self, timeout=5, config=None, custom_url=None, target_ip=None):
        # For custom provider, 'config' dict is passed which contains keys.
        # 'custom_url' argument overrides the url in config if passed (used for v6).
        
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
                
                # Simple extraction
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

# Registry
PROVIDERS = {
    "ipwhois": IpWhoIsProvider(),
    "ipapi": IpApiProvider(),
    "custom": CustomProvider()
}

def get_provider(key):
    return PROVIDERS.get(key, PROVIDERS["ipwhois"])

def get_provider_display_names():
    return {k: v.get_name() for k, v in PROVIDERS.items()}