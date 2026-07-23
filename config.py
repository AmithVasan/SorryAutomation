import os
from utils.env_config import (
    detect_adb, detect_appium, detect_emulator, detect_apk_folder,
)

# -------------------------------
# PATHS  (auto-detected; env var or the original Mac path still win — see
# utils/env_config.py. Zero config needed on a laptop with the Android SDK.)
# -------------------------------
APK_FOLDER = detect_apk_folder()

ADB_PATH = detect_adb()

APPIUM_PATH = detect_appium()

# -------------------------------
# EMULATOR
# -------------------------------
EMULATOR_NAME = os.environ.get("EMULATOR_NAME", "Tab")
EMULATOR_PATH = detect_emulator()

# -------------------------------
# APP
# -------------------------------
PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"
APP_NAME = "sorry"

# -------------------------------
# APPIUM
# -------------------------------
APPIUM_URL = "http://127.0.0.1:4723"
APPIUM_PORT = 4723

# -------------------------------
# ALTTESTER
# -------------------------------
ALTTESTER_PORT = 13000

# -------------------------------
# DEVICE COORDS
# -------------------------------
DEVICE_COORDS = {
    "real": {
        "ip_field": ("500", "1350"),
        "restart":  ("534", "1519"),
    },
    "emulator": {
        "ip_field": ("1250", "966"),
        "restart":  ("1285", "1116"),
    }
}

# -------------------------------
# APK
# -------------------------------
CHECKSUM_FILE = "apk_checksum.txt"