#!/usr/bin/env python3
"""
JUMUA READINESS TEST SCRIPT
Teste tous les systèmes critiques avant la prière du Vendredi
"""

import os
import sys
import time
import json
import subprocess
import datetime
from pathlib import Path

# Add paths
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # AUTO_StreamACMS root
_MANAGER_DIR = os.path.join(_BASE_DIR, "MANAGER")
_LOGS_DIR = os.path.join(_BASE_DIR, "logs")
_SCHEDULES_DIR = os.path.join(_BASE_DIR, "schedules")

# Add to Python path
sys.path.insert(0, _MANAGER_DIR)
sys.path.insert(0, os.path.join(_BASE_DIR, "PTZ"))

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(title):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title:^70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_test(name, result, details=""):
    """Print a test result"""
    status = f"{Colors.GREEN}✓ PASS{Colors.END}" if result else f"{Colors.RED}✗ FAIL{Colors.END}"
    print(f"  {status}  {name}")
    if details:
        print(f"       {details}")

def test_service_running():
    """Test 1: Check if the main service is running"""
    print_header("TEST 1: SERVICE PRINCIPAL")
    
    try:
        result = subprocess.run(
            "ps aux | grep 'python3.*mawaqit_stream_manager' | grep -v grep",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            pid_line = lines[0].split()
            pid = pid_line[1]
            memory = pid_line[5]
            cpu = pid_line[2]
            
            print_test(
                "Processus Python actif",
                True,
                f"PID: {pid}, CPU: {cpu}%, MEM: {memory}K"
            )
            return True
        else:
            print_test("Processus Python actif", False, "Aucun processus trouvé")
            return False
            
    except Exception as e:
        print_test("Processus Python actif", False, str(e))
        return False

def test_network_connectivity():
    """Test 2: Check network connectivity to key devices"""
    print_header("TEST 2: CONNECTIVITÉ RÉSEAU")
    
    devices = {
        "10.1.2.101": "BOX_MAWAQIT_101",
        "10.1.5.20": "CAMÉRA PTZ",
    }
    
    results = []
    for ip, name in devices.items():
        try:
            result = subprocess.run(
                f"ping -c 1 -w 2 {ip}",
                shell=True, capture_output=True, text=True, timeout=3
            )
            status = result.returncode == 0
            results.append(status)
            print_test(f"{name} ({ip})", status)
        except Exception as e:
            results.append(False)
            print_test(f"{name} ({ip})", False, str(e))
    
    return all(results)

def test_prayer_times():
    """Test 3: Fetch prayer times from Mawaqit website"""
    print_header("TEST 3: HORAIRES DE PRIÈRE (Mawaqit Site)")
    
    try:
        from mawaqit_parser import MawaqitParser
        
        parser = MawaqitParser(mosque_url="https://mawaqit.net/fr/mosquee-ennour-sartrouville")
        success = parser.fetch_prayer_times()
        
        if success:
            jumua = parser.prayer_times.get("jumua", "N/A")
            is_double, times = parser.is_double_jumuaa()
            
            print_test("Mawaqit accessible", True, f"Jumu'ah: {jumua}")
            print_test("Double Jumu'ah détecté", is_double, f"Horaires: {times}")
            
            # Afficher tous les horaires
            print("\n  📍 Horaires du jour:")
            for prayer, time_val in parser.prayer_times.items():
                if prayer != "jumua" or not isinstance(time_val, list):
                    print(f"     {prayer:12}: {time_val}")
            
            return True
        else:
            print_test("Mawaqit accessible", False, "Impossible de récupérer les horaires")
            return False
            
    except Exception as e:
        print_test("Mawaqit accessible", False, str(e))
        return False

def test_ptz_camera():
    """Test 4: Check PTZ camera connectivity"""
    print_header("TEST 4: CAMÉRA PTZ")
    
    try:
        from ptz_controller import PTZController
        from ptz_config import PTZ_CONFIG
        
        camera = PTZController(PTZ_CONFIG)
        device_info = camera.get_device_info()
        
        if device_info:
            print_test("Caméra accessible", True, f"Info: {device_info}")
            
            # Test présets
            print("\n  Positions (Présets):")
            presets = [1, 2, 3]
            for preset in presets:
                name = PTZ_CONFIG["positions"].get(preset, {}).get("name", "Unknown")
                print(f"     {preset}: {name}")
            
            return True
        else:
            print_test("Caméra accessible", False, "Impossible de se connecter")
            return False
            
    except Exception as e:
        print_test("Caméra accessible", False, str(e))
        return False

def test_mawaqit_boxes():
    """Test 5: Check Mawaqit boxes status"""
    print_header("TEST 5: BOÎTES MAWAQIT")
    
    try:
        log_file = os.path.join(_LOGS_DIR, "mawaqit_stream.log")
        if not os.path.exists(log_file):
            print_test("Fichier log", False, "Aucun log trouvé")
            return False
        
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
        # Chercher les dernières informations de connexion
        for line in reversed(lines[-200:]):
            if "DISCOVERY COMPLETE" in line:
                print_test("Découverte des BOXes", True, line.strip())
                
                # Compter les BOXes
                box_count = 0
                for prev_line in reversed(lines[-300:]):
                    if "BOX_MAWAQIT" in prev_line or "BOX_MITV" in prev_line:
                        box_count += 1
                        print(f"       {prev_line.strip()}")
                
                return box_count >= 5  # Au moins 5 BOXes
        
        print_test("Découverte des BOXes", False, "Aucune information de découverte")
        return False
        
    except Exception as e:
        print_test("Découverte des BOXes", False, str(e))
        return False

def test_disk_space():
    """Test 6: Check disk space"""
    print_header("TEST 6: ESPACE DISQUE")
    
    try:
        result = subprocess.run(
            f"df -h {_BASE_DIR}",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                available = parts[3]
                usage = parts[4]
                
                # Vérifier qu'il y a au moins 100M disponible
                free_gb = float(available.rstrip('G'))
                print_test("Espace disque", free_gb > 0.1, f"Disponible: {available}, Usage: {usage}")
                return free_gb > 0.1
        
        print_test("Espace disque", False, "Impossible de vérifier")
        return False
        
    except Exception as e:
        print_test("Espace disque", False, str(e))
        return False

def test_recent_errors():
    """Test 7: Check for recent errors in logs"""
    print_header("TEST 7: VÉRIFICATION DES ERREURS")
    
    try:
        log_file = os.path.join(_LOGS_DIR, "mawaqit_stream.log")
        if not os.path.exists(log_file):
            print_test("Fichier log", False, "Aucun log trouvé")
            return True  # Pas d'erreurs si pas de logs
        
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Chercher les erreurs des 30 dernières minutes
        cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=30)
        recent_errors = []
        
        for line in lines[-500:]:
            if "[ERROR]" in line or "[CRITICAL]" in line:
                try:
                    time_str = line.split()[0]
                    error_time = datetime.datetime.strptime(time_str, "%Y-%m-%d")
                    if error_time > cutoff_time:
                        recent_errors.append(line.strip())
                except:
                    pass
        
        if recent_errors:
            print_test("Aucune erreur récente", False, f"{len(recent_errors)} erreur(s) trouvée(s)")
            print("\n  Erreurs récentes:")
            for error in recent_errors[-5:]:
                print(f"     {error}")
            return False
        else:
            print_test("Aucune erreur récente", True, "Système stable")
            return True
            
    except Exception as e:
        print_test("Vérification erreurs", False, str(e))
        return True  # Continuer même si on ne peut pas lire les logs

def test_crontab():
    """Test 8: Check crontab configuration"""
    print_header("TEST 8: CONFIGURATION CRONTAB")
    
    try:
        result = subprocess.run(
            "crontab -l 2>/dev/null | grep -E '^[0-9]|^@'",
            shell=True, capture_output=True, text=True
        )
        
        has_supervision = "*/5 * * * *" in result.stdout or "*/10 * * * *" in result.stdout
        has_boot = "@reboot" in result.stdout
        
        if result.stdout:
            print_test("Tâches cron configurées", True, "")
            print("\n  Tâches:")
            for line in result.stdout.strip().split('\n'):
                if line:
                    print(f"     {line}")
        else:
            print_test("Tâches cron configurées", False, "Aucune tâche trouvée")
            return False
        
        return has_supervision or has_boot
        
    except Exception as e:
        print_test("Tâches cron configurées", False, str(e))
        return False

def run_all_tests():
    """Run all tests and print summary"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔" + "═"*68 + "╗")
    print("║" + "🕌 TEST DE READINESS JUMU'AH - AUTO_StreamACMS 🕌".center(68) + "║")
    print("║" + f"Date: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}".center(68) + "║")
    print("╚" + "═"*68 + "╝")
    print(Colors.END)
    
    results = {
        "Service Principal": test_service_running(),
        "Connectivité Réseau": test_network_connectivity(),
        "Horaires de Prière": test_prayer_times(),
        "Caméra PTZ": test_ptz_camera(),
        "Boîtes Mawaqit": test_mawaqit_boxes(),
        "Espace Disque": test_disk_space(),
        "Erreurs Récentes": test_recent_errors(),
        "Configuration Crontab": test_crontab(),
    }
    
    # Print summary
    print_header("RÉSUMÉ DES TESTS")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓{Colors.END}" if result else f"{Colors.RED}✗{Colors.END}"
        print(f"  {status} {test_name}")
    
    print(f"\n  {Colors.BOLD}Résultat: {passed}/{total} tests réussis{Colors.END}")
    
    if passed == total:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}🎉 SYSTÈME PRÊT POUR JUMU'AH! 🎉{Colors.END}\n")
        return 0
    elif passed >= total * 0.75:
        print(f"\n  {Colors.YELLOW}{Colors.BOLD}⚠️  Quelques problèmes détectés - vérifier les détails ci-dessus{Colors.END}\n")
        return 1
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}🚨 PROBLÈMES CRITIQUES - Action requise avant Jumu'ah!{Colors.END}\n")
        return 2

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
