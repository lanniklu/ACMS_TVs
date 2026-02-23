"""
Package PTZ - Système de contrôle de caméra PTZ pour Mawaqit

Modules:
- ptz_config: Configuration PTZ
- ptz_controller: Contrôleur ISAPI Hikvision
- mawaqit_parser: Parser des horaires Mawaqit
- ptz_scheduler: Scheduler d'automatisation
- mawaqit_ptz_manager: Manager d'intégration principal
"""

__version__ = "1.0.0"
__author__ = "ACMS - Mosquée Ennour"
__description__ = "Système d'automatisation PTZ pour caméra Hikvision"

from .ptz_config import PTZ_CONFIG, PRAYER_TIMES
from .ptz_controller import PTZController
from .mawaqit_parser import MawaqitParser
from .ptz_scheduler import PTZScheduler
from .mawaqit_ptz_manager import MawaqitPTZManager

__all__ = [
    "PTZ_CONFIG",
    "PRAYER_TIMES",
    "PTZController",
    "MawaqitParser",
    "PTZScheduler",
    "MawaqitPTZManager",
]
