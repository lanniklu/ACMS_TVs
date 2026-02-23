# Configuration Automatique Onvifer - Documentation Technique

## Vue d'ensemble

La configuration automatique d'Onvifer permet de pré-configurer la caméra IMAM (10.1.5.20) sur chaque box MAWAQIT sans intervention manuelle via télécommande TV.

**Gain de temps** : ~5 minutes par box × 12 boxes = **1 heure économisée**

---

## Fonctionnement

### 1. Génération de la configuration XML

Le script `mawaqit_box_setup.py` génère automatiquement le fichier `ListDevice.xml` avec :
- **IP caméra** : 10.1.5.20
- **Credentials** : admin / CAMERA_PASSWORD_REDACTED
- **Modèle** : SF-IPDM855ZH-2
- **Protocole** : ONVIF sur HTTP
- **UID unique** : UUID généré pour chaque box
- **Ports** : HTTP 80, ONVIF 80, RTSP 554

### 2. Déploiement sur la box

Le script utilise ADB pour :
1. Créer le fichier XML en local (`/tmp/onvifer_config_*.xml`)
2. Le pousser vers la box (`/data/local/tmp/ListDevice.xml`)
3. Le copier dans le dossier de l'app Onvifer via `run-as`
4. Définir les permissions (644)
5. Nettoyer les fichiers temporaires

### 3. Intégration dans le workflow

La configuration Onvifer s'exécute automatiquement :
- **Après installation** de l'APK Onvifer (si première installation)
- **Même si déjà installé** (pour mettre à jour ou restaurer la config)

---

## Structure XML générée

```xml
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<listDevice>
  <DeviceInfo>
    <sAddress>10.1.5.20</sAddress>
    <iPort>80</iPort>
    <sUserName>admin</sUserName>
    <sPassword>CAMERA_PASSWORD_REDACTED</sPassword>
    <sName>IMAM</sName>
    <sModel>SF-IPDM855ZH-2</sModel>
    <deviceType>ONVIF</deviceType>
    <transportProtocol>HTTP</transportProtocol>
    <uid>[UUID généré]</uid>
    <iChannel>1</iChannel>
    <iStream>0</iStream>
    <onvifPort>80</onvifPort>
    <httpPort>80</httpPort>
    <rtspPort>554</rtspPort>
    <rtmpPort>1935</rtmpPort>
    <isOnline>true</isOnline>
    <lastUpdateTime>[timestamp]</lastUpdateTime>
  </DeviceInfo>
</listDevice>
```

---

## Chemin de configuration

**Sur la box Android** :
```
/data/data/net.biyee.onvifer/files/ListDevice.xml
```

**Permissions** : 644 (rw-r--r--)

---

## Validation

### Tester la génération XML (sans ADB)

```bash
cd /home/acms_tech/AUTO_StreamACMS
python3 test_onvifer_config.py
```

Affiche la configuration XML qui serait générée.

### Vérifier sur une box configurée

```bash
adb -s 10.1.2.104:5555 shell "run-as net.biyee.onvifer cat files/ListDevice.xml"
```

Devrait afficher la configuration de la caméra IMAM.

---

## Dépannage

### Erreur "run-as: Package 'net.biyee.onvifer' is not debuggable"

**Solution** : L'app doit être installée en mode debug. Réinstaller :
```bash
adb -s 10.1.2.10X:5555 install -r /home/acms_tech/AUTO_StreamACMS/apks/onvifer.apk
```

### Configuration non visible dans Onvifer

1. Vérifier que le fichier existe :
```bash
adb shell "run-as net.biyee.onvifer ls -la files/"
```

2. Forcer l'arrêt et redémarrer Onvifer :
```bash
adb shell "am force-stop net.biyee.onvifer"
adb shell "am start net.biyee.onvifer/.MainActivity"
```

### Caméra IMAM non accessible depuis VLAN 2

Vérifier les règles firewall MikroTik :
- FWD-200 : VLAN2 → 10.1.5.20 port 554 (RTSP) **accept**
- FWD-201 : VLAN2 → 10.1.5.20 port 80 (HTTP) **accept**
- FWD-202 : VLAN2 → 10.1.5.20 port 8899 (ONVIF) **accept**

---

## Modifications apportées

### Fichier : `mawaqit_box_setup.py`

**Lignes 1-25** : Ajout import `uuid` et `time`

**Lignes 57-62** : Constantes caméra IMAM
```python
CAMERA_IMAM_IP = "10.1.5.20"
CAMERA_IMAM_USERNAME = "admin"
CAMERA_IMAM_PASSWORD = "CAMERA_PASSWORD_REDACTED"
CAMERA_IMAM_NAME = "IMAM"
CAMERA_IMAM_MODEL = "SF-IPDM855ZH-2"
```

**Lignes 254-352** : Classe `OnviferConfigurator`
- `generate_device_xml()` : Génère le XML avec UUID unique
- `configure_camera()` : Déploie la config sur la box via ADB

**Lignes 437-452** : Intégration dans `AppInstaller.install_all()`
- Appel automatique après installation Onvifer
- Tentative même si Onvifer déjà installé

---

## Références

- **Extraction config originale** : Box 10.1.2.104 via `adb backup`
- **Source** : `/data/data/net.biyee.onvifer/files/ListDevice.xml`
- **Format** : XML Android standard (UTF-8, standalone)
- **Version Onvifer** : 21.17 (14.51 MB)

---

**Auteur** : ACMS Tech Team  
**Date** : Janvier 2026  
**Status** : ✅ Implémenté et testé
