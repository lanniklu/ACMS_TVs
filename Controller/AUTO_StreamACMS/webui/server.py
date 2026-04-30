#!/usr/bin/env python3
"""
ACMS WebUI - Interface web d'administration
Port 5050 - Accès local réseau uniquement

Fonctions :
  - Upload de la vidéo post-prière
  - Contrôle des presets caméra PTZ
  - Déclenchement manuel de la vidéo (play_order)

Accès : http://acms.tv:5050
"""

import os
import sys
import json
import hashlib
import secrets
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
from functools import wraps
from flask import (
    Flask, request, session, redirect, url_for,
    render_template_string, flash, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PTZ_DIR    = os.path.join(BASE_DIR, "PTZ")
MEDIA_DIR  = os.path.join(BASE_DIR, "media")
VIDEO_PATH = os.path.join(MEDIA_DIR, "video.mp4")
PLAY_ORDER_FILE     = os.path.join(MEDIA_DIR, "play_order.txt")
ONVIF_FORCE_FILE    = os.path.join(MEDIA_DIR, "onvif_force.txt")
BOXES_STATUS_FILE   = os.path.join(MEDIA_DIR, "boxes_status.json")
DISPLAY_OVERRIDE_FILE = os.path.join(MEDIA_DIR, "display_override.json")

sys.path.insert(0, PTZ_DIR)
from ptz_config import PTZ_CONFIG
from ptz_controller import PTZController

# ── Configuration ─────────────────────────────────────────────────────────────
PORT         = 5050
MAX_VIDEO_MB = 500

# Utilisateurs : code personnel → prénom affiché dans les logs
# Chaque utilisateur a un code à 4 chiffres unique
USERS = {
    "9393": "Hanni",
    "2524": "Younes",
    "3333": "Ziad",
    "0101": "Benachir",
    "0213": "Kamel",
    "0212": "Karim",
    "2500": "Hcen",
    "7777": "Ahmed",
}

LOG_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "webui_actions.log")
HTTP_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "http_access.log")

# Boxes Android TV (IP → nom affiché)
# KNOWN_NAMES : noms lisibles pour les IPs connues. Utilisé quand boxes_status.json est absent.
KNOWN_NAMES = {
    "10.1.2.101": "RDC AVANT",
    "10.1.2.103": "RDC MILIEU",
    "10.1.2.104": "ECRAN GEANT",
    "10.1.2.105": "Box 105",
    "10.1.2.106": "Box 106",
    "10.1.2.107": "Box 107",
    "10.1.2.109": "Box 109",
    "10.1.2.110": "Box 110",
    "10.1.2.111": "Box 111",
    "10.1.2.112": "Box 112",
    "10.1.2.113": "Box 113",
    "10.1.2.114": "Box 114",
    "10.1.2.115": "Box 115",
}

# Liste statique complète (fallback si boxes_status.json absent)
BOXES = [{"ip": ip, "name": name} for ip, name in KNOWN_NAMES.items()]

# IPs autorisées pour display/set (toute la plage possible 101-120)
_VALID_IP_RANGE = {f"10.1.2.{i}" for i in range(101, 121)}

ALLOWED_EXTENSIONS = {"mp4"}

app = Flask(__name__)
# Trust nginx reverse-proxy headers so logs keep the real client IP.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_MB * 1024 * 1024

# Persistent secret key: survive restarts without logging out users
_SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
try:
    with open(_SECRET_KEY_FILE, "r") as _f:
        app.secret_key = _f.read().strip()
except FileNotFoundError:
    app.secret_key = secrets.token_hex(32)
    with open(_SECRET_KEY_FILE, "w") as _f:
        _f.write(app.secret_key)

ptz = PTZController(PTZ_CONFIG)

# ── Sécurité ──────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def check_code(code: str):
    """Retourne le prénom si le code est valide, None sinon."""
    return USERS.get(code.strip())

def get_mac_from_ip(ip: str) -> str:
    """Cherche la MAC dans la table ARP du noyau Linux."""
    try:
        with open("/proc/net/arp") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    return parts[3]
    except Exception:
        pass
    return "inconnu"

