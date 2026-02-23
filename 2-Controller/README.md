# ACMS - AUTO Stream Manager

Système automatisé de gestion des box MAWAQIT pour l'affichage dynamique.

## 📁 Structure

```
AUTO_StreamACMS/
├── apks/                          # APK des applications à installer
│   ├── vlc.apk                    # VLC pour flux HTTP
│   └── onvifer.apk                # Onvifer pour caméras ONVIF
├── logs/                          # Logs d'exécution (créés automatiquement)
├── mawaqit_box_setup.py           # Script de configuration des box neuves
├── mawaqit_stream_manager.py      # Gestionnaire de flux automatique
├── start_mawaqit_manager.sh       # Script superviseur avec auto-restart
├── install.sh                     # Installation et configuration système
└── README.md                      # Ce fichier
```

## 🚀 Installation Rapide (1 commande)

### 1. Copier depuis Windows vers Raspberry Pi

```powershell
scp -r C:\Users\g565799\Desktop\ACMS\AUTO_StreamACMS acms_tech@10.1.5.10:/home/acms_tech/
```

### 2. Installer sur Raspberry Pi

```bash
cd /home/acms_tech/AUTO_StreamACMS
sudo bash install.sh
```

**C'EST TOUT !** Le système est installé et configuré pour démarrage automatique.

---

## 📦 Configuration d'une box MAWAQIT neuve

### Prérequis sur la box
1. Brancher sur **Switch E port 37** (VLAN 2)
2. Activer mode développeur (7x sur "Build number")
3. Activer **ADB réseau** dans Options développeur
4. Configurer IP statique : `10.1.2.10X` / Gateway `10.1.2.1` / DNS `10.1.2.1`

### Lancer la configuration

```bash
cd /home/acms_tech/AUTO_StreamACMS
python3 mawaqit_box_setup.py
```

Le script va automatiquement :
- ✅ Scanner le réseau (10.1.2.101-112)
- ✅ Détecter la box
- ✅ Installer VLC et Onvifer
- ✅ **Configurer automatiquement la caméra IMAM dans Onvifer** (10.1.5.20, admin/Frsbd2013)
- ✅ Configurer l'écran (rotation, luminosité, veille)
- ✅ Optimiser Android pour usage 24/7

**Note** : La configuration Onvifer est entièrement automatisée - plus besoin de configurer la caméra manuellement via la télécommande TV !

---

## 🎯 Gestion automatique des flux

Le `mawaqit_stream_manager.py` gère automatiquement l'affichage selon les priorités :

1. **PC Diffusion** (10.1.4.250:8080) - HTTP via VLC
2. **Caméra IMAM** (10.1.5.20) - ONVIF via Onvifer
3. **Mawaqit** - Application par défaut

### Commandes utiles

```bash
# Voir le statut
ps aux | grep mawaqit

# Voir les logs
tail -f /home/acms_tech/AUTO_StreamACMS/logs/mawaqit_stream.log
tail -f /home/acms_tech/AUTO_StreamACMS/logs/supervisor.log

# Arrêter
pkill -f mawaqit_stream_manager.py

# Redémarrer (le superviseur relancera automatiquement)
# Ou reboot
```

---

## 🔧 Configuration réseau

- **Raspberry Pi** : 10.1.5.10 (VLAN 5)
- **PC Diffusion** : 10.1.4.250 (VLAN 4)
- **Box MAWAQIT** : 10.1.2.101-112 (VLAN 2)
- **Caméra IMAM** : 10.1.5.20 (VLAN 5)

---

## 📝 Logs

Tous les logs sont dans `/home/acms_tech/AUTO_StreamACMS/logs/` :
- `mawaqit_stream.log` - Activité du stream manager
- `box_setup.log` - Configuration des box
- `supervisor.log` - Supervision et redémarrages
- `mawaqit_stream_manager.pid` - PID du processus actif
- `mawaqit_heartbeat.txt` - Heartbeat du système

---

## 🆘 Dépannage

### Le stream manager ne démarre pas
```bash
cd /home/acms_tech/AUTO_StreamACMS
./start_mawaqit_manager.sh
```

### Vérifier les dépendances
```bash
which python3  # Doit être installé
which adb      # Doit être installé
```

### Réinstaller
```bash
cd /home/acms_tech/AUTO_StreamACMS
sudo bash install.sh
```

---

## ✅ Checklist post-installation

- [ ] `install.sh` exécuté avec succès
- [ ] Crontab configuré (`crontab -l` pour vérifier)
- [ ] APK présents dans `apks/` (vlc.apk, onvifer.apk)
- [ ] Stream manager démarre au reboot
- [ ] Box MAWAQIT détectées et configurées

---

**Auteur** : ACMS Tech Team  
**Version** : 1.0  
**Date** : Janvier 2026
