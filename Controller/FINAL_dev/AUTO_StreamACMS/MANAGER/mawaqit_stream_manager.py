#!/usr/bin/env python3
"""
Multi-Device Video Stream Management Script
Automatically manages display on multiple MAWAQIT Android TV boxes
based on source availability (PC VNC/HTTP, ONVIF, Mawaqit)

ACMS Configuration:
- RASPBERRY_PI: 10.1.5.10 (VLAN 5) - Executes this script
- PC_DIFFUSION: 10.1.4.250 (VLAN 4) - VNC or HTTP mode
- CAM-IMAM: 10.1.5.20 (VLAN 5)
- NVR: 10.1.6.50 (VLAN 6)
- BOX_MAWAQIT: Static IPs in VLAN 2 (10.1.2.0/24)
"""

import subprocess
import time
import logging
import socket
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import signal
import sys
import os
from datetime import datetime, timedelta

# ============================================================================
# PTZ CAMERA IMPORTS
# ============================================================================
# Ajoute le chemin du module PTZ
ptz_dir = os.path.join(os.path.dirname(__file__), "..", "PTZ")
sys.path.insert(0, ptz_dir)

try:
    from ptz_config import PTZ_CONFIG
    from ptz_controller import PTZController
    from mawaqit_parser import MawaqitParser
    from ptz_scheduler import PTZScheduler
    PTZ_AVAILABLE = True
except ImportError as e:
    PTZ_AVAILABLE = False
    print(f" Avertissement: Module PTZ non disponible: {e}")

# ============================================================================
# CONFIGURATION PARAMETERS
# ============================================================================

# VLAN 2 network parameters (BOX_MAWAQIT)
VLAN2_NETWORK = "10.1.2.0/24"
VLAN2_SCAN_START = 101     # First IP to scan (10.1.2.101)
VLAN2_SCAN_END = 120       # Last IP to scan (10.1.2.120) - Extended range for all boxes

# ADB port for box connection
ADB_PORT = 5555

# Timeouts (in seconds) - CONFIGURABLE
TIMEOUT_SCAN = 2           # Timeout to scan an IP
TIMEOUT_DEVICE_CONNECT = 5 # ADB device connection timeout
TIMEOUT_SOURCE_CHECK = 3   # Video source check timeout
TIMEOUT_COMMAND = 10       # ADB command execution timeout

# PC IP (PC_DIFFUSION) - Same PC for VNC and HTTP
PC_IP = "10.1.4.250"
PC_VNC_PORT = 5900        # VNC port
PC_HTTP_PORT = 8080       # HTTP port
PC_HTTP_PATH = "/stream"  # HTTP path
PC_VNC_PASSWORD = ""      # VNC password (leave empty if none)

# IMAM Camera (VLAN 5)
CAMERA_IP = "10.1.5.20"
CAMERA_PORT = 80
CAMERA_NAME = "CAM-IMAM"

# Android applications
APP_MAWAQIT = "com.mawaqit.androidtv"
APP_VLC = "org.videolan.vlc/.StartActivity"
APP_VNC_VIEWER = "net.christianbeier.droidvnc_ng/.MainActivity"
APP_ONVIF_VIEWER = "net.biyee.onvifer/.OnviferActivity"

# Coordinates to tap on Onvif app (camera selection)
ONVIF_TAP_X = 400
ONVIF_TAP_Y = 100

# Timing parameters
CHECK_INTERVAL = 5        # Seconds between source checks
NETWORK_RESCAN_INTERVAL = 60  # Seconds between network rescans (to detect new boxes)
ANTI_FLAP_TIME = 10       # Minimum time before source change (prevents oscillations)
                          # Explanation: If a source becomes available then unavailable
                          # quickly, we wait ANTI_FLAP_TIME seconds before switching
                          # to avoid constant changes that disrupt the display
PRE_LAUNCH_DELAY = 2      # Delay before app launch
POST_LAUNCH_DELAY = 3     # Pause after app launch
ONVIF_TAP_DELAY = 3       # Delay before tap on Onvif app

# Prayer time parameters (for automatic camera switching during prayers)
PRAYER_DURATION = 10      # Duration of prayers in minutes

# VLC cache
VLC_CACHE_MS = 300        # VLC network cache in milliseconds

# Reconnection attempts
MAX_RETRY = 3             # Maximum number of attempts

# Supervisor behavior (for crontab + shell loop)
RETRY_DELAY_ON_INIT_FAIL = 30  # Seconds to wait before retry if initialization fails
                                # Prevents rapid restart loop on persistent errors

# ============================================================================
# DYNAMIC PATHS - Relative to script location for portability
# ============================================================================
_MANAGER_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_MANAGER_DIR)
_LOGS_DIR = os.path.join(_BASE_DIR, "logs")
_SCHEDULES_DIR = os.path.join(_BASE_DIR, "schedules")

# Logging
LOG_FILE = os.path.join(_LOGS_DIR, "mawaqit_stream.log")
LOG_LEVEL = logging.INFO

# PID file (prevents multiple instances)
PID_FILE = os.path.join(_LOGS_DIR, "mawaqit_stream_manager.pid")

# Robustness & Safety Parameters
MAX_CONSECUTIVE_ERRORS = 10    # Max errors before forcing restart
WATCHDOG_TIMEOUT = 300         # Seconds - max time for one iteration (5 min)
HEARTBEAT_FILE = os.path.join(_LOGS_DIR, "mawaqit_heartbeat.txt")  # Updated each cycle
MAX_MEMORY_MB = 500            # Restart if memory exceeds this (MB)

# Scheduled restart (preventive maintenance)
SCHEDULED_RESTART_DAY = 6      # 0=Monday, 6=Sunday
SCHEDULED_RESTART_HOUR = 1     # 1 AM
SCHEDULED_RESTART_MINUTE = 0   # At exact hour

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DeviceConfig:
    """Android TV device configuration"""
    ip: str
    port: int = 5555
    name: str = ""
    model: str = ""
    has_mawaqit: bool = False

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

    def __post_init__(self):
        if not self.name:
            self.name = f"Box_{self.ip.split('.')[-1]}"

