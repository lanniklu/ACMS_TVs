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
        Create/update daily schedule from prayer times.
        If internet is unavailable, try loading today's schedule from file.
        Returns: True if successful
        """
        try:
            logging.info("[SCHEDULER] Updating daily schedule...")
            today = datetime.now().strftime("%Y-%m-%d")

            # Try to load today's schedule from file first (fast path / offline)
            existing = self._load_schedule_if_today(today)
            if existing:
                self.current_schedule = existing
                self.last_update = datetime.now()
                logging.info(f"[SCHEDULER] Loaded schedule from file ({today}, {len(existing.get('events', []))} events)")
                # Still try to refresh from internet in background (don't block)
                prayer_times = self.parser.fetch_prayer_times()
                if prayer_times:
                    schedule = self._create_schedule(prayer_times)
                    self.current_schedule = schedule
                    self.last_update = datetime.now()
                    self._save_schedule(schedule)
                    logging.info(f"[SCHEDULER] Schedule refreshed from internet ({len(schedule.get('events', []))} events)")
                else:
                    logging.info("[SCHEDULER] Internet unavailable - using cached schedule")
                return True

            # No file for today - must fetch from internet
            prayer_times = self.parser.fetch_prayer_times()
            if not prayer_times:
                logging.error("[SCHEDULER] Failed to fetch prayer times and no cache available")
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

    def _load_schedule_if_today(self, today: str) -> dict | None:
        """Load schedule from file only if it matches today's date. Returns None otherwise."""
        try:
            schedule_file = os.path.join(
                self.config.get("schedules_dir", "/tmp/"),
                f"ptz_schedule_{today.replace('-', '')}.json"
            )
            if not os.path.exists(schedule_file):
                return None
            with open(schedule_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validate date
            file_date = data.get("date")
            if file_date != today:
                logging.warning(f"[SCHEDULER] Schedule file date mismatch: {file_date} != {today}")
                return None
            events = data.get("events", [])
            if not events:
                logging.warning("[SCHEDULER] Schedule file has no events, ignoring")
                return None
            return data
        except Exception as e:
            logging.warning(f"[SCHEDULER] Could not load schedule file: {e}")
            return None
    
    def _create_schedule(self, prayer_times: Dict) -> Dict:
        """
        Create daily schedule from prayer times
        Handles regular Salat, Jumuaa, and Ramadan (Tahajuud, Tarawih)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        events = []
        
        # Check if Ramadan
        is_ramadan = prayer_times.get("ramadan", False)
        hijra_date = prayer_times.get("hijra_date", "")
        if is_ramadan:
            logging.info(f"[SCHEDULER] Ramadan schedule: {hijra_date}")
        
        # Regular prayers (not Friday)
        if datetime.now().weekday() != 4:  # Not Friday
            regular_prayers = {
                "fajr": ("Fajr", 2),      # Position 2
                "dhuhr": ("Dhuhr", 2),
                "asr": ("Asr", 2),
                "maghrib": ("Maghrib", 2),
                "isha": ("Isha", 2)
            }
            
            for prayer_key, (prayer_name, position) in regular_prayers.items():
                # Skip Isha during Ramadan (it's covered by Tarawih)
                if is_ramadan and prayer_key == "isha":
                    continue
                    
                time_str = self._extract_time(prayer_times.get(prayer_key))
                if time_str:
                    # Maghrib during Ramadan: 2 min after Adhan ; all other cases: from Mawaqit iqamaCalendar
                    if is_ramadan and prayer_key == "maghrib":
                        offset = self.config.get("ramadan_maghrib_offset", 2)
                    else:
                        _prayer = prayer_times.get(prayer_key)
                        _raw_offset = _prayer.get("iqama_offset", 10) if isinstance(_prayer, dict) else 10
                        offset = _raw_offset if _raw_offset > 0 else 2  # iqama=0: add 2min for adhan duration
                    iqama_time = self._add_minutes(time_str, offset)
                    
                    # RAMADAN: Add Tahajuud event for Fajr (1 hour before)
                    if is_ramadan and prayer_key == "fajr":
                        tahajuud_start = self._add_minutes(time_str, -60)  # Fajr - 60 min
                        tahajuud_end = self._add_minutes(time_str, -20)    # Fajr - 20 min (40min window)
                        events.append({
                            "type": "tahajuud",
                            "prayer": "tahajuud",
                            "prayer_name": "Tahajuud",
                            "fajr_time": time_str,
                            "onvif_start": tahajuud_start,
                            "onvif_end": tahajuud_end,
                            "time": tahajuud_start,
                            "position": 2,
                            "description": f"Tahajuud - Night prayer ({tahajuud_start} -> {tahajuud_end})"
                        })
                    
                    # Prayer duration and post-prayer video delay
                    if is_ramadan and prayer_key == "maghrib":
                        onvif_duration = self.config.get("ramadan_maghrib_duration", 7)
                        post_video_delay = self.config.get("ramadan_maghrib_video_delay", 0)
                    else:
                        _prayer = prayer_times.get(prayer_key)
                        onvif_duration = _prayer.get("dua_duration", 10) if isinstance(_prayer, dict) else 10
                        post_video_delay = 1  # 1 min default delay

                    events.append({
                        "type": "iqama",
                        "prayer": prayer_key,
                        "prayer_name": prayer_name,
                        "iqama_time": iqama_time,
                        "onvif_duration": onvif_duration,
                        "post_prayer_video_delay": post_video_delay,
                        "onvif_end": self._add_minutes(iqama_time, onvif_duration),
                        "time": iqama_time,
                        "position": position,
                        "description": f"{prayer_name} ({iqama_time} -> {self._add_minutes(iqama_time, onvif_duration)})"
                    })
        
        # Friday (Jumuaa) - Single block from first Jumuaa T1-10min to last Jumuaa T2+50min
        if datetime.now().weekday() == 4:  # Friday
            jumua_data = self._extract_time(prayer_times.get("jumua"))

            # Handle single or multiple Jumuaa times
            jumua_times = []
            if isinstance(jumua_data, list):
                jumua_times = sorted(jumua_data)  # Double Jumuaa: ["12:30", "13:45"]
            elif jumua_data:
                jumua_times = [jumua_data]  # Single Jumuaa: "12:30"

            if jumua_times:
                first_jumua = jumua_times[0]
                last_jumua = jumua_times[-1]
                block_start = self._add_minutes(first_jumua, -10)  # T1 - 10 min
                block_end = self._add_minutes(last_jumua, 60)       # T2 + 60 min
                events.append({
                    "type": "jumuaa_block",
                    "prayer": "jumua",
                    "prayer_name": "Jumuaa",
                    "jumua_times": jumua_times,
                    "start_time": block_start,
                    "end_time": block_end,
                    "time": block_start,
                    "position": 7,
                    "description": f"Jumuaa pos7 ({block_start} -> {block_end})"
                })
        
        # Other Friday prayers (Asr, Maghrib, Isha)
        if datetime.now().weekday() == 4:
            other_prayers = {
                "fajr": ("Fajr", 2),
                "asr": ("Asr", 2),
                "maghrib": ("Maghrib", 2),
                "isha": ("Isha", 2)
            }
            
            for prayer_key, (prayer_name, position) in other_prayers.items():
                time_str = self._extract_time(prayer_times.get(prayer_key))
                if time_str:
                    # Maghrib during Ramadan: 2 min after Adhan ; all other cases: 10 min
                    if is_ramadan and prayer_key == "maghrib":
                        offset = self.config.get("ramadan_maghrib_offset", 2)
                        onvif_duration = self.config.get("ramadan_maghrib_duration", 7)
                        post_video_delay = self.config.get("ramadan_maghrib_video_delay", 0)
                    else:
                        _prayer = prayer_times.get(prayer_key)
                        _raw_offset = _prayer.get("iqama_offset", 10) if isinstance(_prayer, dict) else 10
                        offset = _raw_offset if _raw_offset > 0 else 2  # iqama=0: add 2min for adhan duration
                        onvif_duration = _prayer.get("dua_duration", 10) if isinstance(_prayer, dict) else 10
                        post_video_delay = 1
                    iqama_time = self._add_minutes(time_str, offset)
                    events.append({
                        "type": "iqama",
                        "prayer": prayer_key,
                        "prayer_name": prayer_name,
                        "iqama_time": iqama_time,
                        "onvif_duration": onvif_duration,
                        "post_prayer_video_delay": post_video_delay,
                        "position": position,
                        "description": f"{prayer_name} (position {position})"
                    })
        
        # RAMADAN: Add Tarawih event (Isha time + 2h30) - every night including Fridays
        if is_ramadan:
            isha_time = self._extract_time(prayer_times.get("isha"))
            if isha_time:
                _isha = prayer_times.get("isha")
                _isha_raw_offset = _isha.get("iqama_offset", 10) if isinstance(_isha, dict) else 10
                _isha_offset = _isha_raw_offset if _isha_raw_offset > 0 else 2  # iqama=0: add 2min for adhan duration
                iqama_isha = self._add_minutes(isha_time, _isha_offset)
                tarawih_end = self._add_minutes(iqama_isha, 150)  # Iqama Isha + 150 min
                events.append({
                    "type": "tarawih",
                    "prayer": "tarawih",
                    "prayer_name": "Tarawih",
                    "isha_time": isha_time,
                    "onvif_start": iqama_isha,
                    "onvif_end": tarawih_end,
                    "time": iqama_isha,
                    "position": 3,
                    "description": f"Tarawih - Evening prayer ({iqama_isha} -> {tarawih_end})"
                })
        
        # Sort by time
        events.sort(key=lambda e: e.get("time", e.get("iqama_time", "00:00")))
        
        return {
            "date": today,
            "events": events,
            "created_at": datetime.now().isoformat(),
            "is_ramadan": is_ramadan,
            "hijra_date": hijra_date
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
    
    def is_ramadan(self) -> bool:
        """Check if current schedule is in Ramadan"""
        return self.current_schedule.get("is_ramadan", False) if self.current_schedule else False
    
    def load_schedule(self):
        """Load schedule from JSON file"""
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, "r", encoding="utf-8") as f:
                    self.current_schedule = json.load(f)
                logger.info("Schedule loaded from file")
                if self.is_ramadan():
                    logger.info(f"Ramadan: {self.current_schedule.get('hijra_date')}")
            else:
                logger.warning("No schedule found, first update required")
        except Exception as e:
            logger.error(f"Erreur chargement planning: {e}")

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
