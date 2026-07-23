#!/usr/bin/env python3
"""
check_setup.py — one-shot readiness check for a laptop that will run the suite.

Run it from the repo root:

    python3 check_setup.py

It prints PASS / MISSING for each requirement and never crashes — missing
pieces are reported, not raised. Green across the board = you can run the GUI
and hit Run with no further input.
"""

import os
import sys
import socket
import shutil
import subprocess
from pathlib import Path

OK, BAD, WARN = "✅", "❌", "⚠️ "
results = []   # (ok: bool|None, label, detail)


def add(ok, label, detail=""):
    results.append((ok, label, detail))


# ── Python version ──────────────────────────────────────────────────────────
add(sys.version_info >= (3, 8), "Python ≥ 3.8", sys.version.split()[0])

# ── Toolchain paths (auto-detected) ──────────────────────────────────────────
try:
    from utils.env_config import (
        detect_adb, detect_appium, detect_emulator, detect_apk_folder,
    )
    adb = detect_adb()
    add(Path(adb).exists() or shutil.which("adb") is not None, "adb found", adb)
    appium = detect_appium()
    add(Path(appium).exists() or shutil.which("appium") is not None,
        "appium found", appium)
    apk = detect_apk_folder()
    add(Path(apk).exists(), "APK folder", apk)
except Exception as e:
    add(False, "toolchain detection (utils/env_config)", str(e))
    adb = None

# ── A device is connected ─────────────────────────────────────────────────────
if adb and (Path(adb).exists() or shutil.which("adb")):
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True,
                             timeout=10).stdout
        devices = [l.split("\t")[0] for l in out.splitlines()[1:]
                   if l.strip() and "\tdevice" in l]
        add(bool(devices), "device connected (USB debugging on)",
            ", ".join(devices) if devices else "no authorized device in `adb devices`")
    except Exception as e:
        add(False, "adb devices", str(e))

# ── Python dependencies ───────────────────────────────────────────────────────
for mod, pip_name in [
    ("appium", "Appium-Python-Client"),
    ("alttester", "AltTester-Driver"),
    ("pymongo", "pymongo"),
    ("requests", "requests"),
    ("dotenv", "python-dotenv"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
]:
    try:
        __import__(mod)
        add(True, f"python dep: {mod}")
    except Exception:
        add(False, f"python dep: {mod}", f"pip install {pip_name}")

# ── .env (secrets) present ────────────────────────────────────────────────────
env_path = Path(".env")
if env_path.exists():
    text = env_path.read_text(errors="replace")
    has_mongo = "MONGO" in text
    has_slack = "SLACK" in text
    add(has_mongo, ".env has Mongo config", "" if has_mongo else "MONGO_* missing")
    add(has_slack, ".env has Slack config",
        "" if has_slack else "SLACK_* missing (only needed for Slack reports/build fetch)")
else:
    add(False, ".env present", "copy the shared .env into the repo root")

# ── Central AltTester server (only if SAT_ALT_HOST is set) ────────────────────
alt_host = os.environ.get("SAT_ALT_HOST")
if alt_host:
    try:
        with socket.create_connection((alt_host, 13000), timeout=4):
            add(True, f"central AltTester server reachable ({alt_host}:13000)")
    except Exception as e:
        add(False, f"central AltTester server ({alt_host}:13000)", str(e))
else:
    add(None, "SAT_ALT_HOST", "not set → LOCAL mode (AltTester runs on this machine)")

# ── Report ────────────────────────────────────────────────────────────────────
print("\n──────── Setup check ────────")
missing = 0
for ok, label, detail in results:
    mark = WARN if ok is None else (OK if ok else BAD)
    if ok is False:
        missing += 1
    line = f"{mark} {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
print("─────────────────────────────")
if missing == 0:
    print("All good — you can run: uvicorn webapp.app:app --host 127.0.0.1 --port 8000")
    sys.exit(0)
else:
    print(f"{missing} item(s) need attention — see above.")
    sys.exit(1)