class StreamPriority(Enum):
    """Video stream priorities - HTTP is absolute priority"""
    PC_HTTP = 1      # ABSOLUTE priority (always first choice)
    ONVIF = 2        # Medium priority (during prayers only if HTTP unavailable)
    MAWAQIT = 3      # Fallback (always available)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """Formatter with colors for console"""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging():
    """Configure logging system"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(funcName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_formatter = ColoredFormatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ============================================================================
# LOG MAINTENANCE
# ============================================================================

def cleanup_old_logs():
    """Remove log files and schedule files older than 72 hours"""
    try:
        if not os.path.exists(_LOGS_DIR):
            return
        
        # Current time
        now = datetime.now()
        cutoff_time = now - timedelta(hours=72)
        
        deleted_count = 0
        
        # Clean up *.log files older than 72 hours
        for filename in os.listdir(_LOGS_DIR):
            if filename.endswith(".log"):
                filepath = os.path.join(_LOGS_DIR, filename)
                if os.path.isfile(filepath):
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_mtime < cutoff_time:
                        try:
                            os.remove(filepath)
                            logging.debug(f"Deleted old log: {filename}")
                            deleted_count += 1
                        except Exception as e:
                            logging.warning(f"Failed to delete {filename}: {e}")
        
        # Clean up schedule JSON files older than 7 days
        if os.path.exists(_SCHEDULES_DIR):
            schedule_cutoff = now - timedelta(days=7)
            for filename in os.listdir(_SCHEDULES_DIR):
                if filename.endswith(".json"):
                    filepath = os.path.join(_SCHEDULES_DIR, filename)
                    if os.path.isfile(filepath):
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if file_mtime < schedule_cutoff:
                            try:
                                os.remove(filepath)
                                logging.debug(f"Deleted old schedule: {filename}")
                                deleted_count += 1
                            except Exception as e:
                                logging.warning(f"Failed to delete schedule {filename}: {e}")
        
        if deleted_count > 0:
            logging.info(f"Log cleanup: Removed {deleted_count} old files")
    
    except Exception as e:
        logging.error(f"Error during log cleanup: {e}")

# ============================================================================
# NETWORK SCANNER
# ============================================================================

class NetworkScanner:
    """Scans VLAN 2 network to discover BOX_MAWAQIT devices"""

    @staticmethod
    def check_adb_port(ip: str, port: int, timeout: int) -> bool:
        """Check if ADB port is open on an IP"""
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
            sock.close()
            return True
        except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
            return False

    @staticmethod
    def identify_mawaqit_box(ip: str, port: int) -> Optional[Dict]:
        """
        Attempts to connect via ADB and identify if it's a MAWAQIT BOX
        Returns device info if it's a MAWAQIT BOX, None otherwise
        """
        address = None
        try:
            # Validate inputs
            if not ip or not isinstance(port, int):
                return None

            address = f"{ip}:{port}"

            # Attempt ADB connection
            result = subprocess.run(
                ["adb", "connect", address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_DEVICE_CONNECT
            )

            if "connected" not in result.stdout.decode("utf-8", errors='replace').lower():
                return None

            # Retrieve device information
            time.sleep(0.5)

            # Get model
            model_result = subprocess.run(
                ["adb", "-s", address, "shell", "getprop", "ro.product.model"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_COMMAND
            )
            model = model_result.stdout.decode("utf-8", errors='replace').strip() or "Unknown"

            # Check if Mawaqit application is installed
            app_result = subprocess.run(
                ["adb", "-s", address, "shell", "pm", "list", "packages"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_COMMAND
            )
            packages = app_result.stdout.decode("utf-8", errors='replace')
            has_mawaqit = APP_MAWAQIT in packages

            # Criteria to identify a MAWAQIT BOX:
            # 1. Mawaqit application is installed
            # 2. OR model contains "X96" or "TV Box" or "Android TV"

            is_mawaqit_box = (
                has_mawaqit or
                any(keyword in model.lower() for keyword in ["x96", "tv box", "android tv", "h96"])
            )

            if is_mawaqit_box:
                logging.info(f"MAWAQIT BOX detected: {ip} (Model: {model}, App: {has_mawaqit})")
                return {
                    "ip": ip,
                    "port": port,
                    "model": model,
                    "has_mawaqit": has_mawaqit
                }
            else:
                logging.debug(f"Android device found but not a MAWAQIT BOX: {ip} ({model})")
                # Disconnect if it's not a MAWAQIT BOX
                try:
                    subprocess.run(["adb", "disconnect", address],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                except:
                    pass
                return None

        except subprocess.TimeoutExpired:
            logging.debug(f"Timeout identifying {ip}")
            if address:
                try:
                    subprocess.run(["adb", "disconnect", address],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
                except:
                    pass
            return None
        except Exception as e:
            logging.debug(f"Identification error {ip}: {e}")
            return None

    @staticmethod
    def discover_mawaqit_boxes() -> List[DeviceConfig]:
        """
        Scans VLAN 2 network to discover all MAWAQIT BOXes
        Monolithic code - no threading
        """
        logging.info("=" * 70)
        logging.info("DISCOVERING MAWAQIT BOXes ON VLAN 2 NETWORK")
        logging.info("=" * 70)

        network_base = "10.1.2"
        logging.info(f"Scanning network {network_base}.{VLAN2_SCAN_START}-{VLAN2_SCAN_END}")
        logging.info(f"ADB Port: {ADB_PORT}, Timeout: {TIMEOUT_SCAN}s")

        discovered_boxes = []

        # Scan each IP sequentially
        for i in range(VLAN2_SCAN_START, VLAN2_SCAN_END + 1):
            ip = f"{network_base}.{i}"

            # Check if ADB port is open
            if NetworkScanner.check_adb_port(ip, ADB_PORT, TIMEOUT_SCAN):
                logging.debug(f"ADB port open on {ip}")
                # Identify if it's a MAWAQIT BOX
                result = NetworkScanner.identify_mawaqit_box(ip, ADB_PORT)
                if result:
                    device = DeviceConfig(
                        ip=result["ip"],
                        port=result["port"],
                        name=f"BOX_MAWAQIT_{result['ip'].split('.')[-1]}",
                        model=result["model"],
                        has_mawaqit=result["has_mawaqit"]
                    )
                    discovered_boxes.append(device)

        # Sort by IP
        discovered_boxes.sort(key=lambda d: int(d.ip.split('.')[-1]))

        logging.info("=" * 70)
        logging.info(f"DISCOVERY COMPLETE: {len(discovered_boxes)} MAWAQIT BOXes found")
        for box in discovered_boxes:
            mawaqit_status = "with Mawaqit app" if box.has_mawaqit else "without Mawaqit app"
            logging.info(f"  {box.name} - {box.ip} ({box.model}, {mawaqit_status})")
        logging.info("=" * 70)

        return discovered_boxes

# ============================================================================
# ADB MANAGER
# ============================================================================

class ADBManager:
    """Manages ADB connections and commands"""

    def __init__(self):
        self._connected_devices = set()

    def ensure_server_running(self) -> bool:
        """Ensure ADB server is started"""
        try:
            subprocess.run(
                ["adb", "start-server"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            return True
        except Exception as e:
            logging.error(f"Unable to start ADB server: {e}")
            return False

    def connect_device(self, device: DeviceConfig) -> bool:
        """Connect a device via ADB"""
        try:
            # Check if already connected
            result = subprocess.run(
                ["adb", "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )

            devices_output = result.stdout.decode("utf-8")
            if device.address in devices_output and "device" in devices_output:
                self._connected_devices.add(device.address)
                logging.debug(f"{device.name} already connected")
                return True

            # Connection attempt
            logging.debug(f"Connecting to {device.name} ({device.address})...")
            result = subprocess.run(
                ["adb", "connect", device.address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_DEVICE_CONNECT
            )

            output = result.stdout.decode("utf-8")
            if "connected" in output.lower():
                self._connected_devices.add(device.address)
                logging.info(f"+ {device.name} connected")
                return True
            else:
                logging.warning(f"- Connection failed {device.name}: {output}")
                return False

        except subprocess.TimeoutExpired:
            logging.error(f"- Connection timeout {device.name}")
            return False
        except Exception as e:
            logging.error(f"- Connection error {device.name}: {e}")
            return False

    def execute_command(self, device: DeviceConfig, command: List[str], retry: int = MAX_RETRY) -> Tuple[bool, str]:
        """Execute an ADB command on a device - with robust error handling"""
        if not device or not command:
            logging.error("Invalid device or command")
            return False, ""

        for attempt in range(retry):
            try:
                # Ensure device is connected
                if device.address not in self._connected_devices:
                    if not self.connect_device(device):
                        if attempt < retry - 1:
                            time.sleep(1)
                        continue

                # Build safe command
                cmd = ["adb", "-s", device.address, "shell"] + command

                # Execute command with timeout
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=TIMEOUT_COMMAND
                )

                stdout = result.stdout.decode("utf-8", errors='replace').strip()
                stderr = result.stderr.decode("utf-8", errors='replace').strip()

                if result.returncode == 0:
                    logging.debug(f"Command OK on {device.name}: {' '.join(command)}")
                    return True, stdout
                else:
                    logging.warning(f"Command error on {device.name}: {stderr}")
                    self._connected_devices.discard(device.address)

            except subprocess.TimeoutExpired:
                logging.error(f"Command timeout on {device.name}")
                self._connected_devices.discard(device.address)
            except UnicodeDecodeError as e:
                logging.error(f"Encoding error on {device.name}: {e}")
                self._connected_devices.discard(device.address)
            except Exception as e:
                logging.error(f"Command exception on {device.name}: {e}", exc_info=True)
                self._connected_devices.discard(device.address)

            if attempt < retry - 1:
                time.sleep(1)

        return False, ""

    def disconnect_all(self):
        """Disconnect all devices"""
        try:
            subprocess.run(["adb", "disconnect"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._connected_devices.clear()
            logging.info("All devices disconnected")
        except Exception as e:
            logging.error(f"Disconnection error: {e}")

# ============================================================================
# SOURCE VERIFICATION
# ============================================================================

class SourceChecker:
    """Checks video source availability"""

    @staticmethod
    def check_tcp_port(ip: str, port: int, timeout: int = TIMEOUT_SOURCE_CHECK) -> bool:
        """Check if a TCP port responds - with comprehensive error handling"""
        sock = None
        try:
            # Validate inputs
            if not ip or not isinstance(port, int) or port <= 0:
                logging.debug(f"Invalid parameters: ip={ip}, port={port}")
                return False

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            return result == 0
        except socket.timeout:
            logging.debug(f"Timeout checking {ip}:{port}")
            return False
        except socket.gaierror as e:
            logging.debug(f"DNS error for {ip}: {e}")
            return False
        except (socket.error, ConnectionRefusedError, OSError) as e:
            logging.debug(f"Connection error {ip}:{port}: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error checking {ip}:{port}: {e}")
            return False
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass

    @staticmethod
    def check_vnc() -> bool:
        """Check if VNC server responds"""
        result = SourceChecker.check_tcp_port(PC_IP, PC_VNC_PORT)
        if result:
            logging.debug(f"+ VNC accessible: {PC_IP}:{PC_VNC_PORT}")
        else:
            logging.debug(f"- VNC inaccessible: {PC_IP}:{PC_VNC_PORT}")
        return result

    @staticmethod
    def check_http() -> bool:
        """Check if HTTP stream is actually serving content"""
        try:
            # First check if port is open
            if not SourceChecker.check_tcp_port(PC_IP, PC_HTTP_PORT, timeout=2):
                logging.debug(f"- HTTP port closed: {PC_IP}:{PC_HTTP_PORT}")
                return False

            # Then verify the stream endpoint is responding with data
            url = f"http://{PC_IP}:{PC_HTTP_PORT}{PC_HTTP_PATH}"
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)

            try:
                sock.connect((PC_IP, PC_HTTP_PORT))
                # Send HTTP HEAD request to check if stream exists
                request = f"HEAD {PC_HTTP_PATH} HTTP/1.0\r\nHost: {PC_IP}\r\n\r\n"
                sock.sendall(request.encode())

                # Read response
                response = sock.recv(1024).decode('utf-8', errors='ignore')

                # Check for valid HTTP response (200 OK or similar)
                if 'HTTP/' in response and ('200' in response or '206' in response):
                    logging.debug(f"+ HTTP stream accessible: {url}")
                    return True
                else:
                    logging.debug(f"- HTTP stream returned: {response[:50]}")
                    return False
            finally:
                sock.close()

        except socket.timeout:
            logging.debug(f"- HTTP stream timeout: {PC_IP}:{PC_HTTP_PORT}{PC_HTTP_PATH}")
            return False
        except Exception as e:
            logging.debug(f"- HTTP stream check error: {e}")
            return False

    @staticmethod
    def check_onvif() -> bool:
        """Check if ONVIF camera responds"""
        result = SourceChecker.check_tcp_port(CAMERA_IP, CAMERA_PORT)
        if result:
            logging.debug(f"+ ONVIF accessible: {CAMERA_NAME} ({CAMERA_IP})")
        else:
            logging.debug(f"- ONVIF inaccessible: {CAMERA_NAME}")
        return result

# ============================================================================
# STREAM MANAGER
# ============================================================================

class StreamManager:
    """Manages streaming on devices"""

    def __init__(self, adb_manager: ADBManager):
        self.adb = adb_manager
        self.device_states: Dict[str, Dict] = {}

    def _get_device_state(self, device: DeviceConfig) -> Dict:
        """Get device state"""
        if device.address not in self.device_states:
            self.device_states[device.address] = {
                "current_stream": None,
                "last_switch_time": 0,
                "device": device,
                "error_count": 0,
                "last_error_time": 0,
                "total_switches": 0,
                "verification_failures": 0,
                "blocked_stream": None
            }
        return self.device_states[device.address]

    def _can_switch(self, device: DeviceConfig, new_stream: str) -> bool:
        """
        Check if we can change stream (anti-flapping)
        ANTI_FLAP_TIME prevents too frequent changes that disrupt display
        """
        state = self._get_device_state(device)
        now = time.time()

        if state["current_stream"] == new_stream:
            return False

        # Block if this stream has failed verification multiple times
        if state.get("blocked_stream") == new_stream:
            return False

        if now - state["last_switch_time"] < ANTI_FLAP_TIME:
            logging.debug(f"Anti-flap active for {device.name} ({ANTI_FLAP_TIME}s)")
            return False

        return True

    def _update_state(self, device: DeviceConfig, stream: str):
        """Update device state"""
        state = self._get_device_state(device)
        state["current_stream"] = stream
        state["last_switch_time"] = time.time()
        # Reset verification failures on successful switch
        state["verification_failures"] = 0

    def _record_verification_failure(self, device: DeviceConfig, stream: str):
        """Record verification failure and block stream after max failures"""
        state = self._get_device_state(device)
        state["verification_failures"] = state.get("verification_failures", 0) + 1

        if state["verification_failures"] >= 5:
            logging.error(f"Stream {stream} failed {state['verification_failures']} times on {device.name} - BLOCKING")
            state["blocked_stream"] = stream
            state["verification_failures"] = 0  # Reset counter
            return True  # Blocked
        return False

    def _unblock_stream(self, device: DeviceConfig, stream: str):
        """Unblock a stream when source state changes"""
        state = self._get_device_state(device)
        if state.get("blocked_stream") == stream:
            logging.info(f"Unblocking stream {stream} on {device.name}")
            state["blocked_stream"] = None
            state["verification_failures"] = 0

    def _get_foreground_app(self, device: DeviceConfig) -> Optional[str]:
        """Get the package name of the currently focused app"""
        try:
            command = ["dumpsys", "activity", "activities"]
            success, output = self.adb.execute_command(device, command)

            if success and output:
                # Parse output to find mResumedActivity line
                # Format: mResumedActivity: ActivityRecord{HASH u0 com.package.name/.ActivityName tID}
                for line in output.split('\n'):
                    if 'mResumedActivity' in line or 'mFocusedActivity' in line:
                        # Extract package name
                        if ' u0 ' in line:
                            # Split by 'u0 ' and get the part after
                            parts = line.split(' u0 ')
                            if len(parts) > 1:
                                # Get package/activity part
                                package_part = parts[1].split()[0]  # First element after 'u0 '
                                # Extract package name (before '/')
                                if '/' in package_part:
                                    package = package_part.split('/')[0]
                                    logging.debug(f"{device.name} foreground app: {package}")
                                    return package
            return None
        except Exception as e:
            logging.debug(f"Error getting foreground app for {device.name}: {e}")
            return None

    def _verify_app_launched(self, device: DeviceConfig, expected_package: str, max_retries: int = 3) -> bool:
        """Verify that the expected app is in foreground"""
        try:
            for attempt in range(max_retries):
                time.sleep(1)  # Wait for app to start
                foreground_app = self._get_foreground_app(device)

                if foreground_app and expected_package in foreground_app:
                    logging.debug(f"Verified {expected_package} on {device.name}")
                    return True

                logging.debug(f"Attempt {attempt + 1}/{max_retries}: {device.name} foreground={foreground_app}")

            logging.warning(f"Failed to verify {expected_package} on {device.name}")
            return False
        except Exception as e:
            logging.error(f"Error verifying app on {device.name}: {e}")
            return False

    def play_vnc(self, device: DeviceConfig) -> bool:
        """Launch VNC viewer - with error isolation"""
        try:
            stream_id = f"VNC:{PC_IP}:{PC_VNC_PORT}"
            if not self._can_switch(device, stream_id):
                return False

            logging.info(f"-> Launching VNC on {device.name}: {PC_IP}:{PC_VNC_PORT}")
            time.sleep(PRE_LAUNCH_DELAY)

            vnc_uri = f"vnc://{PC_IP}:{PC_VNC_PORT}"
            intent_command = [
                "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", vnc_uri,
                "-n", APP_VNC_VIEWER
            ]

            success, _ = self.adb.execute_command(device, intent_command)

            if success:
                self._update_state(device, stream_id)
                logging.info(f"+ VNC command sent to {device.name}")
                time.sleep(POST_LAUNCH_DELAY)
                return True
            else:
                logging.error(f"- VNC launch failed on {device.name}")
                self._record_error(device)
                return False
        except Exception as e:
            logging.error(f"Exception in play_vnc for {device.name}: {e}", exc_info=True)
            self._record_error(device)
            return False

    def play_http_vlc(self, device: DeviceConfig) -> bool:
        """Launch VLC for HTTP stream - with error isolation"""
        try:
            url = f"http://{PC_IP}:{PC_HTTP_PORT}{PC_HTTP_PATH}"
            if not self._can_switch(device, f"HTTP:{url}"):
                return False

            logging.info(f"-> Launching HTTP on {device.name}: {url}")
            time.sleep(PRE_LAUNCH_DELAY)

            intent_command = [
                "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", url,
                "-n", APP_VLC,
                "--ei", "network-caching", str(VLC_CACHE_MS)
            ]

            success, _ = self.adb.execute_command(device, intent_command)

            if success:
                self._update_state(device, f"HTTP:{url}")
                logging.info(f"+ HTTP command sent to {device.name}")
                time.sleep(POST_LAUNCH_DELAY)
                return True
            else:
                logging.error(f"- HTTP launch failed on {device.name}")
                self._record_error(device)
                return False
        except Exception as e:
            logging.error(f"Exception in play_http_vlc for {device.name}: {e}", exc_info=True)
            self._record_error(device)
            return False

    def play_onvif(self, device: DeviceConfig) -> bool:
        """Launch ONVIF viewer for camera - with error isolation"""
        try:
            if not self._can_switch(device, f"ONVIF:{CAMERA_NAME}"):
                return False

            logging.info(f"-> Launching ONVIF on {device.name}: {CAMERA_NAME}")
            time.sleep(PRE_LAUNCH_DELAY)

            intent_command = ["am", "start", "-n", APP_ONVIF_VIEWER]
            success, _ = self.adb.execute_command(device, intent_command)

            if success:
                # Onvifer auto-starts camera stream (no tap needed)
                time.sleep(2)  # Short delay for app startup

                self._update_state(device, f"ONVIF:{CAMERA_NAME}")
                logging.info(f"+ ONVIF command sent to {device.name}")
                time.sleep(POST_LAUNCH_DELAY)
                return True
            else:
                logging.error(f"- ONVIF launch failed on {device.name}")
                self._record_error(device)
                return False
        except Exception as e:
            logging.error(f"Exception in play_onvif for {device.name}: {e}", exc_info=True)
            self._record_error(device)
            return False

    def play_mawaqit(self, device: DeviceConfig) -> bool:
        """Launch Mawaqit (fallback) - with error isolation"""
        try:
            if not self._can_switch(device, "MAWAQIT"):
                return False

            logging.info(f"-> Launching Mawaqit on {device.name}")

            monkey_command = ["monkey", "-p", APP_MAWAQIT, "1"]
            success, _ = self.adb.execute_command(device, monkey_command)

            if success:
                self._update_state(device, "MAWAQIT")
                logging.info(f"+ Mawaqit command sent to {device.name}")
                time.sleep(POST_LAUNCH_DELAY)
                return True
            else:
                logging.error(f"- Mawaqit launch failed on {device.name}")
                self._record_error(device)
                return False
        except Exception as e:
            logging.error(f"Exception in play_mawaqit for {device.name}: {e}", exc_info=True)
            self._record_error(device)
            return False

    def _record_error(self, device: DeviceConfig):
        """Record error for device - helps track problematic boxes"""
        try:
            state = self._get_device_state(device)
            state["error_count"] = state.get("error_count", 0) + 1
            state["last_error_time"] = time.time()

            if state["error_count"] >= 5:
                logging.warning(f"Device {device.name} has {state['error_count']} errors")
        except Exception as e:
            logging.debug(f"Error recording error for {device.name}: {e}")

    def get_current_stream(self, device: DeviceConfig) -> Optional[str]:
        """Get currently displayed stream"""
        try:
            state = self._get_device_state(device)
            return state["current_stream"]
        except Exception as e:
            logging.debug(f"Error getting current stream for {device.name}: {e}")
            return None

# ============================================================================
# MULTI-DEVICE CONTROLLER
# ============================================================================

class MultiDeviceController:
    """Controls multiple devices"""

    def __init__(self):
        self.adb = ADBManager()
        self.stream_manager = StreamManager(self.adb)
        self.devices: List[DeviceConfig] = []

        # Global source state (HTTP is priority, VNC removed)
        self.http_available = False
        self.onvif_available = False

        self._running = False
        self._box_115_initialized = False  # Track if .115 has been launched

        # ============================================================
        # PTZ CAMERA INITIALIZATION
        # ============================================================
        self.ptz_controller = None
        self.ptz_parser = None
        self.ptz_scheduler = None
        self.last_ptz_schedule_update = 0  # Timestamp for last schedule update
        self.ptz_check_interval = 60  # Vérifier PTZ chaque minute
        self.ptz_update_interval = 3600  # Mettre à jour schedule chaque HEURE (au lieu de 24h)
        self.ptz_last_schedule_date = None  # Track the date of current schedule
    
        if PTZ_AVAILABLE:
            try:
                # Update PTZ config with dynamic paths
                PTZ_CONFIG["schedules_dir"] = _SCHEDULES_DIR + "/"
                PTZ_CONFIG["logs_dir"] = _LOGS_DIR + "/"
                
                logging.info("[PTZ] Initialisation du système PTZ...")
                self.ptz_controller = PTZController(PTZ_CONFIG)
                self.ptz_parser = MawaqitParser(cache_dir=_SCHEDULES_DIR)
                self.ptz_scheduler = PTZScheduler(self.ptz_controller, self.ptz_parser, PTZ_CONFIG)
                
                # Test connexion caméra
                if self.ptz_controller.get_device_info():
                    logging.info("[PTZ] Camera IMAM connectee (10.1.5.20)")
                    # Mise à jour du planning au démarrage
                    self.ptz_scheduler.update_daily_schedule()
                    self.last_ptz_schedule_update = time.time()
                    self.ptz_last_schedule_date = datetime.now().strftime("%Y-%m-%d")
                else:
                    logging.error("[PTZ] Camera IMAM non accessible")
            except Exception as e:
                logging.error(f"[PTZ] Erreur initialisation: {e}")

    def _check_and_update_ptz(self):
        """
        Vérifie les événements PTZ et les exécute
        À appeler régulièrement dans la boucle principale
        """
        if not self.ptz_scheduler or not self.ptz_controller:
            return
        
        try:
            now = time.time()
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Mettre à jour si:
            # 1. Le jour a changé (minuit)
            # 2. Ou l'intervalle de 1h est dépassé
            should_update = False
            
            if self.ptz_last_schedule_date != today:
                logging.info(f"[PTZ] Date changed ({self.ptz_last_schedule_date} → {today}), forcing schedule update")
                should_update = True
            elif now - self.last_ptz_schedule_update > self.ptz_update_interval:
                logging.debug(f"[PTZ] Update interval ({self.ptz_update_interval}s) elapsed, refreshing schedule")
                should_update = True
            
            if should_update:
                logging.info("[PTZ] Mise à jour du planning...")
                if self.ptz_scheduler.update_daily_schedule():
                    self.last_ptz_schedule_update = now
                    self.ptz_last_schedule_date = today
            
            # Vérifier et exécuter les événements chaque minute
            self.ptz_scheduler.check_and_execute()
            
        except Exception as e:
            logging.error(f"[PTZ] Erreur vérification: {e}")

    def initialize(self) -> bool:
        """Initialize the system"""
        logging.info("=" * 70)
        logging.info("MULTI-DEVICE MAWAQIT SYSTEM INITIALIZATION")
        logging.info("=" * 70)

        # Start ADB server
        if not self.adb.ensure_server_running():
            logging.error("Unable to start ADB server")
            return False

        # AUTOMATIC DISCOVERY OF MAWAQIT BOXes
        logging.info("Automatic discovery of MAWAQIT BOXes on network...")
        self.devices = NetworkScanner.discover_mawaqit_boxes()

        if not self.devices:
            logging.error("No MAWAQIT BOX discovered on VLAN 2 network")
            logging.error("Verify that:")
            logging.error("  1. Boxes are powered on")
            logging.error("  2. Boxes are connected to VLAN 2 network")
            logging.error("  3. ADB is enabled on boxes")
            logging.error("  4. Boxes have IPs in configured range")
            return False

        logging.info(f"Configuration: {len(self.devices)} MAWAQIT BOXes found")

        # Check connection state
        connected_count = 0
        for device in self.devices:
            if device.address in self.adb._connected_devices:
                connected_count += 1
            else:
                if self.adb.connect_device(device):
                    connected_count += 1

        logging.info(f"{connected_count}/{len(self.devices)} devices connected")

        if connected_count == 0:
            logging.error("No device connected")
            return False

        return True

    def check_sources(self):
        """Check state of all sources - HTTP is priority"""
        prev_http = self.http_available
        prev_onvif = self.onvif_available

        try:
            self.http_available = SourceChecker.check_http()
        except Exception as e:
            logging.error(f"Error checking HTTP: {e}")
            self.http_available = False

        try:
            self.onvif_available = SourceChecker.check_onvif()
        except Exception as e:
            logging.error(f"Error checking ONVIF: {e}")
            self.onvif_available = False

        # Unblock streams when HTTP becomes available
        if not prev_http and self.http_available:
            logging.info("HTTP stream became available - unblocking")
            for device in self.devices:
                self.stream_manager._unblock_stream(device, f"HTTP:http://{PC_IP}:{PC_HTTP_PORT}{PC_HTTP_PATH}")
            for device in self.devices:
                self.stream_manager._unblock_stream(device, f"VNC:{PC_IP}:{PC_VNC_PORT}")

        if not prev_onvif and self.onvif_available:
            logging.info("ONVIF stream became available - unblocking")
            for device in self.devices:
                self.stream_manager._unblock_stream(device, f"ONVIF:{CAMERA_NAME}")

    def get_prayer_info(self):
        """
        Détecte si on est actuellement DANS une période de prière avec ONVIF
        Retourne: {
            "type": "tahajuud"|"fajr"|"iqama"|"jumuaa"|"tarawih"|None,
            "prayer": prayer_key,
            "description": description,
            "onvif_start": HH:MM,
            "onvif_end": HH:MM
        } ou None si pas en période prière
        """
        if not self.ptz_scheduler or not self.ptz_scheduler.current_schedule:
            return None
        
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            
            # Parcourt chaque événement du planning
            for event in self.ptz_scheduler.current_schedule.get("events", []):
                event_type = event.get("type")
                
                # Support pour tous les types de prière
                if event_type == "tahajuud":
                    # Tahajuud: de onvif_start à onvif_end
                    start_str = event.get("onvif_start")
                    end_str = event.get("onvif_end")
                    if start_str and end_str:
                        start_dt = datetime.strptime(f"{today} {start_str}", "%Y-%m-%d %H:%M")
                        end_dt = datetime.strptime(f"{today} {end_str}", "%Y-%m-%d %H:%M")
                        if start_dt <= now <= end_dt:
                            return {
                                "type": "tahajuud",
                                "prayer": "tahajuud",
                                "description": event.get("description", "Tahajuud"),
                                "onvif_start": start_str,
                                "onvif_end": end_str
                            }
                
                elif event_type == "iqama":
                    # Salat normal: de iqama_time à iqama_time + 10 min
                    start_str = event.get("iqama_time")
                    if start_str:
                        start_dt = datetime.strptime(f"{today} {start_str}", "%Y-%m-%d %H:%M")
                        end_dt = start_dt + timedelta(minutes=10)
                        if start_dt <= now <= end_dt:
                            return {
                                "type": "iqama",
                                "prayer": event.get("prayer", "unknown"),
                                "description": event.get("description", f"Salat {event.get('prayer')}"),
                                "onvif_start": start_str,
                                "onvif_end": end_dt.strftime("%H:%M")
                            }
                
                elif event_type in ["jumua_pre", "jumua_khotba", "jumua_position3"]:
                    # Jumuaa: de -10min avant la première jusqu'à +60min après la deuxième
                    jumua_time_str = event.get("jumua_time")
                    if jumua_time_str:
                        jumua_dt = datetime.strptime(f"{today} {jumua_time_str}", "%Y-%m-%d %H:%M")
                        jumuaa_start = jumua_dt - timedelta(minutes=10)
                        jumuaa_end = jumua_dt + timedelta(minutes=60)
                        if jumuaa_start <= now <= jumuaa_end:
                            return {
                                "type": "jumuaa",
                                "prayer": "jumua",
                                "description": event.get("description", "Jumuaa"),
                                "onvif_start": jumuaa_start.strftime("%H:%M"),
                                "onvif_end": jumuaa_end.strftime("%H:%M")
                            }
                
                elif event_type == "tarawih":
                    # Tarawih: de isha_time à isha_time + 150 min
                    start_str = event.get("onvif_start")
                    end_str = event.get("onvif_end")
                    if start_str and end_str:
                        start_dt = datetime.strptime(f"{today} {start_str}", "%Y-%m-%d %H:%M")
                        end_dt = datetime.strptime(f"{today} {end_str}", "%Y-%m-%d %H:%M")
                        if start_dt <= now <= end_dt:
                            return {
                                "type": "tarawih",
                                "prayer": "tarawih",
                                "description": event.get("description", "Tarawih"),
                                "onvif_start": start_str,
                                "onvif_end": end_str
                            }
            
            return None
        
        except Exception as e:
            logging.error(f"Error in get_prayer_info: {e}")
            return None

    def update_device(self, device: DeviceConfig) -> bool:
        """
        Update device display based on source availability.
        
        Logic (NEW):
        1. HTTP available? → Use HTTP (ABSOLUTE PRIORITY)
        2. HTTP DOWN + In prayer time? → Use ONVIF if available
        3. Fallback → Use MAWAQIT (always available)
        
        Prayer types that trigger ONVIF (if HTTP is down):
        - tahajuud, fajr, iqama (salat), jumuaa, tarawih
        """
        try:
            # ====== RULE 1: HTTP PRIORITAIRE (ABSOLUTE) ======
            if self.http_available:
                logging.debug(f"HTTP available → streaming on {device.name}")
                return self.stream_manager.play_http_vlc(device)

            # ====== RULE 2: HTTP DOWN, check for prayer + ONVIF ======
            prayer_info = self.get_prayer_info()
            
            if prayer_info and self.onvif_available:
                prayer_type = prayer_info.get("type")
                description = prayer_info.get("description", "")
                
                # Types de prière qui utilisent ONVIF
                prayer_types_with_onvif = ["tahajuud", "fajr", "iqama", "jumuaa", "tarawih"]
                
                if prayer_type in prayer_types_with_onvif:
                    logging.info(f"[ONVIF] Prayer detected ({prayer_type}): {description} on {device.name}")
                    return self.stream_manager.play_onvif(device)

            # ====== RULE 3: FALLBACK to MAWAQIT ======
            if prayer_info:
                logging.info(f"Prayer but ONVIF unavailable → Mawaqit on {device.name}")
            return self.stream_manager.play_mawaqit(device)

        except Exception as e:
            logging.error(f"Update error {device.name}: {e}")
            return False

    def launch_mawaqit_on_box_115(self):
        """Launch MAWAQIT app on box .115 ONCE at startup (workaround for auto-start issue)"""
        # Only execute once
        if self._box_115_initialized:
            return

        box_115_ip = "10.1.2.115"

        # Check if box .115 is in our devices list
        box_115 = None
        for device in self.devices:
            if device.ip == box_115_ip:
                box_115 = device
                break

        if not box_115:
            # Box not discovered, skip initialization
            logging.debug(f"Box {box_115_ip} not discovered, skipping MAWAQIT auto-launch")
            self._box_115_initialized = True
            return

        # Ensure connected
        if box_115.address not in self.adb._connected_devices:
            if not self.adb.connect_device(box_115):
                logging.warning(f"Cannot connect to {box_115_ip}, will retry later")
                return  # Don't mark as initialized, will retry next cycle

        # Launch MAWAQIT
        logging.info(f"Initial MAWAQIT launch on {box_115_ip} (startup workaround)...")
        launch_cmd = ["am", "start", "-n", f"{APP_MAWAQIT}/.MainActivity"]
        success, output = self.adb.execute_command(box_115, launch_cmd)

        if success:
            logging.info(f"MAWAQIT launched on {box_115_ip}")
            self._box_115_initialized = True
        else:
            logging.warning(f"Failed to launch MAWAQIT on {box_115_ip}, will retry later")

    def update_all_devices(self):
        """Update all devices sequentially"""
        for device in self.devices:
            try:
                self.update_device(device)
            except Exception as e:
                logging.error(f"Error updating {device.name}: {e}")

    def verify_all_devices(self):
        """Verify that apps are actually running on all devices after launch commands"""
        logging.info("Verifying apps on all devices...")

        # Wait a bit for all apps to start
        time.sleep(3)

        for device in self.devices:
            try:
                expected_stream = self.stream_manager.get_current_stream(device)
                if not expected_stream:
                    logging.debug(f"{device.name}: No expected stream")
                    continue

                logging.debug(f"{device.name}: Expected stream = {expected_stream}")

                # Determine expected package based on stream type
                expected_package = None
                if expected_stream == "MAWAQIT":
                    expected_package = "com.mawaqit"  # Will match both .androidtv and .launcher
                elif expected_stream.startswith("VNC:"):
                    expected_package = "droidvnc_ng"
                elif expected_stream.startswith("HTTP:"):
                    expected_package = "org.videolan.vlc"
                elif expected_stream.startswith("ONVIF:"):
                    expected_package = "net.biyee.onvifer"

                if expected_package:
                    foreground_app = self.stream_manager._get_foreground_app(device)

                    if foreground_app and expected_package in foreground_app:
                        logging.info(f"{device.name}: {expected_package} verified")
                    else:
                        logging.warning(f"{device.name}: Expected {expected_package}, got {foreground_app}")

                        # Retry expected app launch a few times without reboot
                        max_retries = 5
                        for attempt in range(1, max_retries + 1):
                            logging.info(f"Relaunching expected app on {device.name} (attempt {attempt}/{max_retries})")

                            if expected_package == "com.mawaqit":
                                self.stream_manager.play_mawaqit(device)
                            elif expected_package == "org.videolan.vlc":
                                self.stream_manager.play_http_vlc(device)
                            elif expected_package == "droidvnc_ng":
                                self.stream_manager.play_vnc(device)
                            elif expected_package == "net.biyee.onvifer":
                                self.stream_manager.play_onvif(device)
                            else:
                                break

                            time.sleep(10)
                            foreground_app = self.stream_manager._get_foreground_app(device)
                            if foreground_app and expected_package in foreground_app:
                                logging.info(f"{device.name}: {expected_package} verified after retry")
                                break
                        continue

                        # Force close the failed app to prevent it staying open with error
                        if expected_package == "org.videolan.vlc":
                            logging.info(f"Force closing VLC on {device.name}")
                            self.adb.execute_command(device, ["am", "force-stop", "org.videolan.vlc"])
                        elif expected_package == "droidvnc_ng":
                            logging.info(f"Force closing VNC on {device.name}")
                            self.adb.execute_command(device, ["am", "force-stop", "net.christianbeier.droidvnc_ng"])
                        elif expected_package == "net.biyee.onvifer":
                            logging.info(f"Force closing ONVIF on {device.name}")
                            self.adb.execute_command(device, ["am", "force-stop", "net.biyee.onvifer"])

                        # Record verification failure
                        blocked = self.stream_manager._record_verification_failure(device, expected_stream)

                        if blocked:
                            # Max failures reached - fallback to MAWAQIT
                            logging.error(f"Fallback to MAWAQIT on {device.name} after repeated failures")
                            self.stream_manager.play_mawaqit(device)
                        else:
                            # Before retrying, check if the source is still actually available
                            logging.info(f"Rechecking source availability before retry on {device.name}...")

                            # Recheck sources to get current state
                            self.check_sources()

                            # Now retry with updated source availability
                            logging.info(f"Retrying launch on {device.name} with current sources...")
                            self.update_device(device)

            except Exception as e:
                logging.error(f"Error verifying {device.name}: {e}")

    def print_status(self):
        """Display system status"""
        logging.info("-" * 70)
        http_status = "OK" if self.http_available else "KO"
        onvif_status = "OK" if self.onvif_available else "KO"
        logging.info(f"SOURCES: HTTP={http_status} | ONVIF={onvif_status}")

        # Display each device state
        for device in self.devices:
            current = self.stream_manager.get_current_stream(device)
            if current:
                logging.info(f"  {device.name}: {current}")

    def run(self):
        """Main loop - with comprehensive error handling and watchdog"""
        self._running = True
        iteration = 0
        consecutive_errors = 0
        last_heartbeat = time.time()
        last_restart_check = time.time()
        last_network_scan = time.time()

        try:
            logging.info("=" * 70)
            logging.info("STARTING MAIN LOOP")
            logging.info(f"Scheduled restart: Every Sunday at {SCHEDULED_RESTART_HOUR:02d}:{SCHEDULED_RESTART_MINUTE:02d}")
            logging.info("=" * 70)

            while self._running:
                iteration_start = time.time()
                iteration += 1

                try:
                    logging.debug(f"Cycle #{iteration}")

                    # Watchdog: Check if iteration takes too long
                    if time.time() - iteration_start > WATCHDOG_TIMEOUT:
                        logging.error(f"Watchdog: Iteration took too long, forcing restart")
                        break

                    # Check sources
                    self.check_sources()

                    # Launch MAWAQIT on box .115 if needed (only once at startup)
                    if not self._box_115_initialized:
                        try:
                            self.launch_mawaqit_on_box_115()
                        except Exception as e:
                            logging.error(f"Error launching MAWAQIT on .115: {e}")

                    # Update all devices (errors isolated per device)
                    self.update_all_devices()

                    # Verify all devices after launch commands
                    self.verify_all_devices()

                    # ============================================================
                    # CHECK & UPDATE PTZ CAMERA (Caméra IMAM)
                    # ============================================================
                    self._check_and_update_ptz()

                    # Display status every 10 iterations
                    if iteration % 10 == 0:
                        self.print_status()

                    # Update heartbeat file
                    if time.time() - last_heartbeat > 30:
                        self._update_heartbeat()
                        last_heartbeat = time.time()

                    # Rescan network for new boxes
                    if time.time() - last_network_scan > NETWORK_RESCAN_INTERVAL:
                        try:
                            logging.info("Rescanning network for new MAWAQIT boxes...")
                            new_boxes = NetworkScanner.discover_mawaqit_boxes()

                            # Check if new boxes were discovered
                            current_ips = {device.ip for device in self.devices}
                            new_ips = {box.ip for box in new_boxes}
                            added_ips = new_ips - current_ips
                            removed_ips = current_ips - new_ips

                            if added_ips:
                                logging.info(f"New box(es) detected: {', '.join(sorted(added_ips))}")
                                # Connect new boxes
                                for box in new_boxes:
                                    if box.ip in added_ips:
                                        if self.adb.connect_device(box):
                                            logging.info(f"+ {box.name} connected and added to management")

                            if removed_ips:
                                logging.info(f"Box(es) disconnected: {', '.join(sorted(removed_ips))}")

                            # Update device list
                            self.devices = new_boxes
                            last_network_scan = time.time()

                        except Exception as e:
                            logging.error(f"Error during network rescan: {e}")
                            last_network_scan = time.time()  # Reset timer even on error

                    # Check memory usage every 50 iterations
                    if iteration % 50 == 0:
                        self._check_memory_usage()

                    # Check for scheduled restart (every 5 minutes)
                    if time.time() - last_restart_check > 300:
                        if self._should_scheduled_restart():
                            logging.info("Scheduled weekly restart time reached (Sunday 1 AM)")
                            logging.info("Performing clean restart for maintenance...")
                            break
                        last_restart_check = time.time()

                    # Reset error counter on successful iteration
                    consecutive_errors = 0

                except Exception as e:
                    consecutive_errors += 1
                    logging.error(f"Error in iteration #{iteration}: {e}", exc_info=True)

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logging.critical(f"Too many consecutive errors ({consecutive_errors}), forcing restart")
                        break

                    # Continue to next iteration after error
                    time.sleep(2)  # Brief pause after error

                # Wait before next check
                try:
                    time.sleep(CHECK_INTERVAL)
                except Exception as e:
                    logging.error(f"Error during sleep: {e}")

        except KeyboardInterrupt:
            logging.info("Keyboard interruption detected")
        except Exception as e:
            logging.critical(f"Fatal error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def _should_scheduled_restart(self) -> bool:
        """Check if we've reached the scheduled weekly restart time"""
        try:
            from datetime import datetime
            now = datetime.now()

            # Check if it's the scheduled day and hour
            if now.weekday() == SCHEDULED_RESTART_DAY:
                if now.hour == SCHEDULED_RESTART_HOUR and now.minute < 10:
                    # Within 10 minutes window of scheduled time
                    logging.debug(f"Scheduled restart check: It's Sunday {now.hour}:{now.minute:02d}")
                    return True

            return False
        except Exception as e:
            logging.error(f"Error checking scheduled restart: {e}")
            return False

    def _update_heartbeat(self):
        """Update heartbeat file to signal system is alive"""
        try:
            import os
            with open(HEARTBEAT_FILE, 'w') as f:
                f.write(f"{time.time()}\n{os.getpid()}\n")
            logging.debug("Heartbeat updated")
        except Exception as e:
            logging.warning(f"Failed to update heartbeat: {e}")

    def _check_memory_usage(self):
        """Check memory usage and warn if too high"""
        try:
            import os
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024

            if memory_mb > MAX_MEMORY_MB:
                logging.warning(f"High memory usage: {memory_mb:.1f} MB (limit: {MAX_MEMORY_MB} MB)")
                logging.warning("Consider restarting to free memory")
            else:
                logging.debug(f"Memory usage: {memory_mb:.1f} MB")
        except ImportError:
            # psutil not available, skip check
            pass
        except Exception as e:
            logging.debug(f"Error checking memory: {e}")

    def shutdown(self):
        """Clean system shutdown"""
        logging.info("=" * 70)
        logging.info("SYSTEM SHUTDOWN")
        logging.info("=" * 70)

        self._running = False

        # Disconnect devices
        try:
            logging.info("Disconnecting devices...")
            self.adb.disconnect_all()
        except Exception as e:
            logging.error(f"Error disconnecting devices: {e}")

        # Remove heartbeat file
        try:
            import os
            if os.path.exists(HEARTBEAT_FILE):
                os.remove(HEARTBEAT_FILE)
        except Exception as e:
            logging.debug(f"Error removing heartbeat file: {e}")

        logging.info("Shutdown complete")

