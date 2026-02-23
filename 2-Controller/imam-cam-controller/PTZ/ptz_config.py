# Configuration PTZ pour la caméra CAM IMAM
# Hikvision DS-2DE2A404IW-DE3 @ 10.1.5.20

PTZ_CONFIG = {
    "camera": {
        "ip": "10.1.5.20",
        "port": 80,
        "username": "admin",
        "password": "Frsbd2013",
    },
    "positions": {
        1: {
            "name": "Position Khotba",
            "description": "Khotba du vendredi (5 min avant Jumuaa)",
            "activation": "jumua_minus_5min",  # S'active 5 min avant Jumuaa
        },
        2: {
            "name": "Position Salat",
            "description": "Activation lors de l'iqama et durant la prière",
            "activation": "iqama",  # S'active à l'iqama
        },
        3: {
            "name": "Position Conférence",
            "description": "Position manuelle pour les conférences",
            "activation": "manual",  # Activée manuellement
        },
    },
    "default_position": 1,  # Position par défaut
}

# Horaires de prière (mis à jour quotidiennement)
PRAYER_TIMES = {
    "fajr": None,      # Fajr (Subh)
    "dhuhr": None,     # Dhuhr (Midi)
    "asr": None,       # Asr (Après-midi)
    "maghrib": None,   # Maghrib (Coucher)
    "isha": None,      # Isha (Soir)
    "jumua": None,     # Jumuaa (Vendredi)
    "iqama_offset": 10,  # Délai d'iqama en minutes (par défaut +10min)
}
