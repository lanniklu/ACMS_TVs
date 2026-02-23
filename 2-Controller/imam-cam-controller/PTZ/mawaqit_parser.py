"""
Parser pour récupérer les horaires de prière depuis Mawaqit
Extrait les données de la page HTML de la mosquée
"""

import requests
from datetime import datetime
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MawaqitParser:
    """Parse les horaires de prière depuis Mawaqit"""

    MOSQUE_URL = "https://mawaqit.net/fr/mosquee-ennour-sartrouville"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ACMS-Mawaqit-Parser",
        })

    def fetch_prayer_times(self):
        """
        Récupère les horaires de prière du jour
        
        Returns:
            dict: Horaires de prière {'fajr': '06:49', 'dhuhr': '13:10', ...}
        """
        try:
            logger.info("Récupération des horaires de prière...")
            response = self.session.get(self.MOSQUE_URL, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                prayers = self._extract_prayer_times(response.text)
                if prayers:
                    logger.info(f"✓ Horaires récupérés: {prayers}")
                    return prayers
                else:
                    logger.error("✗ Impossible d'extraire les horaires")
                    return None
            else:
                logger.error(f"✗ Erreur HTTP: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"✗ Erreur récupération: {e}")
            return None

    def _extract_prayer_times(self, html):
        """
        Extrait les horaires de prière du HTML
        Gère les cas simples ET doubles Jumuaa
        """
        try:
            # Recherche la section avec les horaires
            match = re.search(r'"times":\s*\[(.*?)\]', html)
            if match:
                times_str = f"[{match.group(1)}]"
                # Parse les horaires dans l'ordre: fajr, dhuhr, asr, maghrib, isha
                times = [t.strip().strip('"') for t in times_str.split(',')]
                
                prayers = {
                    "fajr": times[0] if len(times) > 0 else None,
                    "dhuhr": times[1] if len(times) > 1 else None,
                    "asr": times[2] if len(times) > 2 else None,
                    "maghrib": times[3] if len(times) > 3 else None,
                    "isha": times[4] if len(times) > 4 else None,
                }
                
                # Recherche Jumuaa(s) - peut y avoir 1 ou 2
                # Format: "jumua":"12:30" ou "jumua":["12:30","13:45"]
                jumua_single = re.search(r'"jumua":\s*"([\d:]+)"', html)
                jumua_array = re.search(r'"jumua":\s*\[([^\]]+)\]', html)
                
                jumuas = []
                if jumua_array:
                    # Cas avec array de Jumuaa
                    jumua_str = jumua_array.group(1)
                    jumuas = [t.strip().strip('"') for t in jumua_str.split(',')]
                elif jumua_single:
                    # Cas avec un seul Jumuaa
                    jumuas = [jumua_single.group(1)]
                
                if jumuas:
                    prayers["jumua"] = jumuas
                    logger.info(f"Jumuaa détecté(s): {jumuas}")
                
                return prayers
            
            return None
        except Exception as e:
            logger.error(f"Erreur parsing: {e}")
            return None

    def get_next_prayer_event(self, prayers):
        """
        Determine le prochain événement de prière à gérer
        
        Returns:
            dict: {'type': 'iqama'|'jumua', 'prayer': 'fajr'|'jumua'|..., 'time': datetime}
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        events = []
        
        # Vérifie chaque prière
        for prayer_name in ["fajr", "dhuhr", "asr", "maghrib", "isha"]:
            if prayers.get(prayer_name):
                prayer_time = datetime.strptime(prayers[prayer_name], "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
                # Iqama = 10 min après la prière
                iqama_time = prayer_time + timedelta(minutes=10)
                
                if iqama_time > now:
                    events.append({
                        "type": "iqama",
                        "prayer": prayer_name,
                        "time": iqama_time,
                        "prayer_time": prayer_time,
                    })
        
        # Vérifie Jumuaa
        if prayers.get("jumua"):
            jumua_time = datetime.strptime(prayers["jumua"], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
            # Khotba = 5 min avant Jumuaa
            khotba_time = jumua_time - timedelta(minutes=5)
            
            if khotba_time > now:
                events.append({
                    "type": "jumua_khotba",
                    "prayer": "jumua",
                    "time": khotba_time,
                    "jumua_time": jumua_time,
                })
        
        # Retourne le prochain événement
        if events:
            next_event = min(events, key=lambda x: x["time"])
            return next_event
        
        return None