# ============================================================================
# SIGNAL HANDLING
# ============================================================================

controller: Optional[MultiDeviceController] = None

def signal_handler(sig, frame):
    """Handle shutdown signals (Ctrl+C, SIGTERM)"""
    global controller
    logging.info(f"Signal {sig} received")
    if controller:
        controller.shutdown()
    remove_pid_file()
    sys.exit(0)

# ============================================================================
# PID FILE MANAGEMENT
# ============================================================================

def is_process_alive_and_responsive(pid: int) -> bool:
    """Check if process is alive and responsive (not zombie/hung)"""
    try:
        import os
        # Check if process exists
        os.kill(pid, 0)

        # Check if it's our script by reading /proc/[pid]/cmdline
        try:
            with open(f'/proc/{pid}/cmdline', 'r') as f:
                cmdline = f.read()
                # Check if it's the mawaqit_stream_manager.py script
                if 'mawaqit_stream_manager' not in cmdline:
                    logging.warning(f"PID {pid} exists but is not mawaqit_stream_manager")
                    return False

            # Check process state (Z = zombie)
            with open(f'/proc/{pid}/status', 'r') as f:
                for line in f:
                    if line.startswith('State:'):
                        state = line.split()[1]
                        if state == 'Z':
                            logging.warning(f"Process {pid} is a zombie")
                            return False
                        break

            return True
        except FileNotFoundError:
            # /proc not available (not Linux), assume alive if kill(0) succeeded
            return True

    except OSError:
        # Process doesn't exist
        return False
    except Exception as e:
        logging.warning(f"Error checking process {pid}: {e}")
        return False

