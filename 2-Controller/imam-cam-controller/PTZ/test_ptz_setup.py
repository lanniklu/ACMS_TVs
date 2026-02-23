"""
Script de test et configuration initiale du système PTZ
"""

import os
import sys

# Ajoute le chemin du PTZ
ptz_dir = os.path.dirname(__file__)
sys.path.insert(0, ptz_dir)

from ptz_config import PTZ_CONFIG
from ptz_controller import PTZController
from mawaqit_parser import MawaqitParser
from ptz_scheduler import PTZScheduler


def test_camera_connection():
    """Teste la connexion à la caméra"""
    print("\n" + "="*60)
    print("🔍 TEST 1: Connexion à la caméra")
    print("="*60)
    
    ptz = PTZController(PTZ_CONFIG)
    info = ptz.get_device_info()
    
    if info:
        print("✓ Caméra connectée avec succès!")
        print(info[:200] + "..." if len(info) > 200 else info)
    else:
        print("✗ Impossible de se connecter à la caméra")
        print(f"  Vérifiez: {PTZ_CONFIG['camera']['ip']}")
        return False
    
    return True


def test_preset_movement(preset_id=1):
    """Teste le mouvement vers un preset"""
    print("\n" + "="*60)
    print(f"🎥 TEST 2: Mouvement vers preset {preset_id}")
    print("="*60)
    
    ptz = PTZController(PTZ_CONFIG)
    result = ptz.goto_preset(preset_id)
    
    if result:
        print(f"✓ Caméra positionnée au preset {preset_id}")
    else:
        print(f"✗ Erreur positionnement preset {preset_id}")
    
    return result


def test_mawaqit_parser():
    """Teste le parsing des horaires Mawaqit"""
    print("\n" + "="*60)
    print("🕌 TEST 3: Récupération horaires Mawaqit")
    print("="*60)
    
    parser = MawaqitParser()
    prayers = parser.fetch_prayer_times()
    
    if prayers:
        print("✓ Horaires récupérés avec succès!")
        for prayer, time in prayers.items():
            print(f"  {prayer.capitalize():12} : {time}")
        return True
    else:
        print("✗ Impossible de récupérer les horaires")
        return False


def test_schedule_creation():
    """Teste la création du planning"""
    print("\n" + "="*60)
    print("📅 TEST 4: Création du planning PTZ")
    print("="*60)
    
    ptz = PTZController(PTZ_CONFIG)
    parser = MawaqitParser()
    scheduler = PTZScheduler(ptz, parser, PTZ_CONFIG)
    
    result = scheduler.update_daily_schedule()
    
    if result:
        print("✓ Planning créé avec succès!")
    else:
        print("✗ Erreur création planning")
    
    return result


def main():
    print("\n" + "🚀 TESTS DE CONFIGURATION PTZ 🚀".center(60))
    print("="*60)
    
    # Affiche la configuration
    print(f"\n📡 Configuration:")
    print(f"   IP Caméra: {PTZ_CONFIG['camera']['ip']}")
    print(f"   Port: {PTZ_CONFIG['camera']['port']}")
    print(f"   User: {PTZ_CONFIG['camera']['username']}")
    
    # Lance les tests
    tests = [
        ("Connexion caméra", test_camera_connection),
        ("Mouvement preset", lambda: test_preset_movement(1)),
        ("Récupération horaires", test_mawaqit_parser),
        ("Création planning", test_schedule_creation),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n✗ ERREUR: {e}")
            results[test_name] = False
    
    # Résumé
    print("\n" + "="*60)
    print("📊 RÉSUMÉ DES TESTS")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:10} - {test_name}")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    print(f"\nTotal: {passed}/{total} tests réussis")
    
    print("\n" + "="*60)
    if passed == total:
        print("✓ Configuration OK - Système prêt!")
    else:
        print("✗ Erreurs détectées - Vérifiez la configuration")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
