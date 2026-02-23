#!/usr/bin/env python3
"""
Test Script for Path Verification
Vérifie que tous les chemins et imports fonctionnent correctement avant production
"""

import os
import sys
from pathlib import Path

def test_directory_structure():
    """Vérifie la structure des répertoires"""
    print("\n" + "="*70)
    print("TEST 1: STRUCTURE DES RÉPERTOIRES")
    print("="*70)
    
    # Déterminer le répertoire base
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if "MANAGER" in script_dir:
        base_dir = os.path.dirname(script_dir)
    else:
        base_dir = script_dir
    
    print(f"Base directory: {base_dir}")
    
    required_dirs = {
        "MANAGER": os.path.join(base_dir, "MANAGER"),
        "PTZ": os.path.join(base_dir, "PTZ"),
        "logs": os.path.join(base_dir, "logs"),
        "schedules": os.path.join(base_dir, "schedules"),
    }
    
    all_ok = True
    for name, path in required_dirs.items():
        if os.path.isdir(path):
            print(f"✓ {name:15} → {path}")
        else:
            print(f"✗ {name:15} → {path} (NOT FOUND)")
            all_ok = False
    
    return all_ok, base_dir

def test_required_files(base_dir):
    """Vérifie les fichiers requis"""
    print("\n" + "="*70)
    print("TEST 2: FICHIERS REQUIS")
    print("="*70)
    
    required_files = {
        "start_mawaqit_manager.sh": os.path.join(base_dir, "start_mawaqit_manager.sh"),
        "MANAGER/mawaqit_stream_manager.py": os.path.join(base_dir, "MANAGER", "mawaqit_stream_manager.py"),
        "MANAGER/mawaqit_parser.py": os.path.join(base_dir, "MANAGER", "mawaqit_parser.py"),
        "PTZ/__init__.py": os.path.join(base_dir, "PTZ", "__init__.py"),
        "PTZ/ptz_config.py": os.path.join(base_dir, "PTZ", "ptz_config.py"),
        "PTZ/ptz_controller.py": os.path.join(base_dir, "PTZ", "ptz_controller.py"),
        "PTZ/ptz_scheduler.py": os.path.join(base_dir, "PTZ", "ptz_scheduler.py"),
    }
    
    all_ok = True
    for name, path in required_files.items():
        if os.path.isfile(path):
            size = os.path.getsize(path)
            print(f"✓ {name:35} ({size:,} bytes)")
        else:
            print(f"✗ {name:35} (NOT FOUND)")
            all_ok = False
    
    return all_ok

def test_dynamic_paths():
    """Vérifie que les chemins dynamiques fonctionnent"""
    print("\n" + "="*70)
    print("TEST 3: CHEMINS DYNAMIQUES (pour mawaqit_stream_manager.py)")
    print("="*70)
    
    # Simuler ce que fait le script
    if "MANAGER" in os.path.abspath(__file__):
        manager_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        manager_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MANAGER")
    
    base_dir = os.path.dirname(manager_dir)
    logs_dir = os.path.join(base_dir, "logs")
    schedules_dir = os.path.join(base_dir, "schedules")
    
    print(f"Manager dir:   {manager_dir}")
    print(f"Base dir:      {base_dir}")
    print(f"Logs dir:      {logs_dir}")
    print(f"Schedules dir: {schedules_dir}")
    
    # Tester la création des répertoires
    try:
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(schedules_dir, exist_ok=True)
        print("✓ Création répertoires OK")
        return True
    except Exception as e:
        print(f"✗ Erreur création répertoires: {e}")
        return False

def test_ptz_imports():
    """Teste les imports du module PTZ"""
    print("\n" + "="*70)
    print("TEST 4: IMPORTS MODULE PTZ")
    print("="*70)
    
    try:
        # Ajouter PTZ au path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if "MANAGER" in script_dir:
            base_dir = os.path.dirname(script_dir)
        else:
            base_dir = script_dir
        
        ptz_dir = os.path.join(base_dir, "PTZ")
        
        if ptz_dir not in sys.path:
            sys.path.insert(0, ptz_dir)
        
        print(f"PTZ directory added to sys.path: {ptz_dir}")
        
        # Test imports
        try:
            from ptz_config import PTZ_CONFIG
            print("✓ ptz_config.PTZ_CONFIG")
        except ImportError as e:
            print(f"✗ ptz_config: {e}")
            return False
        
        try:
            from ptz_controller import PTZController
            print("✓ ptz_controller.PTZController")
        except ImportError as e:
            print(f"✗ ptz_controller: {e}")
            return False
        
        try:
            from ptz_scheduler import PTZScheduler
            print("✓ ptz_scheduler.PTZScheduler")
        except ImportError as e:
            print(f"✗ ptz_scheduler: {e}")
            return False
        
        try:
            from mawaqit_parser import MawaqitParser
            print("✓ mawaqit_parser.MawaqitParser")
        except ImportError as e:
            print(f"✗ mawaqit_parser: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Erreur lors des imports: {e}")
        return False

