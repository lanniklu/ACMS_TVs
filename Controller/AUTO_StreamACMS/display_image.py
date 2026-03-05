#!/usr/bin/env python3
"""
display_image.py — One-shot script: push image to box(es), display 20s, switch back to ONVIF.

Usage:
    python display_image.py                  # all boxes (10.1.2.101-120)
    python display_image.py 10.1.2.109       # single box
    python display_image.py 109              # short form

Requires: ADB available (platform-tools)
Image:    media/aaa.jpeg (relative to this script)
"""

import subprocess
import time
import sys
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
IMAGE_LOCAL    = os.path.join(SCRIPT_DIR, "media", "aaa.jpeg")
IMAGE_REMOTE   = "/sdcard/Pictures/aaa.jpeg"

ADB_PORT          = 5555
SCAN_START        = 101
SCAN_END          = 120
NETWORK_BASE      = "10.1.2"
DISPLAY_DURATION  = 30          # seconds to show image
SCAN_TIMEOUT      = 1.5         # seconds for ADB port check
ADB_TIMEOUT       = 10          # seconds per ADB command

APP_ONVIF         = "net.biyee.onvifer/.OnviferActivity"
APP_IMAGE_VIEWER  = "com.android.gallery3d/.app.GalleryActivity"

# Try local platform-tools first, then system ADB
_PLATFORM_TOOLS = os.path.join(
    os.path.dirname(SCRIPT_DIR), "platform-tools", "adb.exe"
)
ADB = _PLATFORM_TOOLS if os.path.isfile(_PLATFORM_TOOLS) else "adb"

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def adb(ip: str, *args, timeout: int = ADB_TIMEOUT):
    """Run an ADB command against ip:port. Returns (success, stdout)."""
    target = f"{ip}:{ADB_PORT}"
    cmd = [ADB, "-s", target] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def adb_shell(ip: str, *shell_args, timeout: int = ADB_TIMEOUT):
    return adb(ip, "shell", *shell_args, timeout=timeout)


def port_open(ip: str) -> bool:
    try:
        with socket.create_connection((ip, ADB_PORT), timeout=SCAN_TIMEOUT):
            return True
    except OSError:
        return False


def connect(ip: str) -> bool:
    ok, out = adb(ip[:-len(f":{ADB_PORT}")] if ":" in ip else ip,
                  # connect via top-level adb connect
                  )
    # use direct call
    target = f"{ip}:{ADB_PORT}"
    try:
        r = subprocess.run(
            [ADB, "connect", target],
            capture_output=True, text=True, timeout=ADB_TIMEOUT
        )
        return "connected" in r.stdout.lower() or "already" in r.stdout.lower()
    except Exception:
        return False

# ─── CORE ────────────────────────────────────────────────────────────────────

def process_box(ip: str) -> bool:
    """Full pipeline for one box: push → display → ONVIF."""
    label = f"[{ip}]"

    # 1. Connect via ADB
    if not connect(ip):
        log(f"{label} ✗ ADB connect failed")
        return False
    log(f"{label} ✓ ADB connected")

    # 2. Push image
    target = f"{ip}:{ADB_PORT}"
    try:
        r = subprocess.run(
            [ADB, "-s", target, "push", IMAGE_LOCAL, IMAGE_REMOTE],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            log(f"{label} ✗ push failed: {r.stderr.strip()}")
            return False
    except Exception as e:
        log(f"{label} ✗ push exception: {e}")
        return False
    log(f"{label} ✓ image pushed → {IMAGE_REMOTE}")

    # 3. Broadcast media scan so image is visible
    adb_shell(ip,
        "am", "broadcast",
        "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d", f"file://{IMAGE_REMOTE}"
    )

    # 4. Display image — force specific viewer to bypass chooser
    ok, out = adb_shell(
        ip,
        "am", "start",
        "-n", APP_IMAGE_VIEWER,
        "-a", "android.intent.action.VIEW",
        "-d", f"file://{IMAGE_REMOTE}",
        "-t", "image/jpeg",
        "--activity-clear-top",
        "--activity-single-top"
    )
    if not ok:
        log(f"{label} ✗ image viewer launch failed: {out}")
        return False
    log(f"{label} ✓ image displayed — waiting {DISPLAY_DURATION}s …")

    return True  # caller waits, then restores


def restore_onvif(ip: str):
    """Press HOME then launch ONVIF."""
    label = f"[{ip}]"

    # HOME key to close viewer
    adb_shell(ip, "input", "keyevent", "3")
    time.sleep(0.5)

    # Launch ONVIF
    ok, out = adb_shell(
        ip,
        "am", "start", "-n", APP_ONVIF
    )
    if ok:
        log(f"{label} ✓ ONVIF relancé")
    else:
        log(f"{label} ✗ ONVIF launch failed: {out}")


def run_on_box(ip: str):
    """Full sequence for one box (blocking)."""
    if not process_box(ip):
        return
    time.sleep(DISPLAY_DURATION)
    restore_onvif(ip)

# ─── DISCOVERY ───────────────────────────────────────────────────────────────

def discover_boxes() -> list[str]:
    """Scan range and return reachable IPs."""
    log(f"Scanning {NETWORK_BASE}.{SCAN_START}-{SCAN_END} …")
    reachable = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {
            ex.submit(port_open, f"{NETWORK_BASE}.{i}"): f"{NETWORK_BASE}.{i}"
            for i in range(SCAN_START, SCAN_END + 1)
        }
        for f in as_completed(futures):
            ip = futures[f]
            if f.result():
                reachable.append(ip)
    reachable.sort()
    log(f"Found {len(reachable)} box(es): {reachable}")
    return reachable

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # Check image exists
    if not os.path.isfile(IMAGE_LOCAL):
        log(f"ERROR: image not found: {IMAGE_LOCAL}")
        sys.exit(1)
    log(f"Image: {IMAGE_LOCAL}")
    log(f"ADB:   {ADB}")

    # Determine target IPs
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("10."):
            targets = [arg]
        else:
            targets = [f"{NETWORK_BASE}.{arg}"]
        log(f"Target: {targets}")
    else:
        targets = discover_boxes()

    if not targets:
        log("No boxes found. Exiting.")
        sys.exit(1)

    # Run all boxes in parallel (push + display start), then wait, then restore
    log(f"--- Pushing image and launching viewer on {len(targets)} box(es) ---")

    ready = []
    with ThreadPoolExecutor(max_workers=len(targets)) as ex:
        futures = {ex.submit(process_box, ip): ip for ip in targets}
        for f in as_completed(futures):
            ip = futures[f]
            if f.result():
                ready.append(ip)

    if not ready:
        log("No boxes responded successfully.")
        sys.exit(1)

    log(f"--- {len(ready)} box(es) displaying image — waiting {DISPLAY_DURATION}s ---")
    time.sleep(DISPLAY_DURATION)

    log("--- Restoring ONVIF ---")
    with ThreadPoolExecutor(max_workers=len(ready)) as ex:
        list(ex.map(restore_onvif, ready))

    log("Done.")


if __name__ == "__main__":
    main()
