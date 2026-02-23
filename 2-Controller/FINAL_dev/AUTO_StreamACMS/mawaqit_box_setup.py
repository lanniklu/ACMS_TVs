#!/usr/bin/env python3
"""
New MAWAQIT BOX Initialization Script
Automatically configures a newly purchased box for the ACMS system

Automatic steps:
1. Box detection on VLAN 2 network
2. USB debugging / ADB activation
3. Installation of required applications (VLC for HTTP, Onvif Viewer for cameras)
4. Network configuration (static IP)
5. Android settings (screen rotation, sleep, etc.)

ACMS Configuration:
- Network: VLAN 2 (10.1.2.0/24)
- Gateway: 10.1.2.1
- DNS: 10.1.2.1
"""

import subprocess
import time
import logging
import socket
import sys
import uuid
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

# ============================================================================
# CONFIGURATION PARAMETERS
# ============================================================================

# MAWAQIT Network (VLAN 2)
MAWAQIT_NETWORK = "10.1.2.0/24"
MAWAQIT_SCAN_START = 101     # First IP to scan (10.1.2.101)
MAWAQIT_SCAN_END = 112       # Last IP to scan (10.1.2.112) - 12 boxes planned
MAWAQIT_GATEWAY = "10.1.2.1"
MAWAQIT_DNS = "10.1.2.1"
# ADB Port
ADB_PORT = 5555

# Timeouts
TIMEOUT_SCAN = 2
TIMEOUT_CONNECT = 10
TIMEOUT_COMMAND = 30

# APKs to install (local paths on Raspberry Pi)
# APK_MAWAQIT - Not needed, pre-installed on boxes
APK_VLC = "/home/acms_tech/AUTO_StreamACMS/apks/vlc.apk"
APK_ONVIF_VIEWER = "/home/acms_tech/AUTO_StreamACMS/apks/onvifer.apk"

# Android parameters
SCREEN_ROTATION = 0  # 0=0deg, 1=90deg, 2=180deg, 3=270deg
SCREEN_TIMEOUT = 0   # 0=never (for TV)
BRIGHTNESS = 255     # 0-255 (max)

# Logging
LOG_FILE = "/home/acms_tech/AUTO_StreamACMS/logs/box_setup.log"
LOG_LEVEL = logging.INFO

# Camera IMAM configuration (for Onvifer auto-config)
CAMERA_IMAM_IP = "10.1.5.20"
CAMERA_IMAM_USERNAME = "admin"
CAMERA_IMAM_PASSWORD = "Frsbd2013"
CAMERA_IMAM_NAME = "IMAM"
CAMERA_IMAM_MODEL = "SF-IPDM855ZH-2"

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class BoxConfig:
    """Box configuration"""
    ip: str
    port: int = 5555
    model: str = ""
    android_version: str = ""
    
    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """Formatter with colors for console"""

    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
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

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

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
# NETWORK SCANNER
# ============================================================================

class BoxScanner:
    """Scans network to find new boxes"""

    @staticmethod
    def check_adb_port(ip: str) -> bool:
        """Check if ADB port is open"""
        try:
            sock = socket.create_connection((ip, ADB_PORT), timeout=TIMEOUT_SCAN)
            sock.close()
            return True
        except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
            return False

    @staticmethod
    def scan_network() -> list:
        """Scan network to find Android boxes"""
        logging.info("Scanning VLAN 2 network to discover new boxes...")
        logging.info(f"Range: 10.1.2.{VLAN2_SCAN_START}-{VLAN2_SCAN_END}")
        
        found_boxes = []
        
        for i in range(VLAN2_SCAN_START, VLAN2_SCAN_END + 1):
            ip = f"10.1.2.{i}"
            if BoxScanner.check_adb_port(ip):
                logging.info(f"+ Box detected: {ip}")
                found_boxes.append(ip)
        
        logging.info(f"Scan complete: {len(found_boxes)} box(es) detected")
        return found_boxes

# ============================================================================
# ADB MANAGER
# ============================================================================