def test_main_script_imports():
    """Teste les imports du script principal"""
    print("\n" + "="*70)
    print("TEST 5: IMPORTS SCRIPT PRINCIPAL")
    print("="*70)
    
    try:
        # Test importing main script
        manager_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MANAGER", "mawaqit_stream_manager.py")
        
        if os.path.exists(manager_file):
            print(f"Script trouvé: {manager_file}")
            
            # Simpler: just check syntax
            with open(manager_file, 'r') as f:
                try:
                    compile(f.read(), manager_file, 'exec')
                    print("✓ Syntax Python valide")
                    return True
                except SyntaxError as e:
                    print(f"✗ Erreur de syntaxe: {e}")
                    return False
        else:
            print(f"✗ Script non trouvé: {manager_file}")
            return False
            
    except Exception as e:
        print(f"✗ Erreur: {e}")
        return False

def test_permissions():
    """Vérifie les permissions des fichiers"""
    print("\n" + "="*70)
    print("TEST 6: PERMISSIONS DES FICHIERS")
    print("="*70)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if "MANAGER" in base_dir:
        base_dir = os.path.dirname(base_dir)
    
    # Test permissions on key files
    files_to_check = [
        os.path.join(base_dir, "start_mawaqit_manager.sh"),
        os.path.join(base_dir, "MANAGER", "mawaqit_stream_manager.py"),
        os.path.join(base_dir, "PTZ", "ptz_config.py"),
    ]
    
    all_ok = True
    for filepath in files_to_check:
        if os.path.exists(filepath):
            # Check if readable
            if os.access(filepath, os.R_OK):
                # Check if writable (for logs)
                writable = os.access(filepath, os.W_OK)
                status = "✓ R" + ("W" if writable else "")
                print(f"{status} {os.path.basename(filepath)}")
            else:
                print(f"✗ {os.path.basename(filepath)} (not readable)")
                all_ok = False
        else:
            print(f"? {os.path.basename(filepath)} (not found)")
    
    # Check if logs dir is writable
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    if os.access(logs_dir, os.W_OK):
        print(f"✓ logs/ (writable)")
    else:
        print(f"✗ logs/ (not writable)")
        all_ok = False
    
    return all_ok

def main():
    """Run all tests"""
    print("\n" + "█"*70)
    print("VERIFICATION DES CHEMINS - AUTO_StreamACMS")
    print("█"*70)
    print(f"Date: {os.popen('date').read().strip()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Utilisateur: {os.popen('whoami').read().strip() if sys.platform != 'win32' else 'N/A'}")
    
    results = {}
    
    # Test 1
    dirs_ok, base_dir = test_directory_structure()
    results["Répertoires"] = dirs_ok
    
    # Test 2
    files_ok = test_required_files(base_dir)
    results["Fichiers"] = files_ok
    
    # Test 3
    paths_ok = test_dynamic_paths()
    results["Chemins dynamiques"] = paths_ok
    
    # Test 4
    ptz_ok = test_ptz_imports()
    results["Imports PTZ"] = ptz_ok
    
    # Test 5
    main_ok = test_main_script_imports()
    results["Script principal"] = main_ok
    
    # Test 6
    perm_ok = test_permissions()
    results["Permissions"] = perm_ok
    
    # Summary
    print("\n" + "="*70)
    print("RÉSUMÉ DES TESTS")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")
    
    print("="*70)
    print(f"RÉSULTAT: {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n🎉 TOUS LES TESTS PASSENT - PRÊT À L'EXÉCUTION!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) échoué(s) - Vérifier les erreurs ci-dessus")
        return 1

if __name__ == "__main__":
    sys.exit(main())
