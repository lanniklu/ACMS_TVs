#!/bin/bash
# Script de test des commandes ADB sur les boxes MAWAQIT
# À exécuter depuis le Raspberry Pi

echo "========================================================================"
echo "TEST DES COMMANDES ADB SUR LES BOXES MAWAQIT"
echo "========================================================================"
echo ""

# Couleurs pour la sortie
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BOX_103="10.1.2.103:5555"
BOX_115="10.1.2.115:5555"

echo -e "${YELLOW}[INFO]${NC} Connexion aux boxes..."
adb connect 10.1.2.103:5555
adb connect 10.1.2.115:5555
echo ""

sleep 2

# ===========================================================================
# TEST 1 - DÉTECTION APP COURANTE
# ===========================================================================
echo "========================================================================"
echo "TEST 1 - DÉTECTION DE L'APPLICATION AU PREMIER PLAN"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 1.1]${NC} Détection app sur BOX .103"
RESULT=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "Résultat: $RESULT"
echo ""

echo -e "${YELLOW}[TEST 1.2]${NC} Détection app sur BOX .115"
RESULT=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "Résultat: $RESULT"
echo ""

# ===========================================================================
# TEST 2 - LANCEMENT MAWAQIT
# ===========================================================================
echo "========================================================================"
echo "TEST 2 - LANCEMENT MAWAQIT (monkey)"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 2.1]${NC} Lancement MAWAQIT sur BOX .103"
adb -s $BOX_103 shell "monkey -p com.mawaqit.androidtv 1" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 3
RESULT=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
echo ""

echo -e "${YELLOW}[TEST 2.2]${NC} Lancement MAWAQIT sur BOX .115"
adb -s $BOX_115 shell "monkey -p com.mawaqit.androidtv 1" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 3
RESULT=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
echo ""

# ===========================================================================
# TEST 3 - FORCE STOP VLC
# ===========================================================================
echo "========================================================================"
echo "TEST 3 - FORCE STOP VLC"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 3.1]${NC} Force stop VLC sur BOX .103"
adb -s $BOX_103 shell "am force-stop org.videolan.vlc" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
echo ""

echo -e "${YELLOW}[TEST 3.2]${NC} Force stop VLC sur BOX .115"
adb -s $BOX_115 shell "am force-stop org.videolan.vlc" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
echo ""

# ===========================================================================
# TEST 4 - LANCEMENT VLC AVEC STREAM
# ===========================================================================
echo "========================================================================"
echo "TEST 4 - LANCEMENT VLC (HTTP STREAM)"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 4.1]${NC} Lancement VLC sur BOX .103"
adb -s $BOX_103 shell "am start -a android.intent.action.VIEW -d http://10.1.4.250:8080/stream -n org.videolan.vlc/.StartActivity --ei network-caching 300" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 5
echo "Attente 5 secondes pour que VLC démarre..."
RESULT=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
if [[ $RESULT == *"org.videolan.vlc"* ]]; then
    echo -e "${GREEN}✓ VLC est au premier plan${NC}"
else
    echo -e "${RED}✗ VLC n'est PAS au premier plan${NC}"
fi
echo ""

echo -e "${YELLOW}[TEST 4.2]${NC} Lancement VLC sur BOX .115"
adb -s $BOX_115 shell "am start -a android.intent.action.VIEW -d http://10.1.4.250:8080/stream -n org.videolan.vlc/.StartActivity --ei network-caching 300" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 5
echo "Attente 5 secondes pour que VLC démarre..."
RESULT=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
if [[ $RESULT == *"org.videolan.vlc"* ]]; then
    echo -e "${GREEN}✓ VLC est au premier plan${NC}"
else
    echo -e "${RED}✗ VLC n'est PAS au premier plan${NC}"
fi
echo ""

# ===========================================================================
# TEST 5 - FORCE STOP VLC ET RETOUR MAWAQIT
# ===========================================================================
echo "========================================================================"
echo "TEST 5 - FORCE STOP VLC ET RETOUR À MAWAQIT"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 5.1]${NC} Force stop VLC sur BOX .103"
adb -s $BOX_103 shell "am force-stop org.videolan.vlc" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 2
RESULT=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée après force stop: $RESULT"
echo ""

echo -e "${YELLOW}[TEST 5.2]${NC} Force stop VLC sur BOX .115"
adb -s $BOX_115 shell "am force-stop org.videolan.vlc" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 2
RESULT=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée après force stop: $RESULT"
echo ""

# ===========================================================================
# TEST 6 - LANCEMENT MAWAQIT (méthode am start)
# ===========================================================================
echo "========================================================================"
echo "TEST 6 - LANCEMENT MAWAQIT (am start)"
echo "========================================================================"
echo ""

echo -e "${YELLOW}[TEST 6.1]${NC} Lancement MAWAQIT sur BOX .103 (méthode am start)"
adb -s $BOX_103 shell "am start -n com.mawaqit.androidtv/.MainActivity" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 3
RESULT=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
if [[ $RESULT == *"com.mawaqit.androidtv"* ]]; then
    echo -e "${GREEN}✓ MAWAQIT est au premier plan${NC}"
else
    echo -e "${RED}✗ MAWAQIT n'est PAS au premier plan${NC}"
fi
echo ""

echo -e "${YELLOW}[TEST 6.2]${NC} Lancement MAWAQIT sur BOX .115 (méthode am start)"
adb -s $BOX_115 shell "am start -n com.mawaqit.androidtv/.MainActivity" 2>&1
echo -e "${GREEN}Commande envoyée${NC}"
sleep 3
RESULT=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "App détectée: $RESULT"
if [[ $RESULT == *"com.mawaqit.androidtv"* ]]; then
    echo -e "${GREEN}✓ MAWAQIT est au premier plan${NC}"
else
    echo -e "${RED}✗ MAWAQIT n'est PAS au premier plan${NC}"
fi
echo ""

# ===========================================================================
# RÉSUMÉ FINAL
# ===========================================================================
echo "========================================================================"
echo "RÉSUMÉ DES TESTS"
echo "========================================================================"
echo ""
echo "Toutes les commandes ont été testées sur les deux boxes."
echo "Si VLC n'est pas au premier plan après le lancement, cela signifie"
echo "que le stream n'est pas disponible ou que VLC ne peut pas le lire."
echo ""
echo "État final des boxes:"
echo ""
RESULT_103=$(adb -s $BOX_103 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
RESULT_115=$(adb -s $BOX_115 shell "dumpsys activity activities" 2>&1 | grep "mResumedActivity")
echo "BOX .103: $RESULT_103"
echo "BOX .115: $RESULT_115"
echo ""
echo "========================================================================"
echo "FIN DES TESTS"
echo "========================================================================"
