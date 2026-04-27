from dotenv import load_dotenv
load_dotenv()
import subprocess
import time
import logging
import socket
import os
import glob
import importlib
import traceback
import hashlib

from utils.driver_manager import set_driver


# --- CONFIG ---
APK_FOLDER = "/Users/amithvasan/Downloads/Testing Build"
ADB_PATH = "/Users/amithvasan/Library/Android/sdk/platform-tools/adb"
APPIUM_PATH = "/usr/local/bin/appium"

EMULATOR_NAME = "Tab"
EMULATOR_PATH = "/Users/amithvasan/Library/Android/sdk/emulator/emulator"

PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"

APPIUM_URL = "http://127.0.0.1:4723"

ALTTESTER_PORT = 13000
APP_NAME = "sorry"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------
# COORDINATES
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
# UTIL
# -------------------------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def wait_for_port(host, port, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except Exception:
            time.sleep(1)
    return False


# -------------------------------
# START SERVICES
# -------------------------------
def start_appium():
    logging.info("🚀 Checking Appium server...")

    if wait_for_port("127.0.0.1", 4723, timeout=3):
        logging.info("✅ Appium already running")
        return

    logging.info("🔥 Starting Appium server...")

    subprocess.Popen([
        "osascript", "-e",
        f'tell application "Terminal" to do script "{APPIUM_PATH}"'
    ])

    if not wait_for_port("127.0.0.1", 4723, timeout=40):
        raise RuntimeError("❌ Appium failed to start")

    logging.info("✅ Appium started")


def start_alttester():
    logging.info("🚀 Checking AltTester Desktop...")

    if wait_for_port("127.0.0.1", ALTTESTER_PORT, timeout=2):
        logging.info("✅ AltTester already running")
        return

    logging.info("🔥 Starting AltTester Desktop...")
    subprocess.Popen(["open", "-a", "AltTester Desktop"])

    if not wait_for_port("127.0.0.1", ALTTESTER_PORT, timeout=20):
        raise RuntimeError("❌ AltTester failed to start")

    logging.info("✅ AltTester started")


# -------------------------------
# DEVICE
# -------------------------------
def get_device_id():
    """
    Returns (device_id, is_emulator).
    is_emulator is True only if we just launched one fresh this run.
    """
    logging.info("🔍 Checking for connected devices...")

    result = subprocess.check_output([ADB_PATH, "devices"]).decode().splitlines()

    for line in result[1:]:
        if "device" in line:
            device_id = line.split()[0]
            logging.info(f"✅ Using device: {device_id}")
            is_emulator = device_id.startswith("emulator-")
            return device_id, is_emulator

    logging.warning("⚠️ No device → starting emulator")
    start_emulator()

    for _ in range(40):
        result = subprocess.check_output([ADB_PATH, "devices"]).decode()

        if "emulator-" in result:
            device_id = result.split("\n")[1].split()[0]
            wait_for_emulator_boot(device_id)
            return device_id, True

        time.sleep(1)

    raise RuntimeError("❌ No device found")


