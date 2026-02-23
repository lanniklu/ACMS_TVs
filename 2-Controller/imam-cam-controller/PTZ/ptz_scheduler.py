"""
Scheduler PTZ - Gère l'activation des présets selon les horaires de prière
Doit être appelé quotidiennement par le script principal
"""

from datetime import datetime, timedelta
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PTZScheduler:
    """Scheduler pour automatiser les changements de position PTZ"""

    def __init__(self, ptz_controller, mawaqit_parser, config):
        self.ptz = ptz_controller
        self.parser = mawaqit_parser
        self.config = config
        self.schedule_file = os.path.join(
            os.path.dirname(__file__), "ptz_schedule_today.json"
        )
        self.current_schedule = {}

    def update_daily_schedule(self):
        """
        Met à jour le planning quotidien
        Doit être appelé une fois par jour (à minuit par exemple)
        """
        logger.info("=" * 60)
        logger.info("📅 Mise à jour du planning PTZ quotidien")
        logger.info("=" * 60)

        # Récupère les horaires de prière
        prayers = self.parser.fetch_prayer_times()
        if not prayers:
            logger.error("✗ Impossible de récupérer les horaires")
            return False

        # Crée le planning du jour
        schedule = self._create_schedule(prayers)

        # Sauvegarde le planning
        try:
            with open(self.schedule_file, "w", encoding="utf-8") as f:
                json.dump(schedule, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ Planning sauvegardé: {self.schedule_file}")
        except Exception as e:
            logger.error(f"✗ Erreur sauvegarde: {e}")
            return False

        self.current_schedule = schedule
        self._log_schedule(schedule)
        return True

    def _create_schedule(self, prayers):
        """
        Crée le planning d'activation des présets
        
        Positions:
        - 1: Iqama (lors des 5 prières)
        - 2: Khotba Jumuaa (5 min avant Jumuaa)
        - 3: Conférence (manuel, non géré ici)
        """
        schedule = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "events": [],
        }

        # Prières régulières: position 2 lors de l'iqama
        for prayer_name in ["fajr", "dhuhr", "asr", "maghrib", "isha"]:
            if prayers.get(prayer_name):
                prayer_time_str = prayers[prayer_name]
                prayer_dt = datetime.strptime(prayer_time_str, "%H:%M")
                iqama_time = prayer_dt + timedelta(minutes=prayers.get("iqama_offset", 10))

                schedule["events"].append({
                    "type": "iqama",
                    "prayer": prayer_name,
                    "prayer_time": prayer_time_str,
                    "iqama_time": iqama_time.strftime("%H:%M"),
                    "position": 2,
                    "description": f"Salat {prayer_name.capitalize()}",
                })

        # Jumuaa(s): Gestion spécifique avec 2 phases
        # Phase 1: Khotba (5 min avant)
        # Phase 2: Position 3 (25 min après le début)
        # Gère 1 ou 2 Jumuaa
        jumuas = prayers.get("jumua")
        if jumuas:
            # Normalise en liste si nécessaire
            if not isinstance(jumuas, list):
                jumuas = [jumuas]
            
            for idx, jumua_time_str in enumerate(jumuas, 1):
                jumua_dt = datetime.strptime(jumua_time_str, "%H:%M")
                khotba_time = jumua_dt - timedelta(minutes=5)
                position3_time = jumua_dt + timedelta(minutes=25)

                # Phase 1: Khotba (position 1) - 5 min avant la Jumuaa
                schedule["events"].append({
                    "type": "jumua_khotba",
                    "prayer": f"jumua_{idx}",
                    "jumua_time": jumua_time_str,
                    "khotba_time": khotba_time.strftime("%H:%M"),
                    "position": 1,
                    "description": f"Khotba Jumuaa #{idx} (5 min avant {jumua_time_str})",
                })

                # Phase 2: Position 3 (vue large) - 25 min après le début de Jumuaa
                schedule["events"].append({
                    "type": "jumua_position3",
                    "prayer": f"jumua_{idx}",
                    "jumua_time": jumua_time_str,
                    "position3_time": position3_time.strftime("%H:%M"),
                    "position": 3,
                    "description": f"Jumuaa #{idx} - Vue large (25 min après {jumua_time_str})",
                })

        # Tri par heure
        schedule["events"].sort(key=lambda x: x.get("iqama_time") or x.get("khotba_time") or x.get("position3_time"))

        return schedule

    def _log_schedule(self, schedule):
        """Affiche le planning de manière lisible"""
        logger.info(f"\n📋 Planning du {schedule['date']}:")
        logger.info("-" * 60)
        
        for i, event in enumerate(schedule["events"], 1):
            if event["type"] == "iqama":
                logger.info(
                    f"{i}. {event['description']}"
                    f"\n   Prière: {event['prayer_time']} | "
                    f"Iqama: {event['iqama_time']} | "
                    f"Position: {event['position']}"
                )
            elif event["type"] == "jumua_khotba":
                logger.info(
                    f"{i}. {event['description']}"
                    f"\n   Jumuaa: {event['jumua_time']} | "
                    f"Khotba: {event['khotba_time']} | "
                    f"Position: {event['position']}"
                )

    def check_and_execute(self):
        """
        Vérifie si un événement PTZ doit être exécuté MAINTENANT
        À appeler régulièrement (toutes les minutes par exemple)
        """
        if not self.current_schedule:
            self.load_schedule()

        now = datetime.now()
        current_time = now.strftime("%H:%M")

        for event in self.current_schedule.get("events", []):
            # Détermine l'heure cible
            target_time = event.get("iqama_time") or event.get("khotba_time")

            # Vérifie si c'est le moment (avec 1 minute de tolérance)
            if target_time == current_time:
                logger.info(f"\n⏰ Activation de {event['description']}")
                result = self.ptz.goto_preset(event["position"])
                
                if result:
                    logger.info(f"✓ Preset {event['position']} activé")
                else:
                    logger.error(f"✗ Erreur activation preset {event['position']}")

    def load_schedule(self):
        """Charge le planning sauvegardé"""
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, "r", encoding="utf-8") as f:
                    self.current_schedule = json.load(f)
                logger.info("✓ Planning chargé depuis fichier")
            else:
                logger.warning("⚠ Aucun planning trouvé, première mise à jour nécessaire")
        except Exception as e:
            logger.error(f"✗ Erreur chargement planning: {e}")

    def get_next_event(self):
        """Retourne le prochain événement PTZ"""
        if not self.current_schedule:
            self.load_schedule()

        now = datetime.now()
        current_time = now.strftime("%H:%M")

        for event in self.current_schedule.get("events", []):
            target_time = event.get("iqama_time") or event.get("khotba_time")
            
            if target_time > current_time:
                return event

        return None
