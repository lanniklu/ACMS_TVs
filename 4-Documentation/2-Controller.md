# 2. Controller (Raspberry Pi)

## Rôle
Le controller (Raspberry Pi) est le chef d’orchestre du système : il reçoit les commandes des boutons connectés et pilote les caméras motorisées (PTZ).

## Fonctionnement
- Un script Python (avec Flask) tourne en permanence sur la Raspberry Pi.
- À chaque appui sur un bouton connecté, la Raspberry Pi reçoit une requête et envoie la commande à la caméra pour changer de position.
- La liste des positions est prédéfinie dans le script.

## Installation
1. Installer Python 3 et Flask sur la Raspberry Pi.
2. Placer le script de contrôle dans le dossier dédié.
3. Lancer le script avec la commande : `python3 ptz_button_server.py`

## Maintenance
- Redémarrer la Raspberry Pi en cas de blocage.
- Vérifier les logs du script pour diagnostiquer un problème.
- S’assurer que la Raspberry Pi est bien connectée au réseau.