def start_emulator():
    logging.info(f"🚀 Starting emulator: {EMULATOR_NAME}")

    subprocess.Popen([
        EMULATOR_PATH,
        "-avd", EMULATOR_NAME
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_emulator_boot(device_id):
    logging.info("⏳ Waiting for emulator boot...")

    for _ in range(40):
        try:
            output = subprocess.check_output([
                ADB_PATH, "-s", device_id,
                "shell", "getprop", "sys.boot_completed"
            ]).decode().strip()

            if output == "1":
                logging.info("✅ Emulator boot completed")
                return
        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError("❌ Emulator boot timeout")


# -------------------------------
# APK
# -------------------------------
CHECKSUM_FILE = "apk_checksum.txt"

def get_latest_apk():
    files = glob.glob(os.path.join(APK_FOLDER, "*.apk"))
    return max(files, key=os.path.getctime)


def get_apk_checksum(apk_path):
    sha256 = hashlib.sha256()
    with open(apk_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_saved_checksum():
    if os.path.exists(CHECKSUM_FILE):
        return open(CHECKSUM_FILE).read().strip()
    return None


def save_checksum(checksum):
    open(CHECKSUM_FILE, "w").write(checksum)


def is_app_installed(package_name, device_id):
    result = subprocess.run(
        [ADB_PATH, "-s", device_id, "shell", "pm", "list", "packages"],
        capture_output=True,
        text=True
    )
    return package_name in result.stdout


def install_apk(device_id):
    apk_path = get_latest_apk()
    logging.info(f"Using APK: {apk_path}")

    current_checksum = get_apk_checksum(apk_path)
    saved_checksum = get_saved_checksum()

    if current_checksum == saved_checksum and is_app_installed(PACKAGE_NAME, device_id):
        logging.info("📦 APK unchanged → skipping install")
        return

    logging.info("📦 Installing APK...")
    subprocess.run([ADB_PATH, "-s", device_id, "install", "-r", apk_path])

    save_checksum(current_checksum)
    logging.info("✅ APK installed")


# -------------------------------
# LAUNCH GAME
# -------------------------------
def launch_game(device_id):
    logging.info("🎮 Launching game...")

    subprocess.run([
        ADB_PATH, "-s", device_id,
        "shell", "am", "start",
        "-n", f"{PACKAGE_NAME}/{ACTIVITY_NAME}"
    ])


# -------------------------------
# ALTTESTER POPUP
# -------------------------------
def handle_ip_popup(device_id, is_emulator=False):
    ip = get_local_ip()
    logging.info(f"Handling AltTester popup → {ip}")

    coords = DEVICE_COORDS["emulator"] if is_emulator else DEVICE_COORDS["real"]

    if is_emulator:
        logging.info("⏳ Emulator detected → waiting 15s for game to render...")
        time.sleep(15)
    else:
        time.sleep(5)

    ip_x, ip_y = coords["ip_field"]
    rst_x, rst_y = coords["restart"]

    subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", ip_x, ip_y])
    time.sleep(0.5)

    subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "123"])
    time.sleep(0.2)

    for _ in range(25):
        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "67"])

    subprocess.run([
        ADB_PATH, "-s", device_id,
        "shell", "input", "text", ip.replace(".", "\\.")
    ])

    time.sleep(1)
    subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "66"])
    time.sleep(1)
    subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", rst_x, rst_y])

    logging.info("✅ Restart tapped")


# -------------------------------
# TEST RUNNER
# -------------------------------
def run_all_tests(unity_driver, driver):
    logging.info("🚀 STARTING TEST EXECUTION")

    ordered_tests = [
        "test_01_guest_login.py",
        "test_02_shop.py",
    ]

    for file in ordered_tests:
        module_name = f"tests.{file[:-3]}"

        try:
            module = importlib.import_module(module_name)

            for attr in dir(module):
                if attr.startswith("test_"):
                    test_func = getattr(module, attr)
                    logging.info(f"▶️ Running {file}::{attr}")

                    try:
                        result = test_func(unity_driver, driver)
                        if result is not None and hasattr(result, 'wait_for_object'):
                            unity_driver = result
                            logging.info("🔄 unity_driver updated from test return")
                        logging.info(f"✅ PASS: {attr}")
                    except Exception:
                        logging.error(f"❌ FAIL: {attr}")
                        logging.error(traceback.format_exc())

        except Exception as e:
            logging.error(f"❌ Failed loading {file}: {e}")

    logging.info("🏁 ALL TESTS FINISHED")


# -------------------------------
# MAIN FLOW
# -------------------------------
def run_flow():
    start_appium()
    start_alttester()

    device_id, is_emulator = get_device_id()

    install_apk(device_id)
    launch_game(device_id)

    time.sleep(2)
    handle_ip_popup(device_id, is_emulator=is_emulator)

    time.sleep(2)

    driver, unity_driver = set_driver(
        device_id=device_id,
        app_package=PACKAGE_NAME,
        app_activity=ACTIVITY_NAME,
        alt_port=ALTTESTER_PORT,
        connect_alt=True
    )

    logging.info("🎉 SETUP COMPLETE")

    run_all_tests(unity_driver, driver)

    try:
        unity_driver.stop()
        driver.quit()
        logging.info("🔌 Drivers closed cleanly")
    except Exception as e:
        logging.warning(f"⚠️ Cleanup error: {e}")


# -------------------------------
# ENTRY
# -------------------------------
if __name__ == "__main__":
    try:
        run_flow()
    except Exception as e:
        logging.error("❌ SCRIPT FAILED")
        logging.error(str(e))
        raise