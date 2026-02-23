"""
PTZ Controller for Hikvision ISAPI
Handles preset positioning and camera control
"""

import requests
from requests.auth import HTTPDigestAuth
import logging
from typing import Optional, Dict

class PTZController:
    """Controls PTZ camera via ISAPI protocol"""
    
    def __init__(self, config: Dict):
        """
        Initialize PTZ controller
        config: Configuration dictionary from ptz_config.py
        """
        self.config = config
        self.camera_ip = config.get("camera_ip", "10.1.5.20")
        self.camera_port = config.get("camera_port", 80)
        self.camera_user = config.get("camera_user", "admin")
        self.camera_password = config.get("camera_password", "")
        
        self.base_url = f"http://{self.camera_ip}:{self.camera_port}"
        self.timeout = config.get("network_timeout", 5)
        
    def goto_preset(self, preset_id: int) -> bool:
        """
        Move camera to a preset position
        preset_id: Position number (1, 2, 3, etc.)
        Returns: True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/ISAPI/PTZCtrl/channels/1/presets/{preset_id}/goto"
            
            response = self._request("put", url)
            
            if response.status_code == 200:
                position_name = self.config["positions"][preset_id]["name"]
                logging.info(f"[PTZ] Position {preset_id} ({position_name}) - OK")
                return True
            else:
                logging.error(f"[PTZ] HTTP {response.status_code}: {response.text}")
                return False
                
        except requests.Timeout:
            logging.error(f"[PTZ] Timeout connecting to camera")
            return False
        except Exception as e:
            logging.error(f"[PTZ] Error: {e}")
            return False
    
    def get_device_info(self) -> Optional[Dict]:
        """
        Get camera device information (for connectivity check)
        Returns: Device info dict or None if unavailable
        """
        try:
            url = f"{self.base_url}/ISAPI/System/deviceInfo"
            
            response = self._request("get", url)
            
            if response.status_code == 200:
                logging.debug(f"[PTZ] Camera connected: {response.text[:100]}")
                return {"status": "connected"}
            else:
                logging.error(f"[PTZ] Cannot get device info: HTTP {response.status_code}")
                return None
                
        except requests.Timeout:
            logging.error(f"[PTZ] Camera timeout")
            return None
        except Exception as e:
            logging.error(f"[PTZ] Connection error: {e}")
            return None
    
    def get_current_time(self) -> Optional[str]:
        """
        Get camera current time
        Returns: Time string "HH:MM:SS" or None
        """
        try:
            url = f"{self.base_url}/ISAPI/System/time"
            
            response = self._request("get", url)
            
            if response.status_code == 200:
                # Parse XML response to extract time
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                time_elem = root.find(".//localTime")
                if time_elem is not None:
                    return time_elem.text
                return None
            else:
                return None
                
        except Exception as e:
            logging.debug(f"[PTZ] Error getting time: {e}")
            return None

    def _request(self, method: str, url: str):
        """
        Make an HTTP request to the camera with basic auth and fallback to digest.
        """
        auth_basic = (self.camera_user, self.camera_password) if self.camera_password else None
        response = requests.request(method, url, auth=auth_basic, timeout=self.timeout)

        if response.status_code == 401 and self.camera_password:
            auth_digest = HTTPDigestAuth(self.camera_user, self.camera_password)
            response = requests.request(method, url, auth=auth_digest, timeout=self.timeout)

        return response
