"""
Mawaqit Parser - Retrieves prayer times from Mawaqit website
Handles single and double Jumuaa (Friday) detection
"""

import requests
import logging
import re
import json

class MawaqitParser:
    """Parse prayer times from Mawaqit website"""
    
    def __init__(self, mosque_url="https://mawaqit.net/fr/mosquee-ennour-sartrouville"):
        """
        Initialize parser
        mosque_url: Direct URL to the mosque on Mawaqit website
        """
        self.mosque_url = mosque_url
        self.prayer_times = {}
        self.location_name = "Mosquée En-Nour - Sartrouville"
        
    def fetch_prayer_times(self):
        """
        Fetch prayer times from Mawaqit website only (no API fallback)
        Returns dict with prayer times or None on error
        """
        if not self.mosque_url:
            logging.error("[MAWAQIT] No mosque URL provided")
            return None

        return self._fetch_from_website()

    def _extract_conf_data(self, html_text):
        """
        Extract confData JSON object from the page script.
        Returns dict or None.
        """
        marker = "confData = {"
        start = html_text.find(marker)
        if start == -1:
            return None

        i = start + len(marker) - 1  # position at '{'
        depth = 0
        for idx in range(i, len(html_text)):
            ch = html_text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj_text = html_text[i:idx + 1]
                    try:
                        return json.loads(obj_text)
                    except Exception:
                        return None
        return None

    def _fetch_from_website(self):
        """
        Fetch prayer times by scraping Mawaqit website (HTML text parsing)
        Returns dict with prayer times or None on error
        """
        try:
            logging.info(f"[MAWAQIT] Scraping prayer times from: {self.mosque_url}")
            
            # Fetch the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36'
            }
            response = requests.get(self.mosque_url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            html_text = response.text
            
            # Extract mosque name from title or h1
            name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_text)
            if name_match:
                self.location_name = name_match.group(1).strip()
            
            prayer_times = {}

            # Try to extract embedded confData JSON first
            conf_data = self._extract_conf_data(html_text)
            if conf_data:
                times_list = conf_data.get("times") or []
                if len(times_list) >= 5:
                    prayer_times["fajr"] = {"time": times_list[0], "iqama_offset": 10}
                    prayer_times["dhuhr"] = {"time": times_list[1], "iqama_offset": 10}
                    prayer_times["asr"] = {"time": times_list[2], "iqama_offset": 10}
                    prayer_times["maghrib"] = {"time": times_list[3], "iqama_offset": 10}
                    prayer_times["isha"] = {"time": times_list[4], "iqama_offset": 10}

                jumua_times = []
                for key in ["jumua", "jumua2", "jumua3"]:
                    value = conf_data.get(key)
                    if isinstance(value, str) and re.match(r"^\d{2}:\d{2}$", value):
                        jumua_times.append(value)

                if jumua_times:
                    prayer_times["jumua"] = jumua_times[0] if len(jumua_times) == 1 else jumua_times

            # Fallback: extract JSON-like data by regex
            if not prayer_times:
                times_match = re.search(r'"times"\s*:\s*\[(.*?)\]', html_text, re.DOTALL)
                if times_match:
                    raw_times = "[" + times_match.group(1) + "]"
                    try:
                        times_list = json.loads(raw_times)
                    except Exception:
                        times_list = []

                    if len(times_list) >= 5:
                        prayer_times["fajr"] = {"time": times_list[0], "iqama_offset": 10}
                        prayer_times["dhuhr"] = {"time": times_list[1], "iqama_offset": 10}
                        prayer_times["asr"] = {"time": times_list[2], "iqama_offset": 10}
                        prayer_times["maghrib"] = {"time": times_list[3], "iqama_offset": 10}
                        prayer_times["isha"] = {"time": times_list[4], "iqama_offset": 10}

                    jumua_times = []
                    for key in ["jumua", "jumua2", "jumua3"]:
                        m = re.search(rf'"{key}"\s*:\s*"(\\d{{2}}:\\d{{2}})"', html_text)
                        if m:
                            jumua_times.append(m.group(1))

                    if jumua_times:
                        prayer_times["jumua"] = jumua_times[0] if len(jumua_times) == 1 else jumua_times

            # Fallback: legacy HTML text parsing
            if not prayer_times:
                pattern = r'(Fajr|Dhuhr|Asr|Maghrib|Isha|Jumua)\s+([0-9]{2}:[0-9]{2})(?:\+(\d+))?'
                matches = re.findall(pattern, html_text, re.IGNORECASE)

                if not matches:
                    logging.error(f"[MAWAQIT] No prayer times found in HTML from {self.mosque_url}")
                    logging.debug(f"[MAWAQIT] HTML snippet: {html_text[:500]}")
                    return None

                jumua_times = []
                for prayer_name, time_str, offset in matches:
                    prayer_key = prayer_name.lower()
                    if prayer_key == "jumua":
                        jumua_times.append(time_str)
                    else:
                        prayer_times[prayer_key] = {
                            "time": time_str,
                            "iqama_offset": int(offset) if offset else 10
                        }

                if jumua_times:
                    prayer_times["jumua"] = jumua_times[0] if len(jumua_times) == 1 else jumua_times
            
            self.prayer_times = prayer_times
            
            logging.info(f"[MAWAQIT] ✓ Prayer times scraped successfully from {self.location_name}")
            logging.info(f"[MAWAQIT] Timings: {prayer_times}")
            
            return self.prayer_times
            
        except requests.exceptions.ConnectionError as e:
            logging.error(f"[MAWAQIT] Connection error: {e}")
            return None
        except requests.exceptions.Timeout:
            logging.error(f"[MAWAQIT] Website timeout (10s)")
            return None
        except requests.RequestException as e:
            logging.error(f"[MAWAQIT] HTTP request error: {e}")
            return None
        except Exception as e:
            logging.error(f"[MAWAQIT] Error scraping prayer times: {e}")
            return None
    
    def get_prayer_time(self, prayer_name):
        """Get specific prayer time"""
        prayer = self.prayer_times.get(prayer_name.lower())
        if isinstance(prayer, dict):
            return prayer.get("time")
        return prayer
    
    def get_iqama_offset(self, prayer_name):
        """Get Iqama offset for a prayer (minutes after Adhan)"""
        prayer = self.prayer_times.get(prayer_name.lower())
        if isinstance(prayer, dict):
            return prayer.get("iqama_offset", 10)
        return 10
    
    def get_all_prayer_times(self):
        """Get all prayer times"""
        return self.prayer_times
    
    def is_double_jumuaa(self):
        """
        Check if Friday has double Jumuaa
        Returns: (is_double: bool, times: list)
        Example: (True, ["12:30", "13:45"])
        """
        jumua_time = self.prayer_times.get("jumua")
        if isinstance(jumua_time, list) and len(jumua_time) > 1:
            return True, jumua_time
        return False, [jumua_time] if jumua_time else []
