from flask import Flask, request
import requests
import threading
import time

# Configuration
CAMERA_IP = "10.1.5.20"
CAMERA_USER = "admin"
CAMERA_PASSWORD = "CAMERA_PASSWORD_REDACTED"  # À remplacer
PRESETS = [1, 2, 3, 4, 5]  # Liste des positions PTZ
DEBOUNCE_DELAY = 2.0  # secondes

app = Flask(__name__)
current_index = 0
last_press_time = 0
lock = threading.Lock()

def goto_preset(preset):
    url = f"http://{CAMERA_IP}/ISAPI/PTZCtrl/channels/1/presets/{preset}/goto"
    try:
        response = requests.put(url, auth=(CAMERA_USER, CAMERA_PASSWORD), timeout=5)
        print(f"Preset {preset}: {response.status_code}")
    except Exception as e:
        print(f"Erreur lors de l'envoi de la commande PTZ: {e}")

@app.route("/button", methods=["GET", "POST"])
def button_press():
    global current_index, last_press_time
    with lock:
        now = time.time()
        if now - last_press_time < DEBOUNCE_DELAY:
            return ("Ignored (debounce)", 200)
        last_press_time = now
        current_index = (current_index + 1) % len(PRESETS)
        preset = PRESETS[current_index]
        threading.Thread(target=goto_preset, args=(preset,)).start()
        print(f"Bouton appuyé, position {preset}")
    return (f"PTZ preset {preset}", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
