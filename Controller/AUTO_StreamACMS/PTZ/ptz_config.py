"""
PTZ Configuration for ACMS IMAM Camera
Camera: DS-2DE2A404IW-DE3
IP: 10.1.5.20
"""

PTZ_CONFIG = {
    # Camera connection
    "camera_ip": "10.1.5.20",
    "camera_port": 80,
    "camera_user": "admin",
    "camera_password": "Frsbd2013",  # Will be configured at runtime
    
    # Preset positions
    "positions": {
        1: {"name": "Khotba", "description": "Imam podium/Sermon"},
        2: {"name": "Salat", "description": "Prayer"},
        3: {"name": "LARGE", "description": "Large"},
        5: {"name": "Coference", "description": "Conférence"}
    },
    
    # Default position
    "default_position": 2,
    
    # Paths (for Linux RPi)
    "schedules_dir": "/home/acms_tech/AUTO_StreamACMS/schedules/",
    "logs_dir": "/home/acms_tech/AUTO_StreamACMS/logs/",
    
    # Prayer timing
    "iqama_offset": 10,               # Minutes after Adhan before Onvif activates (all prayers, all year)
    "ramadan_maghrib_offset": 2,        # Minutes after Adhan before Onvif activates (Maghrib only, Ramadan only)
    "ramadan_maghrib_duration": 8,      # Duration (min) of Onvif during Maghrib Ramadan (shorter salat)
    "ramadan_maghrib_video_delay": 0,   # Delay (min) before post-prayer video for Maghrib Ramadan (immediate)
    
    # Mawaqit API
    "mawaqit_mosque_id": "12345",  # Configure with actual mosque ID
    "mawaqit_api_url": "https://www.mawaqit.net/api/getTiming",
}

# Prayer schedule (will be populated from Mawaqit API)
PRAYER_TIMES = {
    "fajr": "06:00",
    "dhuhr": "12:00",
    "asr": "15:30",
    "maghrib": "18:00",
    "isha": "19:30",
    "jumua": "12:30"  # Can also be a list for double Jumuaa: ["12:30", "13:45"]
}

# Timing parameters
TIMINGS = {
    "check_interval": 5,        # seconds between checks
    "anti_flap_time": 10,       # minimum time before position change
    "network_timeout": 5,       # HTTP timeout to camera
}