class ADBManager:
    """Manages ADB connections and commands"""

    @staticmethod
    def ensure_server_running() -> bool:
        """Start ADB server"""
        try:
            subprocess.run(
                ["adb", "start-server"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            return True
        except Exception as e:
            logging.error(f"ADB server start error: {e}")
            return False

    @staticmethod
    def connect(ip: str) -> bool:
        """Connect a box via ADB"""
        try:
            address = f"{ip}:{ADB_PORT}"
            logging.info(f"ADB connection to {address}...")
            
            result = subprocess.run(
                ["adb", "connect", address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_CONNECT
            )
            
            output = result.stdout.decode("utf-8")
            if "connected" in output.lower():
                logging.info(f"+ Connection successful")
                return True
            else:
                logging.error(f"- Connection failed: {output}")
                return False
                
        except Exception as e:
            logging.error(f"- Connection error: {e}")
            return False

    @staticmethod
    def execute(ip: str, command: list, timeout: int = TIMEOUT_COMMAND) -> Tuple[bool, str]:
        """Execute an ADB command"""
        try:
            address = f"{ip}:{ADB_PORT}"
            result = subprocess.run(
                ["adb", "-s", address, "shell"] + command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
            
            stdout = result.stdout.decode("utf-8").strip()
            return result.returncode == 0, stdout
            
        except Exception as e:
            logging.error(f"Command execution error: {e}")
            return False, ""

    @staticmethod
    def get_info(ip: str) -> Optional[BoxConfig]:
        """Retrieve box information"""
        try:
            address = f"{ip}:{ADB_PORT}"
            
            # Model
            success, model = ADBManager.execute(ip, ["getprop", "ro.product.model"])
            if not success:
                model = "Unknown"
            
            # Android version
            success, android_ver = ADBManager.execute(ip, ["getprop", "ro.build.version.release"])
            if not success:
                android_ver = "Unknown"
            
            return BoxConfig(
                ip=ip,
                model=model,
                android_version=android_ver
            )
            
        except Exception as e:
            logging.error(f"Info retrieval error: {e}")
            return None

# ============================================================================
# ONVIFER CONFIGURATOR
# ============================================================================

class OnviferConfigurator:
    """Configures Onvifer with camera IMAM"""

    @staticmethod
    def generate_device_xml(camera_ip: str, username: str, password: str, 
                           name: str, model: str) -> str:
        """Generate ListDevice.xml content for camera configuration"""
        device_uid = str(uuid.uuid4())
        
        xml_content = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<listDevice>
  <DeviceInfo>
    <sAddress>{camera_ip}</sAddress>
    <iPort>80</iPort>
    <sUserName>{username}</sUserName>
    <sPassword>{password}</sPassword>
    <sName>{name}</sName>
    <sModel>{model}</sModel>
    <deviceType>ONVIF</deviceType>
    <transportProtocol>HTTP</transportProtocol>
    <uid>{device_uid}</uid>
    <iChannel>1</iChannel>
    <iStream>0</iStream>
    <onvifPort>80</onvifPort>
    <httpPort>80</httpPort>
    <rtspPort>554</rtspPort>
    <rtmpPort>1935</rtmpPort>
    <isOnline>true</isOnline>
    <lastUpdateTime>{int(time.time() * 1000)}</lastUpdateTime>
  </DeviceInfo>
</listDevice>"""
        return xml_content

    @staticmethod
    def configure_camera(ip: str) -> bool:
        """Configure Onvifer with camera IMAM"""
        try:
            logging.info("Configuring Onvifer with camera IMAM...")
            
            # Generate XML configuration
            xml_content = OnviferConfigurator.generate_device_xml(
                CAMERA_IMAM_IP,
                CAMERA_IMAM_USERNAME,
                CAMERA_IMAM_PASSWORD,
                CAMERA_IMAM_NAME,
                CAMERA_IMAM_MODEL
            )
            
            # Create temp file on local system
            temp_xml = f"/tmp/onvifer_config_{ip.replace('.', '_')}.xml"
            with open(temp_xml, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            # Push to box in /data/local/tmp (world writable)
            address = f"{ip}:{ADB_PORT}"
            logging.info("Pushing configuration to box...")
            result = subprocess.run(
                ["adb", "-s", address, "push", temp_xml, "/data/local/tmp/ListDevice.xml"],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logging.error(f"Failed to push config: {result.stderr.decode()}")
                return False
            
            # Copy to Onvifer app directory using run-as
            logging.info("Installing configuration in Onvifer app...")
            
            # First, ensure directory exists
            ADBManager.execute(ip, [
                "run-as", "net.biyee.onvifer",
                "mkdir", "-p", "files"
            ])
            
            # Copy file from /data/local/tmp to app directory
            success, output = ADBManager.execute(ip, [
                "run-as", "net.biyee.onvifer",
                "cp", "/data/local/tmp/ListDevice.xml", "files/ListDevice.xml"
            ])
            
            if not success:
                logging.error(f"Failed to install config: {output}")
                return False
            
            # Set permissions
            ADBManager.execute(ip, [
                "run-as", "net.biyee.onvifer",
                "chmod", "644", "files/ListDevice.xml"
            ])
            
            # Cleanup temp files
            subprocess.run(["rm", "-f", temp_xml], capture_output=True)
            ADBManager.execute(ip, ["rm", "-f", "/data/local/tmp/ListDevice.xml"])
            
            logging.info("✓ Camera IMAM configured successfully in Onvifer")
            return True
            
        except Exception as e:
            logging.error(f"Onvifer configuration error: {e}")
            return False

# ============================================================================
# APP INSTALLER
# ============================================================================

class AppInstaller:
    """Installs required applications"""

    @staticmethod
    def is_installed(ip: str, package: str) -> bool:
        """Check if an app is installed"""
        success, output = ADBManager.execute(ip, ["pm", "list", "packages"])
        return success and package in output

    @staticmethod
    def install_apk(ip: str, apk_path: str, app_name: str) -> bool:
        """Install an APK"""
        try:
            address = f"{ip}:{ADB_PORT}"
            logging.info(f"Installing {app_name}...")
            
            # Download APK if it's a URL
            local_apk = apk_path
            if apk_path.startswith("http"):
                logging.info(f"Downloading from {apk_path}...")
                result = subprocess.run(
                    ["wget", "-O", f"/tmp/{app_name}.apk", apk_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120
                )
                if result.returncode != 0:
                    logging.error(f"Download error for {app_name}")
                    return False
                local_apk = f"/tmp/{app_name}.apk"
            
            # Install APK
            result = subprocess.run(
                ["adb", "-s", address, "install", "-r", local_apk],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_COMMAND
            )
            
            if result.returncode == 0:
                logging.info(f"+ {app_name} installed")
                return True
            else:
                logging.error(f"- Installation failed for {app_name}")
                return False
                
        except Exception as e:
            logging.error(f"Installation error for {app_name}: {e}")
            return False

    @staticmethod
    def install_all(ip: str) -> bool:
        """Install all required applications"""
        logging.info("=" * 70)
        logging.info("INSTALLING APPLICATIONS")
        logging.info("=" * 70)
        
        success = True
        
        # Mawaqit - Pre-installed on boxes
        if AppInstaller.is_installed(ip, "com.mawaqit.androidtv"):
            logging.info("+ Mawaqit already installed (pre-installed on box)")
        else:
            logging.warning("! Mawaqit not detected - should be pre-installed")
        
        # VLC
        if not AppInstaller.is_installed(ip, "org.videolan.vlc"):
            if not AppInstaller.install_apk(ip, APK_VLC, "VLC"):
                success = False
        else:
            logging.info("VLC already installed")
        
        # Onvif Viewer
        onvifer_already_installed = AppInstaller.is_installed(ip, "net.biyee.onvifer")
        if not onvifer_already_installed:
            if not AppInstaller.install_apk(ip, APK_ONVIF_VIEWER, "Onvif-Viewer"):
                success = False
            else:
                # Configure camera after installation
                if not OnviferConfigurator.configure_camera(ip):
                    logging.warning("! Onvifer installed but camera configuration failed")
        else:
            logging.info("Onvif Viewer already installed")
            # Try to configure camera even if already installed (in case config was lost)
            if not OnviferConfigurator.configure_camera(ip):
                logging.warning("! Camera configuration update failed")
        
        logging.info("=" * 70)
        return success

# ============================================================================
# SYSTEM CONFIGURATOR
# ============================================================================

class SystemConfigurator:
    """Configures box system settings"""

    @staticmethod
    def configure_network(ip: str, static_ip: str) -> bool:
        """Configure static IP (requires root or manual configuration)"""
        logging.info(f"Configuring static IP: {static_ip}")
        logging.warning("Static IP configuration requires root access")
        logging.warning(f"Please manually configure IP {static_ip}")
        logging.warning(f"Gateway: {VLAN2_GATEWAY}")
        logging.warning(f"DNS: {VLAN2_DNS}")
        return True

    @staticmethod
    def configure_screen(ip: str) -> bool:
        """Configure screen (rotation, brightness, sleep)"""
        logging.info("Configuring screen...")
        
        # Rotation
        success, _ = ADBManager.execute(ip, [
            "settings", "put", "system", "user_rotation", str(SCREEN_ROTATION)
        ])
        if success:
            logging.info(f"+ Rotation: {SCREEN_ROTATION}")
        
        # Screen timeout (0 = never)
        success, _ = ADBManager.execute(ip, [
            "settings", "put", "system", "screen_off_timeout", str(SCREEN_TIMEOUT)
        ])
        if success:
            logging.info(f"+ Screen timeout: {SCREEN_TIMEOUT}")
        
        # Brightness
        success, _ = ADBManager.execute(ip, [
            "settings", "put", "system", "screen_brightness", str(BRIGHTNESS)
        ])
        if success:
            logging.info(f"+ Brightness: {BRIGHTNESS}")
        
        return True

    @staticmethod
    def configure_android(ip: str) -> bool:
        """Configure Android settings"""
        logging.info("Configuring Android settings...")
        
        # Disable automatic updates
        ADBManager.execute(ip, [
            "settings", "put", "global", "auto_update_mode", "0"
        ])
        
        # Keep screen on while charging
        ADBManager.execute(ip, [
            "settings", "put", "global", "stay_on_while_plugged_in", "7"
        ])
        
        logging.info("+ Android settings configured")
        return True

# ============================================================================
# COMPLETE INITIALIZATION
# ============================================================================

class BoxInitializer:
    """Completely initializes a new box"""

    @staticmethod
    def initialize_box(ip: str, static_ip: Optional[str] = None) -> bool:
        """Initialize a complete box"""
        logging.info("=" * 70)
        logging.info(f"BOX INITIALIZATION {ip}")
        logging.info("=" * 70)
        
        # Connection
        if not ADBManager.connect(ip):
            logging.error("Unable to connect to box")
            return False
        
        # Retrieve info
        box_info = ADBManager.get_info(ip)
        if box_info:
            logging.info(f"Model: {box_info.model}")
            logging.info(f"Android: {box_info.android_version}")
        
        # Application installation
        if not AppInstaller.install_all(ip):
            logging.warning("Some applications were not installed")
        
        # System configuration
        SystemConfigurator.configure_screen(ip)
        SystemConfigurator.configure_android(ip)
        
        # Network configuration
        if static_ip:
            SystemConfigurator.configure_network(ip, static_ip)
        
        logging.info("=" * 70)
        logging.info("INITIALIZATION COMPLETE")
        logging.info("=" * 70)
        logging.info("Box is ready to be used with mawaqit_stream_manager.py")
        
        return True

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main function"""
    setup_logging()
    
    logging.info("=" * 70)
    logging.info("BOX_MAWAQIT INITIALIZATION - ACMS")
    logging.info("=" * 70)
    logging.info(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 70)
    
    # Start ADB server
    if not ADBManager.ensure_server_running():
        logging.error("Unable to start ADB server")
        sys.exit(1)
    
    # Scan network
    found_boxes = BoxScanner.scan_network()
    
    if not found_boxes:
        logging.error("No box detected on network")
        logging.error("Verify that:")
        logging.error("  1. Box is powered on")
        logging.error("  2. Box is connected to VLAN 2")
        logging.error("  3. ADB is enabled (Settings > Developer options)")
        sys.exit(1)
    
    # If multiple boxes, ask which one to initialize
    if len(found_boxes) > 1:
        logging.info(f"Multiple boxes detected: {', '.join(found_boxes)}")
        ip_to_init = input("Enter IP of box to initialize: ").strip()
        if ip_to_init not in found_boxes:
            logging.error("Invalid IP")
            sys.exit(1)
    else:
        ip_to_init = found_boxes[0]
    
    # Ask for desired static IP
    static_ip = input(f"Desired static IP (e.g., 10.1.2.101) [Enter for DHCP]: ").strip()
    if not static_ip:
        static_ip = None
    
    # Initialize box
    if BoxInitializer.initialize_box(ip_to_init, static_ip):
        logging.info("Success! Box is ready.")
    else:
        logging.error("Initialization failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
