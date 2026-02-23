"""
Contrôleur PTZ pour caméra Hikvision
Gère les présets PTZ selon les horaires de prière de Mawaqit
"""

import requests
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PTZController:
    """Contrôleur pour caméra PTZ Hikvision via API ISAPI"""

    def __init__(self, config):
        self.config = config
        self.base_url = f"http://{config['camera']['ip']}/ISAPI"
        self.session = self._create_session()

    def _create_session(self):
        """Crée une session HTTP avec authentification"""
        session = requests.Session()
        session.auth = (
            self.config["camera"]["username"],
            self.config["camera"]["password"],
        )
        session.headers.update({
            "Content-Type": "application/xml",
            "User-Agent": "ACMS-PTZ-Controller",
        })
        return session

    def goto_preset(self, preset_id):
        """
        Déplace la caméra vers un preset spécifique
        
        Args:
            preset_id (int): ID du preset (1-255)
            
        Returns:
            bool: True si succès, False sinon
        """
        url = f"{self.base_url}/PTZCtrl/channels/1/presets/{preset_id}/goto"
        
        try:
            response = self.session.put(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✓ Caméra positionnée au preset {preset_id}")
                return True
            else:
                logger.error(f"✗ Erreur preset {preset_id}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"✗ Erreur connexion: {e}")
            return False

    def get_device_info(self):
        """Récupère les infos de la caméra"""
        url = f"{self.base_url}/System/deviceInfo"
        try:
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Erreur récupération infos: {e}")
            return None

    def get_current_time(self):
        """Récupère l'heure actuelle de la caméra"""
        url = f"{self.base_url}/System/time"
        try:
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Erreur récupération heure: {e}")
            return None
