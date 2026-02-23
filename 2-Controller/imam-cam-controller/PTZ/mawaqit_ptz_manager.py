"""
Intégration PTZ dans le script Mawaqit
À ajouter dans mawaqit_stream_manager.py
"""

# Imports à ajouter
import sys
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# Ajouter le chemin du PTZ
ptz_dir = os.path.join(os.path.dirname(__file__), 'imam-cam-controller', 'PTZ')
sys.path.insert(0, ptz_dir)

from ptz_config import PTZ_CONFIG
from ptz_controller import PTZController
from mawaqit_parser import MawaqitParser
from ptz_scheduler import PTZScheduler


class MawaqitPTZManager:
    """Gestionnaire d'intégration Mawaqit <-> PTZ"""

    def __init__(self):
        self.ptz_controller = None
        self.mawaqit_parser = None
        self.ptz_scheduler = None
        self.scheduler = BackgroundScheduler()
        self._initialize_ptz()

    def _initialize_ptz(self):
        """Initialise les composants PTZ"""
        try:
            self.ptz_controller = PTZController(PTZ_CONFIG)
            self.mawaqit_parser = MawaqitParser()
            self.ptz_scheduler = PTZScheduler(
                self.ptz_controller, 
                self.mawaqit_parser, 
                PTZ_CONFIG
            )
            print("[PTZ] ✓ Système PTZ initialisé")
        except Exception as e:
            print(f"[PTZ] ✗ Erreur initialisation: {e}")

    def start_ptz_scheduler(self):
        """
        Démarre le scheduler PTZ
        - Mise à jour du planning à minuit
        - Vérification toutes les minutes
        """
        if not self.scheduler.running:
            # Mise à jour quotidienne à minuit
            self.scheduler.add_job(
                self.ptz_scheduler.update_daily_schedule,
                'cron',
                hour=0,
                minute=0,
                id='ptz_daily_update',
                name='PTZ Daily Schedule Update'
            )

            # Vérification chaque minute
            self.scheduler.add_job(
                self.ptz_scheduler.check_and_execute,
                'interval',
                minutes=1,
                id='ptz_minute_check',
                name='PTZ Minute Check'
            )

            self.scheduler.start()
            print("[PTZ] ✓ Scheduler PTZ démarré")
            
            # Mise à jour initiale
            self.ptz_scheduler.update_daily_schedule()

    def stop_ptz_scheduler(self):
        """Arrête le scheduler PTZ"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print("[PTZ] ✓ Scheduler PTZ arrêté")

    def get_ptz_status(self):
        """Retourne l'état du système PTZ"""
        return {
            "ptz_initialized": self.ptz_controller is not None,
            "scheduler_running": self.scheduler.running,
            "next_event": self.ptz_scheduler.get_next_event() if self.ptz_scheduler else None,
        }

    def manual_preset(self, preset_id):
        """Active manuellement un preset"""
        if self.ptz_controller:
            return self.ptz_controller.goto_preset(preset_id)
        return False


# Exemple d'utilisation dans mawaqit_stream_manager.py:
"""
def main():
    # ... code existant ...
    
    # Initialiser le gestionnaire PTZ
    ptz_manager = MawaqitPTZManager()
    ptz_manager.start_ptz_scheduler()
    
    try:
        # ... boucle principale ...
        pass
    finally:
        ptz_manager.stop_ptz_scheduler()
"""