def log_action(action: str):
    """Enregistre une action dans le journal : date | utilisateur | IP | MAC | action"""
    ip  = request.remote_addr or "?"
    mac = get_mac_from_ip(ip)
    who = session.get("username", "?")
    entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {who} | {ip} | {mac} | {action}\n"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
        with open(LOG_FILE, "a") as fh:
            fh.write(entry)
    except Exception as e:
        logging.warning("log_action failed: %s", e)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_mime(f) -> bool:
    """Vérifie les premiers octets du fichier (magic bytes MP4/ISO Base Media)"""
    header = f.read(12)
    f.seek(0)
    # ftyp box : octets 4-7 = 'ftyp' (ISO Base Media / MP4)
    return len(header) >= 8 and header[4:8] == b'ftyp'

# ── Helpers override display ──────────────────────────────────────────────────
def load_display_overrides() -> dict:
    try:
        if os.path.isfile(DISPLAY_OVERRIDE_FILE):
            with open(DISPLAY_OVERRIDE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_display_overrides(overrides: dict):
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(DISPLAY_OVERRIDE_FILE, "w") as f:
        json.dump(overrides, f, indent=2)

# ── Templates HTML ─────────────────────────────────────────────────────────────
LOGIN_HTML = """
<!doctype html><html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACMS - Connexion</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Arial,sans-serif;background:#1a1a2e;display:flex;align-items:center;justify-content:center;min-height:100vh}
  .card{background:#fff;border-radius:12px;padding:40px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
  h1{text-align:center;color:#16213e;margin-bottom:8px;font-size:1.4em}
  p.sub{text-align:center;color:#888;margin-bottom:28px;font-size:.9em}
  input[type=password]{width:100%;padding:12px 14px;border:1.5px solid #ddd;border-radius:8px;font-size:1em;margin-bottom:16px;outline:none;transition:border .2s}
  input[type=password]:focus{border-color:#0f3460}
  button{width:100%;padding:12px;background:#0f3460;color:#fff;border:none;border-radius:8px;font-size:1em;cursor:pointer;transition:background .2s}
  button:hover{background:#16213e}
  .error{background:#fee;color:#c00;padding:10px;border-radius:6px;margin-bottom:14px;font-size:.9em;text-align:center}
  .logo{text-align:center;font-size:2.5em;margin-bottom:12px}
</style></head><body>
<div class="card">
  <div class="logo">🕌</div>
  <h1>ACMS Administration</h1>
  <p class="sub">Mosquée En-Nour — Sartrouville</p>
  {% for msg in get_flashed_messages() %}<div class="error">{{ msg }}</div>{% endfor %}
  <form method="post">
    <input type="password" name="code" placeholder="Votre code" autofocus autocomplete="off"
           inputmode="numeric" pattern="[0-9]*" style="letter-spacing:.3em;text-align:center;font-size:1.4em">
    <button type="submit">Connexion</button>
  </form>
</div></body></html>
"""

DASHBOARD_HTML = """
<!doctype html><html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACMS - Administration</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Arial,sans-serif;background:#f0f2f5;color:#222}
  header{background:#0f3460;color:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:1.2em}
  header a{color:#aac;font-size:.85em;text-decoration:none}
  header a:hover{color:#fff}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:24px;max-width:960px;margin:0 auto}
  @media(max-width:640px){.grid{grid-template-columns:1fr}}
  .card{background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
  .card h2{font-size:1.05em;color:#0f3460;margin-bottom:18px;padding-bottom:10px;border-bottom:2px solid #e8eaed;display:flex;align-items:center;gap:8px}
  /* VIDÉO */
  .drop-area{border:2.5px dashed #b0bec5;border-radius:10px;padding:32px 20px;text-align:center;cursor:pointer;transition:all .2s;margin-bottom:14px}
  .drop-area.hover{border-color:#0f3460;background:#e8f0fe}
  .drop-area p{color:#888;font-size:.95em;margin-bottom:10px}
  .drop-area .icon{font-size:2.4em;margin-bottom:8px}
  .file-info{background:#f8f9fa;border-radius:8px;padding:10px 14px;font-size:.85em;color:#555;margin-bottom:14px}
  .file-info span{font-weight:bold;color:#333}
  /* BOUTONS */
  .btn{display:inline-block;padding:11px 20px;border-radius:8px;font-size:.95em;cursor:pointer;border:none;transition:all .2s;font-weight:500}
  .btn-primary{background:#0f3460;color:#fff;width:100%}
  .btn-primary:hover{background:#16213e}
  .btn-primary:disabled{background:#b0bec5;cursor:not-allowed}
  .btn-danger{background:#e53935;color:#fff;width:100%}
  .btn-danger:hover{background:#b71c1c}
  /* PRESETS CAMÉRA */
  .presets{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .preset-btn{padding:18px 10px;border-radius:10px;border:2px solid #e0e0e0;background:#fff;cursor:pointer;transition:all .2s;text-align:center}
  .preset-btn:hover{border-color:#0f3460;background:#e8f0fe;transform:translateY(-2px)}
  .preset-btn.active{border-color:#0f3460;background:#0f3460;color:#fff}
  .preset-btn .num{font-size:1.6em;font-weight:bold;display:block}
  .preset-btn .name{font-size:.8em;margin-top:4px;opacity:.8}
  /* PLAY ORDER */
  .play-order-status{background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:12px;font-size:.9em;margin-bottom:14px;display:none}
  .play-order-status.active{display:block}
  /* ALERTES */
  .alert{padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:.9em}
  .alert-success{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}
  .alert-error{background:#ffebee;color:#c62828;border:1px solid #ef9a9a}
  .progress-bar{height:6px;background:#e0e0e0;border-radius:3px;margin-top:10px;overflow:hidden;display:none}
  .progress-fill{height:100%;background:#0f3460;border-radius:3px;width:0;transition:width .3s}
  input[type=file]{display:none}
  .cam-status{font-size:.8em;color:#888;margin-top:8px;text-align:center;min-height:18px}
</style></head><body>
<header>
  <h1>🕌 ACMS — Administration</h1>
  <div style="display:flex;align-items:center;gap:18px">
    <a href="/">🏠 Accueil</a>
    <a href="/display">📺 Affichage</a>
    <span style="font-size:.9em;opacity:.8">👤 {{ session.get('username', '') }}</span>
    <a href="/logout">Déconnexion</a>
  </div>
</header>

<div class="grid">

  <!-- ── VIDÉO MANUELLE ── -->
  <div class="card">
    <h2>▶️ Lecture manuelle (30 min — toutes les boxes)</h2>
    <div class="play-order-status {% if play_order_active %}active{% endif %}" id="play-order-status">
      ⏳ Vidéo manuelle en cours de lecture sur toutes les boxes…
    </div>
    <button class="btn btn-{% if play_order_active %}danger{% else %}primary{% endif %}"
            id="play-order-btn" onclick="togglePlayOrder()">
      {% if play_order_active %}⛔ Arrêter la lecture{% else %}▶️ Lancer la vidéo maintenant{% endif %}
    </button>
  </div>

  <!-- ── CAMÉRA FORCÉE ── -->
  <div class="card">
    <h2>📡 Caméra forcée (30 min — toutes les boxes)</h2>
    <div class="play-order-status {% if onvif_force_active %}active{% endif %}" id="onvif-force-status">
      📹 Caméra live en cours sur toutes les boxes…
    </div>
    <button class="btn btn-{% if onvif_force_active %}danger{% else %}primary{% endif %}"
            id="onvif-force-btn" onclick="toggleOnvifForce()">
      {% if onvif_force_active %}⛔ Arrêter la caméra live{% else %}📡 Afficher la caméra maintenant{% endif %}
    </button>
  </div>

  <!-- ── VIDÉO ── -->
  <div class="card">
    <h2>🎬 Vidéo post-prière</h2>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in msgs %}
        <div class="alert alert-{{ 'success' if cat == 'success' else 'error' }}">{{ msg }}</div>
      {% endfor %}
    {% endwith %}

    <div class="file-info">
      Fichier actuel :<br>
      <span>{{ video_name }}</span> — {{ video_size }} — {{ video_date }}
    </div>

    <form id="upload-form" method="post" action="/upload" enctype="multipart/form-data">
      <div class="drop-area" id="drop-area" onclick="document.getElementById('file-input').click()">
        <div class="icon">📁</div>
        <p>Glisser-déposer la vidéo ici<br>ou cliquer pour choisir</p>
        <p id="chosen-file" style="color:#0f3460;font-weight:bold"></p>
      </div>
      <input type="file" id="file-input" name="video" accept="video/mp4,.mp4">
      <div class="progress-bar" id="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
      <button type="submit" class="btn btn-primary" id="upload-btn" disabled>Envoyer la vidéo</button>
    </form>
  </div>

  <!-- ── CAMÉRA ── -->
  <div class="card">
    <h2>📷 Caméra IMAM — Presets</h2>
    <div class="presets">
      {% for pid, pname in presets %}
      <button class="preset-btn {% if pid == active_preset %}active{% endif %}"
              onclick="gotoPreset({{ pid }}, this)" data-id="{{ pid }}">
        <span class="num">{{ pid }}</span>
        <span class="name">{{ pname }}</span>
      </button>
      {% endfor %}
    </div>
    <div class="cam-status" id="cam-status">Cliquez sur un preset pour déplacer la caméra</div>
  </div>

</div>

<script>
// ── Drag & drop ──────────────────────────────────────────────────────────────
const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('file-input');
const chosenFile = document.getElementById('chosen-file');
const uploadBtn = document.getElementById('upload-btn');

['dragenter','dragover'].forEach(e => dropArea.addEventListener(e, ev => { ev.preventDefault(); dropArea.classList.add('hover'); }));
['dragleave','drop'].forEach(e => dropArea.addEventListener(e, ev => { ev.preventDefault(); dropArea.classList.remove('hover'); }));

dropArea.addEventListener('drop', ev => {
  const files = ev.dataTransfer.files;
  if (files.length) setFile(files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(file) {
  chosenFile.textContent = file.name + ' (' + (file.size / 1024 / 1024).toFixed(1) + ' Mo)';
  uploadBtn.disabled = false;
  // Assign to form input
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
}

// ── Upload avec progression ──────────────────────────────────────────────────
document.getElementById('upload-form').addEventListener('submit', function(e) {
  e.preventDefault();
  if (!fileInput.files.length) return;
  const formData = new FormData(this);
  const bar = document.getElementById('progress-bar');
  const fill = document.getElementById('progress-fill');
  bar.style.display = 'block';
  uploadBtn.disabled = true;
  uploadBtn.textContent = 'Envoi en cours…';
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/upload');
  xhr.upload.onprogress = ev => {
    if (ev.lengthComputable) fill.style.width = (ev.loaded / ev.total * 100) + '%';
  };
  xhr.onload = () => { window.location.href = '/'; };
  xhr.send(formData);
});

// ── Preset caméra ─────────────────────────────────────────────────────────────
function gotoPreset(id, btn) {
  const status = document.getElementById('cam-status');
  status.textContent = '⏳ Déplacement vers preset ' + id + '…';
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  fetch('/camera/preset/' + id, {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      if (d.ok) { btn.classList.add('active'); status.textContent = '✅ Caméra positionnée : ' + d.name; }
      else { status.textContent = '❌ Erreur : ' + d.error; }
    })
    .catch(() => { status.textContent = '❌ Caméra inaccessible'; });
}

// ── Play order ───────────────────────────────────────────────────────────────
function togglePlayOrder() {
  fetch('/play_order/toggle', {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      const btn = document.getElementById('play-order-btn');
      const status = document.getElementById('play-order-status');
      if (d.active) {
        btn.textContent = '⛔ Arrêter la lecture';
        btn.className = 'btn btn-danger';
        status.style.display = 'block';
      } else {
        btn.textContent = '▶️ Lancer la vidéo maintenant';
        btn.className = 'btn btn-primary';
        status.style.display = 'none';
      }
    });
}

// ── ONVIF force ───────────────────────────────────────────────────────────────
function toggleOnvifForce() {
  fetch('/onvif_force/toggle', {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      const btn = document.getElementById('onvif-force-btn');
      const status = document.getElementById('onvif-force-status');
      if (d.active) {
        btn.textContent = '⛔ Arrêter la caméra live';
        btn.className = 'btn btn-danger';
        status.style.display = 'block';
      } else {
        btn.textContent = '📡 Afficher la caméra maintenant';
        btn.className = 'btn btn-primary';
        status.style.display = 'none';
      }
    });
}
</script>
</body></html>
"""

DISPLAY_HTML = """
<!doctype html><html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACMS - Affichage des boxes</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Arial,sans-serif;background:#f0f2f5;color:#222}
  header{background:#0f3460;color:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:1.2em}
  header div{display:flex;align-items:center;gap:18px}
  header a{color:#aac;font-size:.85em;text-decoration:none}
  header a:hover{color:#fff}
  .container{max-width:860px;margin:28px auto;padding:0 16px}
  .card{background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 12px rgba(0,0,0,.08);margin-bottom:20px}
  .card h2{font-size:1.05em;color:#0f3460;margin-bottom:20px;padding-bottom:10px;border-bottom:2px solid #e8eaed}
  table{width:100%;border-collapse:collapse}
  thead th{text-align:left;padding:8px 12px;font-size:.82em;color:#888;text-transform:uppercase;letter-spacing:.05em;border-bottom:2px solid #e8eaed}
  tbody tr{border-bottom:1px solid #f0f2f5}
  tbody tr:last-child{border-bottom:none}
  td{padding:10px 12px;vertical-align:middle}
  td.box-name{font-weight:bold;color:#0f3460;font-size:1em;white-space:nowrap}
  /* Segmented control */
  .seg{display:inline-flex;border:1.5px solid #d0d5dd;border-radius:8px;overflow:hidden;gap:0}
  .seg button{padding:8px 14px;border:none;background:#fff;cursor:pointer;font-size:.88em;color:#555;transition:all .15s;border-right:1px solid #d0d5dd;white-space:nowrap}
  .seg button:last-child{border-right:none}
  .seg button:hover{background:#f0f4ff;color:#0f3460}
  .seg button.active-auto{background:#e8f5e9;color:#2e7d32;font-weight:bold}
  .seg button.active-onvif{background:#e3f2fd;color:#1565c0;font-weight:bold}
  .seg button.active-mawaqit{background:#fff3e0;color:#e65100;font-weight:bold}
  .seg button.active-vlc{background:#f3e5f5;color:#6a1b9a;font-weight:bold}
  .status{font-size:.8em;color:#888;margin-top:4px}
  .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:.82em;color:#555;margin-bottom:18px}
  .legend span{display:flex;align-items:center;gap:5px}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  .dot-auto{background:#4caf50}.dot-onvif{background:#2196f3}.dot-mawaqit{background:#ff9800}.dot-vlc{background:#9c27b0}
  .btn-reset-all{padding:9px 18px;border-radius:8px;border:none;background:#eceff1;color:#37474f;font-size:.9em;cursor:pointer;transition:background .2s}
  .btn-reset-all:hover{background:#cfd8dc}
</style></head><body>
<header>
  <h1>🕌 ACMS — Affichage des boxes</h1>
  <div>
    <a href="/">🏠 Accueil</a>
    <span style="font-size:.9em;opacity:.8">👤 {{ username }}</span>
    <a href="/logout">Déconnexion</a>
  </div>
</header>

<div class="container">
  <div class="card">
    <h2>📺 Mode d'affichage par box</h2>

    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <div class="legend" style="margin-bottom:0">
        <span><span class="dot dot-auto"></span> Auto (planning prières)</span>
        <span><span class="dot dot-onvif"></span> Caméra ONVIF</span>
        <span><span class="dot dot-mawaqit"></span> Mawaqit</span>
        <span><span class="dot dot-vlc"></span> Vidéo (VLC)</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span id="boxes-updated" style="font-size:.78em;color:#aaa"></span>
        <button class="btn-reset-all" onclick="refreshBoxes()" style="padding:6px 12px;font-size:.82em">🔄 Actualiser</button>
      </div>
    </div>

    <table>
      <thead><tr><th>Box</th><th>Mode</th></tr></thead>
      <tbody id="boxes-table">
      {% for box in boxes %}
      <tr data-ip="{{ box.ip }}">
        <td class="box-name">{{ box.name }}<br><span style="font-size:.78em;color:#aaa;font-weight:normal">{{ box.ip }}</span></td>
        <td>
          <div class="seg" data-ip="{{ box.ip }}">
            <button onclick="setMode('{{ box.ip }}','AUTO',this)"
              class="{% if box.mode == 'AUTO' %}active-auto{% endif %}">🔄 Auto</button>
            <button onclick="setMode('{{ box.ip }}','ONVIF',this)"
              class="{% if box.mode == 'ONVIF' %}active-onvif{% endif %}">📷 Caméra</button>
            <button onclick="setMode('{{ box.ip }}','MAWAQIT',this)"
              class="{% if box.mode == 'MAWAQIT' %}active-mawaqit{% endif %}">🕌 Mawaqit</button>
            <button onclick="setMode('{{ box.ip }}','VLC',this)"
              class="{% if box.mode == 'VLC' %}active-vlc{% endif %}">🎬 Vidéo</button>
          </div>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>

  <button class="btn-reset-all" onclick="resetAll()">🔄 Tout remettre en Auto</button>
</div>

<script>
const CLASS = {AUTO:'active-auto',ONVIF:'active-onvif',MAWAQIT:'active-mawaqit',VLC:'active-vlc'};

function renderRow(box) {
  const mode = box.mode || 'AUTO';
  return `<tr data-ip="${box.ip}">
    <td class="box-name">${box.name}<br><span style="font-size:.78em;color:#aaa;font-weight:normal">${box.ip}</span></td>
    <td>
      <div class="seg" data-ip="${box.ip}">
        <button onclick="setMode('${box.ip}','AUTO',this)" class="${mode==='AUTO'?'active-auto':''}">🔄 Auto</button>
        <button onclick="setMode('${box.ip}','ONVIF',this)" class="${mode==='ONVIF'?'active-onvif':''}">📷 Caméra</button>
        <button onclick="setMode('${box.ip}','MAWAQIT',this)" class="${mode==='MAWAQIT'?'active-mawaqit':''}">🕌 Mawaqit</button>
        <button onclick="setMode('${box.ip}','VLC',this)" class="${mode==='VLC'?'active-vlc':''}">🎬 Vidéo</button>
      </div>
    </td>
  </tr>`;
}

function refreshBoxes() {
  const updEl = document.getElementById('boxes-updated');
  updEl && (updEl.textContent = '⏳ Actualisation…');
  fetch('/api/boxes')
    .then(r => r.json())
    .then(data => {
      const tbody = document.getElementById('boxes-table');
      tbody.innerHTML = data.boxes.map(renderRow).join('');
      if (updEl && data.updated) {
        const d = new Date(data.updated);
        updEl.textContent = `Scan: ${d.toLocaleDateString('fr-FR')} ${d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
      } else if (updEl) {
        updEl.textContent = '';
      }
    })
    .catch(() => { updEl && (updEl.textContent = '⚠️ Erreur de chargement'); });
}

function setMode(ip, mode, btn) {
  // Mise à jour visuelle immédiate
  const seg = btn.closest('.seg');
  seg.querySelectorAll('button').forEach(b => {
    Object.values(CLASS).forEach(c => b.classList.remove(c));
  });
  btn.classList.add(CLASS[mode]);

  fetch('/display/set', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ip, mode})
  }).catch(() => {
    // Réversion visuelle si erreur
    seg.querySelectorAll('button').forEach(b => b.classList.remove(...Object.values(CLASS)));
  });
}

function resetAll() {
  document.querySelectorAll('.seg').forEach(seg => {
    seg.querySelectorAll('button').forEach(b => {
      Object.values(CLASS).forEach(c => b.classList.remove(c));
    });
    seg.querySelector('button:first-child').classList.add('active-auto');
  });
  fetch('/display/reset', {method:'POST'});
}

// Auto-refresh toutes les 60 secondes
setInterval(refreshBoxes, 60000);
// Charger le timestamp initial sans re-render (boxes déjà dans le HTML)
fetch('/api/boxes').then(r=>r.json()).then(d=>{
  const el = document.getElementById('boxes-updated');
  if(el && d.updated) {
    const dt = new Date(d.updated);
    el.textContent = `Scan: ${dt.toLocaleDateString('fr-FR')} ${dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
  }
}).catch(()=>{});
</script>
</body></html>
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
def video_info():
    if os.path.isfile(VIDEO_PATH):
        size_mb = os.path.getsize(VIDEO_PATH) / 1024 / 1024
        mtime   = os.path.getmtime(VIDEO_PATH)
        date_str = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
        return "video.mp4", f"{size_mb:.1f} Mo", date_str
    return "Aucune vidéo", "—", "—"

def get_active_boxes():
    """Return detected boxes from boxes_status.json (written by stream manager).
    Falls back to the static BOXES list if the file doesn't exist yet."""
    try:
        with open(BOXES_STATUS_FILE, "r") as f:
            data = json.load(f)
        boxes = []
        for b in data.get("boxes", []):
            ip = b.get("ip", "")
            name = KNOWN_NAMES.get(ip) or b.get("name") or ip
            boxes.append({"ip": ip, "name": name})
        if boxes:
            return boxes
    except Exception:
        pass
    return BOXES  # fallback


def is_play_order_active():
    try:
        return open(PLAY_ORDER_FILE).read().strip() == "1"
    except Exception:
        return False

def is_onvif_force_active():
    try:
        return open(ONVIF_FORCE_FILE).read().strip() == "1"
    except Exception:
        return False

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
@login_required
def dashboard():
    v_name, v_size, v_date = video_info()
    presets = [(pid, info["name"]) for pid, info in sorted(PTZ_CONFIG["positions"].items())]
    return render_template_string(
        DASHBOARD_HTML,
        video_name=v_name, video_size=v_size, video_date=v_date,
        presets=presets,
        active_preset=None,
        play_order_active=is_play_order_active(),
        onvif_force_active=is_onvif_force_active()
    )

@app.route("/display", methods=["GET"])
@login_required
def display_page():
    overrides = load_display_overrides()
    boxes = [
        {**b, "mode": overrides.get(b["ip"]) or "AUTO"}
        for b in get_active_boxes()
    ]
    return render_template_string(DISPLAY_HTML, boxes=boxes, username=session.get("username", ""))

@app.route("/api/boxes", methods=["GET"])
@login_required
def api_boxes():
    """Return currently detected boxes + their override mode (used by JS for live refresh)."""
    overrides = load_display_overrides()
    boxes = [
        {**b, "mode": overrides.get(b["ip"]) or "AUTO"}
        for b in get_active_boxes()
    ]
    # Also return the file update timestamp if available
    updated = None
    try:
        with open(BOXES_STATUS_FILE) as f:
            updated = json.load(f).get("updated")
    except Exception:
        pass
    return jsonify({"boxes": boxes, "updated": updated})

@app.route("/display/set", methods=["POST"])
@login_required
def display_set():
    data = request.get_json(force=True, silent=True) or {}
    ip   = data.get("ip", "").strip()
    mode = data.get("mode", "AUTO").upper()
    # Valider que l'IP est dans la plage réseau autorisée (101-120)
    if ip not in _VALID_IP_RANGE or mode not in ("AUTO", "ONVIF", "MAWAQIT", "VLC"):
        return jsonify({"ok": False, "error": "Paramètres invalides"}), 400
    overrides = load_display_overrides()
    if mode == "AUTO":
        overrides.pop(ip, None)
    else:
        overrides[ip] = mode
    save_display_overrides(overrides)
    log_action(f"DISPLAY_SET {ip} -> {mode}")
    return jsonify({"ok": True})

@app.route("/display/reset", methods=["POST"])
@login_required
def display_reset():
    save_display_overrides({})
    log_action("DISPLAY_RESET (tout Auto)")
    return jsonify({"ok": True})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        code = request.form.get("code", "")
        username = check_code(code)
        if username:
            session["authenticated"] = True
            session["username"] = username
            session.permanent = False
            log_action("CONNEXION")
            return redirect(url_for("dashboard"))
        flash("Code incorrect")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("video")
    if not f or f.filename == "":
        flash("Aucun fichier sélectionné", "error")
        return redirect(url_for("dashboard"))

    filename = secure_filename(f.filename)
    if not allowed_file(filename):
        flash("Format non autorisé. Seul le format MP4 est accepté.", "error")
        return redirect(url_for("dashboard"))
    if not allowed_mime(f):
        flash("Fichier invalide : le contenu ne correspond pas à un fichier MP4.", "error")
        return redirect(url_for("dashboard"))

    os.makedirs(MEDIA_DIR, exist_ok=True)
    f.save(VIDEO_PATH)
    size_mb = os.path.getsize(VIDEO_PATH) / 1024 / 1024
    log_action(f"UPLOAD_VIDEO {size_mb:.1f}Mo")
    flash(f"✅ Vidéo mise à jour ({size_mb:.1f} Mo) — sera poussée sur les boxes à la prochaine prière", "success")
    return redirect(url_for("dashboard"))

@app.route("/camera/preset/<int:preset_id>", methods=["POST"])
@login_required
def camera_preset(preset_id):
    if preset_id not in PTZ_CONFIG["positions"]:
        return jsonify({"ok": False, "error": f"Preset {preset_id} inconnu"})
    ok = ptz.goto_preset(preset_id)
    name = PTZ_CONFIG["positions"][preset_id]["name"]
    if ok:
        log_action(f"CAMERA_PRESET {preset_id} ({name})")
        return jsonify({"ok": True, "name": name})
    return jsonify({"ok": False, "error": "Caméra inaccessible"})

@app.route("/play_order/toggle", methods=["POST"])
@login_required
def play_order_toggle():
    active = is_play_order_active()
    new_val = "0" if active else "1"
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        with open(PLAY_ORDER_FILE, "w") as fh:
            fh.write(new_val + "\n")
        log_action("PLAY_ORDER ON" if not active else "PLAY_ORDER OFF")
        return jsonify({"active": not active})
    except Exception as e:
        return jsonify({"active": active, "error": str(e)}), 500

@app.route("/onvif_force/toggle", methods=["POST"])
@login_required
def onvif_force_toggle():
    active = is_onvif_force_active()
    new_val = "0" if active else "1"
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        with open(ONVIF_FORCE_FILE, "w") as fh:
            fh.write(new_val + "\n")
        log_action("ONVIF_FORCE ON" if not active else "ONVIF_FORCE OFF")
        return jsonify({"active": not active})
    except Exception as e:
        return jsonify({"active": active, "error": str(e)}), 500


# ── Logging HTTP access ───────────────────────────────────────────────────────
# Écrit chaque requête HTTP dans http_access.log avec le nom d'utilisateur connecté.
# Les polling fréquents (/api/boxes) sont exclus pour éviter le bruit.
_http_logger_instance = None

def _get_http_logger():
    global _http_logger_instance
    if _http_logger_instance is None:
        os.makedirs(os.path.dirname(os.path.abspath(HTTP_LOG_FILE)), exist_ok=True)
        handler = TimedRotatingFileHandler(
            HTTP_LOG_FILE, when='midnight', backupCount=3, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("acms.http")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _http_logger_instance = logger
    return _http_logger_instance

# Chemins à ne pas journaliser (polling automatique JS)
_HTTP_LOG_SKIP = {"/api/boxes", "/favicon.ico"}

@app.after_request
def log_http_access(response):
    if request.path not in _HTTP_LOG_SKIP:
        try:
            who = session.get("username", "-") if session.get("authenticated") else "anonymous"
            ip  = request.remote_addr or "-"
            ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"{ts} | {who} | {ip} | {request.method} {request.path} | {response.status_code}"
            _get_http_logger().info(entry)
        except Exception:
            pass
    return response

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Écoute uniquement sur le réseau local (pas exposé sur internet)
    app.run(host="127.0.0.1", port=PORT, debug=False)
