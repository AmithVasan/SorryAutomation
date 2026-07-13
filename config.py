import os

# -------------------------------
# PATHS
# -------------------------------
APK_FOLDER = os.environ.get(
    "APK_FOLDER",
    "/Users/amithvasan/Downloads/Testing Build"
)

ADB_PATH = os.environ.get(
    "ADB_PATH",
    "/Users/amithvasan/Library/Android/sdk/platform-tools/adb"
)

APPIUM_PATH = os.environ.get(
    "APPIUM_PATH",
    "/usr/local/bin/appium"
)

# -------------------------------
# EMULATOR
# -------------------------------
EMULATOR_NAME = os.environ.get("EMULATOR_NAME", "Tab")
EMULATOR_PATH = os.environ.get(
    "EMULATOR_PATH",
    "/Users/amithvasan/Library/Android/sdk/emulator/emulator"
)

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