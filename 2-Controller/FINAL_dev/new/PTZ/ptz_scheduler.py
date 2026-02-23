"""
PTZ Scheduler - Manages prayer-based camera positioning
Handles daily schedule creation and event execution
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

class PTZScheduler:
    """Manages PTZ scheduling based on prayer times"""
    
    def __init__(self, controller, parser, config: Dict):
        """
        Initialize scheduler
        controller: PTZController instance
        parser: MawaqitParser instance
        config: Configuration from ptz_config.py
        """
        self.controller = controller
        self.parser = parser
        self.config = config
        
        self.current_schedule = None
        self.last_update = None
        self._last_executed_time = None
        self._last_executed_position = None
        self.schedule_file = os.path.join(
            config.get("schedules_dir", "/tmp/"),
            f"ptz_schedule_{datetime.now().strftime('%Y%m%d')}.json"
        )
        
    def update_daily_schedule(self) -> bool:
        """
        Create/update daily schedule from prayer times
        Returns: True if successful
        """
        try:
            logging.info("[SCHEDULER] Updating daily schedule...")
            
            # Fetch latest prayer times
            prayer_times = self.parser.fetch_prayer_times()
            if not prayer_times:
                logging.error("[SCHEDULER] Failed to fetch prayer times")
                return False
            
            schedule = self._create_schedule(prayer_times)
            self.current_schedule = schedule
            self.last_update = datetime.now()
            
            # Save to file
            self._save_schedule(schedule)
            
            logging.info(f"[SCHEDULER] Schedule updated: {len(schedule.get('events', []))} events")
            return True
            
        except Exception as e:
            logging.error(f"[SCHEDULER] Error updating schedule: {e}")
            return False
    
    def _create_schedule(self, prayer_times: Dict) -> Dict:
        """
        Create daily schedule from prayer times
        Handles regular Salat and special Jumuaa handling
        """
        today = datetime.now().strftime("%Y-%m-%d")
        events = []
        
        # Regular prayers (not Friday)
        if datetime.now().weekday() != 4:  # Not Friday
            regular_prayers = {
                "fajr": ("Fajr", 2),      # Position 2 (Salat)
                "dhuhr": ("Dhuhr", 2),
                "asr": ("Asr", 2),
                "maghrib": ("Maghrib", 2),
                "isha": ("Isha", 2)
            }
            
            for prayer_key, (prayer_name, position) in regular_prayers.items():
                time_str = self._extract_time(prayer_times.get(prayer_key))
                if time_str:
                    iqama_time = self._add_minutes(time_str, self.config.get("iqama_offset", 10))
                    events.append({
                        "type": "iqama",
                        "prayer": prayer_key,
                        "prayer_name": prayer_name,
                        "iqama_time": iqama_time,
                        "position": position,
                        "description": f"{prayer_name} (position {position})"
                    })
        
        # Friday (Jumuaa) - Special 3-phase handling
        if datetime.now().weekday() == 4:  # Friday
            jumua_data = self._extract_time(prayer_times.get("jumua"))
            
            # Handle single or multiple Jumuaa times
            jumua_times = []
            if isinstance(jumua_data, list):
                jumua_times = jumua_data  # Double Jumuaa: ["12:30", "13:45"]
            elif jumua_data:
                jumua_times = [jumua_data]  # Single Jumuaa: "12:30"
            
            for jumua_time in jumua_times:
                # Phase 1: Position 5 (Conference) - 10 minutes BEFORE Jumuaa
                pre_jumua_time = self._add_minutes(jumua_time, -10)
                events.append({
                    "type": "jumua_pre",
                    "prayer": "jumua",
                    "prayer_name": "Jumuaa",
                    "jumua_time": jumua_time,
                    "position": 5,
                    "time": pre_jumua_time,
                    "description": f"Jumuaa Pre (position 5) at {jumua_time}"
                })
                
                # Phase 2: Position 1 (Khotba) - at Jumuaa time
                events.append({
                    "type": "jumua_khotba",
                    "prayer": "jumua",
                    "prayer_name": "Jumuaa",
                    "jumua_time": jumua_time,
                    "position": 1,
                    "time": jumua_time,
                    "description": f"Jumuaa Khotba (position 1) at {jumua_time}"
                })

                # Phase 3: Position 3 (Large) - 50 minutes AFTER Jumuaa
                large_view_time = self._add_minutes(jumua_time, 50)
                events.append({
                    "type": "jumua_position3",
                    "prayer": "jumua",
                    "prayer_name": "Jumuaa",
                    "jumua_time": jumua_time,
                    "position": 3,
                    "time": large_view_time,
                    "description": f"Jumuaa Large View (position 3) at +50min"
                })
        
        # Other Friday prayers (Asr, Maghrib, Isha)
        if datetime.now().weekday() == 4:
            other_prayers = {
                "asr": ("Asr", 2),
                "maghrib": ("Maghrib", 2),
                "isha": ("Isha", 2)
            }
            
            for prayer_key, (prayer_name, position) in other_prayers.items():
                time_str = self._extract_time(prayer_times.get(prayer_key))
                if time_str:
                    iqama_time = self._add_minutes(time_str, self.config.get("iqama_offset", 10))
                    events.append({
                        "type": "iqama",
                        "prayer": prayer_key,
                        "prayer_name": prayer_name,
                        "iqama_time": iqama_time,
                        "position": position,
                        "description": f"{prayer_name} (position {position})"
                    })
        
        # Sort by time
        events.sort(key=lambda e: e.get("time", e.get("iqama_time", "00:00")))
        
        return {
            "date": today,
            "events": events,
            "created_at": datetime.now().isoformat()
        }
    
    def check_and_execute(self):
        """
        Check schedule and execute positions if time matches
        Call this regularly in main loop
        """
        if not self.current_schedule:
            return
        
        try:
            now = datetime.now()
            chosen_event = self._get_current_event(now)
            if not chosen_event:
                return

            event_time = chosen_event.get("time", chosen_event.get("iqama_time"))
            position = chosen_event["position"]
            description = chosen_event["description"]

            if self._last_executed_time == event_time and self._last_executed_position == position:
                return

            logging.info(f"[SCHEDULER] Executing: {description}")
            self.controller.goto_preset(position)
            self._last_executed_time = event_time
            self._last_executed_position = position
                    
        except Exception as e:
            logging.error(f"[SCHEDULER] Error checking schedule: {e}")
    
    def _add_minutes(self, time_str: str, minutes: int) -> str:
        """Add/subtract minutes from HH:MM format"""
        try:
            hours, mins = map(int, time_str.split(":"))
            dt = datetime.now().replace(hour=hours, minute=mins, second=0, microsecond=0)
            dt += timedelta(minutes=minutes)
            return dt.strftime("%H:%M")
        except:
            return time_str

    def _extract_time(self, value):
        """
        Normalize prayer time values coming from the parser.
        Accepts strings, lists, or dicts like {"time": "HH:MM"}.
        """
        if isinstance(value, dict):
            return value.get("time")
        return value

    def _event_time_to_dt(self, event, today):
        time_str = event.get("time", event.get("iqama_time"))
        if not time_str:
            return None
        try:
            return datetime.strptime(f"{today} {time_str}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def _get_current_event(self, now):
        """Return the latest event whose time is <= now."""
        today = now.strftime("%Y-%m-%d")
        events = self.current_schedule.get("events", [])
        latest = None
        latest_dt = None

        for event in events:
            event_dt = self._event_time_to_dt(event, today)
            if not event_dt:
                continue
            if event_dt <= now and (latest_dt is None or event_dt > latest_dt):
                latest = event
                latest_dt = event_dt

        return latest
    
    def _save_schedule(self, schedule: Dict):
        """Save schedule to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.schedule_file), exist_ok=True)
            with open(self.schedule_file, 'w') as f:
                json.dump(schedule, f, indent=2)
            logging.debug(f"[SCHEDULER] Schedule saved: {self.schedule_file}")
        except Exception as e:
            logging.warning(f"[SCHEDULER] Could not save schedule: {e}")