def kill_stuck_process(pid: int) -> bool:
    """Kill a stuck/zombie process"""
    try:
        import os
        import time

        logging.warning(f"Attempting to kill stuck process {pid}...")

        # Try graceful termination first (SIGTERM)
        try:
            os.kill(pid, signal.SIGTERM)
            logging.info(f"Sent SIGTERM to process {pid}, waiting 5s...")
            time.sleep(5)

            # Check if still alive
            try:
                os.kill(pid, 0)
                # Still alive, force kill
                logging.warning(f"Process {pid} didn't respond to SIGTERM, sending SIGKILL...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(2)
            except OSError:
                # Process terminated
                logging.info(f"Process {pid} terminated gracefully")
                return True

        except OSError:
            # Already dead
            logging.info(f"Process {pid} already terminated")
            return True

        # Final check
        try:
            os.kill(pid, 0)
            logging.error(f"Failed to kill process {pid}")
            return False
        except OSError:
            logging.info(f"Process {pid} successfully killed")
            return True

    except Exception as e:
        logging.error(f"Error killing process {pid}: {e}")
        return False

def create_pid_file() -> bool:
    """Create PID file to prevent multiple instances - with stuck process recovery"""
    try:
        import os
        if os.path.exists(PID_FILE):
            # Check if process is still running
            try:
                with open(PID_FILE, 'r') as f:
                    old_pid = int(f.read().strip())

                # Check if process is alive and responsive
                if is_process_alive_and_responsive(old_pid):
                    logging.error(f"Another instance is already running (PID {old_pid})")
                    logging.error("If you believe this is an error, manually remove:")
                    logging.error(f"  sudo rm {PID_FILE}")
                    return False
                else:
                    # Process is dead, zombie, or hung - kill it
                    logging.warning(f"Found dead/stuck process (PID {old_pid})")
                    if kill_stuck_process(old_pid):
                        logging.info("Stuck process cleaned up, continuing startup...")
                        os.remove(PID_FILE)
                    else:
                        logging.error("Failed to clean up stuck process")
                        return False

            except (OSError, ValueError) as e:
                # Invalid PID file, remove it
                logging.warning(f"Invalid PID file: {e}, removing...")
                os.remove(PID_FILE)

        # Create new PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logging.debug(f"PID file created: {PID_FILE}")
        return True
    except Exception as e:
        logging.warning(f"Could not create PID file: {e} (continuing anyway)")
        return True  # Don't fail if PID file can't be created

def remove_pid_file():
    """Remove PID file on clean exit"""
    try:
        import os
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logging.debug(f"PID file removed")
    except Exception as e:
        logging.warning(f"Could not remove PID file: {e}")

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main function - Compatible with crontab + supervisor loop"""
    global controller
    import os

    # Configure logging
    setup_logging()
    
    # Clean up old logs on startup
    cleanup_old_logs()

    # Log process info for supervisor monitoring
    logging.info("=" * 70)
    logging.info("MULTI-DEVICE MAWAQIT MANAGER - ACMS")
    logging.info("=" * 70)
    logging.info(f"PID: {os.getpid()}")
    logging.info(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"Log: {LOG_FILE}")
    logging.info(f"Network: {VLAN2_NETWORK} (scan: .{VLAN2_SCAN_START}-.{VLAN2_SCAN_END})")
    logging.info(f"PC: {PC_IP} (VNC:{PC_VNC_PORT}, HTTP:{PC_HTTP_PORT})")
    logging.info(f"Camera: {CAMERA_NAME} ({CAMERA_IP}:{CAMERA_PORT})")
    logging.info(f"Anti-flap: {ANTI_FLAP_TIME}s")
    logging.info("=" * 70)

    # Check for existing instance
    if not create_pid_file():
        logging.error("Exiting due to existing instance")
        sys.exit(2)  # Exit code 2: already running

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Create controller
        controller = MultiDeviceController()

        # Initialize system
        if not controller.initialize():
            logging.error("Initialization failed")
            logging.error(f"Waiting {RETRY_DELAY_ON_INIT_FAIL}s before supervisor restart...")
            remove_pid_file()
            time.sleep(RETRY_DELAY_ON_INIT_FAIL)  # Delay to prevent rapid restart loop
            sys.exit(1)  # Exit code 1: initialization error

        # Start main loop
        logging.info("Entering main loop (supervisor will restart on exit)")
        controller.run()

        # Normal exit (should not reach here unless stopped by signal)
        remove_pid_file()
        sys.exit(0)  # Exit code 0: clean exit

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received")
        if controller:
            controller.shutdown()
        remove_pid_file()
        sys.exit(0)

    except Exception as e:
        logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        logging.critical(f"Waiting {RETRY_DELAY_ON_INIT_FAIL}s before supervisor restart...")
        if controller:
            try:
                controller.shutdown()
            except:
                pass
        remove_pid_file()
        time.sleep(RETRY_DELAY_ON_INIT_FAIL)  # Delay to prevent rapid restart loop
        sys.exit(1)  # Exit code 1: fatal error

if __name__ == "__main__":
    main()
