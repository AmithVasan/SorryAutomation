from dotenv import load_dotenv
load_dotenv()
import time

import subprocess
import logging
import socket
import os
import glob
import importlib
import traceback
import hashlib
import threading
from utils.report_manager import send_reports
from utils.driver_manager import set_driver
from utils.state_manager import state
from utils.google_play_helper import reconnect_alttester
import utils.event_tracker as event_tracker
import utils.popup_handler as popup_handler
from tests.test_registry import TEST_REGISTRY
from datetime import datetime


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

# --- WIFI ADB CONFIG ---
#
# Three modes:
#   ""        → USB mode (default, no WiFi)
#   "auto"    → Auto-detect device IP from USB at startup, then switch to WiFi.
#               Plug USB in at the start, unplug after the script connects.
#               Handles daily IP changes automatically — nothing to update.
#   "x.x.x.x" → Static IP (only useful if you've set a fixed IP on the device).
#
WIFI_DEVICE_IP   = "auto"   # ← set to "auto" for wireless mode
WIFI_ADB_PORT    = 5555    # standard ADB TCP port
WIFI_IP_CACHE    = ".wifi_device_ip"  # file where the last known IP is cached

# --- PARALLEL EXECUTION CONFIG ---
# Set PARALLEL_MODE = True to run tests on ALL connected devices simultaneously.
# Each device runs the full test suite in its own thread.
# Combined report is sent once at the end.
#
# DEVICE_APP_NAMES maps each device index to its AltTester appName.
# Index 0 = first detected device, 1 = second, etc.
# The appName must match what was compiled into the APK's AltTester config.
# If both devices run the same APK (same appName), set both to "sorry".
PARALLEL_MODE    = False
DEVICE_APP_NAMES = ["sorry", "sorry"]   # extend for more devices

# --- SLACK BUILD WATCHER ---
#
# Checks a Slack channel for new APK builds after run-type selection.
# A build is picked up when ANY keyword in SLACK_MATCH_KEYWORDS appears
# (case-insensitive) in the message text, APK filename, or branch name
# mentioned in the message.
#
# Set SLACK_BUILD_CHANNEL and SLACK_BOT_TOKEN in your .env file.
# Leave SLACK_BUILD_CHANNEL empty ("") to disable the watcher entirely.
#
SLACK_BUILD_CHANNEL  = os.getenv("SLACK_BUILD_CHANNEL", "")     # e.g. C0ABC123XYZ
SLACK_BOT_TOKEN      = os.getenv("SLACK_BOT_TOKEN",     "")     # xoxb-... bot token
SLACK_MATCH_KEYWORDS = ["[SAT]", "alttester"]                   # case-insensitive; covers [SAT], AltTester, Alttester, alttester
SLACK_LAST_TS_FILE   = ".slack_last_build_ts"                   # tracks last downloaded ts


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------
# UTIL
# -------------------------------
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
def _appium_healthy(timeout=3):
    """
    Real Appium health check — hits GET /status instead of just testing
    TCP connectivity.  A raw port check can return True for any process
    listening on 4723; this confirms Appium is actually ready for sessions.
    """
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:4723/status", timeout=2
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def start_appium():
    logging.info("🚀 Checking Appium server...")

    if _appium_healthy(timeout=3):
        logging.info("✅ Appium already running and healthy")
        return

    logging.info("🔥 Starting Appium server...")

    subprocess.Popen([
        "osascript", "-e",
        f'tell application "Terminal" to do script "{APPIUM_PATH}"'
    ])

    # Wait for Appium to be genuinely ready (not just the port to open)
    logging.info("⏳ Waiting for Appium to be ready...")
    deadline = time.time() + 60
    while time.time() < deadline:
        if _appium_healthy(timeout=2):
            logging.info("✅ Appium started and healthy")
            return
        time.sleep(1)

    raise RuntimeError("❌ Appium failed to start within 60 s")


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
def _get_usb_device_id():
    """
    Return the ADB serial of the first USB-connected device, or None.
    USB serials never contain ':' — WiFi/TCP device_ids do (e.g. 10.x.x.x:5555).
    """
    try:
        lines = subprocess.check_output(
            [ADB_PATH, "devices"], timeout=5
        ).decode().splitlines()
        for line in lines[1:]:
            if "\tdevice" in line:
                candidate = line.split()[0]
                if ":" not in candidate:   # not a TCP/WiFi connection
                    return candidate
    except Exception:
        pass
    return None


def get_all_connected_devices():
    """
    Return a list of all ADB device_ids currently reachable.
    Includes both USB-connected serials and any active WiFi (TCP) devices.
    Used by parallel mode to discover how many devices to run against.
    """
    devices = []
    try:
        lines = subprocess.check_output(
            [ADB_PATH, "devices"], timeout=5
        ).decode().splitlines()
        for line in lines[1:]:
            if "\tdevice" in line:
                devices.append(line.split()[0])
    except Exception:
        pass
    return devices


def _load_cached_ip():
    """Return the last-saved WiFi IP, or None if cache file doesn't exist."""
    try:
        ip = open(WIFI_IP_CACHE).read().strip()
        return ip if ip else None
    except FileNotFoundError:
        return None


def _save_cached_ip(ip):
    """Persist the current WiFi IP so the next run can skip USB detection."""
    try:
        open(WIFI_IP_CACHE, "w").write(ip)
        logging.info(f"   💾 WiFi IP cached → {WIFI_IP_CACHE} ({ip})")
    except Exception as e:
        logging.warning(f"   ⚠️ Could not save WiFi IP cache: {e}")


def _get_device_wifi_ip(usb_device_id):
    """
    Read the current WiFi IP address directly from the USB-connected device.
    Tries wlan0 first, then any active wlan interface.
    Returns an IP string like "192.168.1.45", or raises RuntimeError.
    """
    # Primary: ip -f inet addr show wlan0
    try:
        out = subprocess.check_output(
            [ADB_PATH, "-s", usb_device_id, "shell",
             "ip", "-f", "inet", "addr", "show", "wlan0"],
            timeout=8
        ).decode()
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                ip = line.split()[1].split("/")[0]
                logging.info(f"   📶 Detected WiFi IP (wlan0): {ip}")
                return ip
    except Exception:
        pass

    # Fallback: ip route — picks up any wlan interface
    try:
        out = subprocess.check_output(
            [ADB_PATH, "-s", usb_device_id, "shell", "ip", "route"],
            timeout=8
        ).decode()
        for line in out.splitlines():
            if "wlan" in line and "src" in line:
                parts = line.split()
                src_idx = parts.index("src")
                ip = parts[src_idx + 1]
                logging.info(f"   📶 Detected WiFi IP (route): {ip}")
                return ip
    except Exception:
        pass

    raise RuntimeError(
        "❌ Could not detect device WiFi IP — is WiFi enabled on the device?"
    )


def connect_wifi_device(ip, port=5555, timeout=10):
    """
    Connect to an Android device over WiFi via ADB TCP/IP.
    Returns the ADB device_id string, e.g. "192.168.1.45:5555".
    Always raises RuntimeError on failure (including timeout) so callers
    can catch a single exception type for fallback logic.
    """
    device_id = f"{ip}:{port}"
    logging.info(f"📡 Connecting to WiFi device: {device_id} ...")

    try:
        result = subprocess.run(
            [ADB_PATH, "connect", device_id],
            capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"❌ WiFi ADB connect timed out for {device_id} "
            f"(IP likely changed — falling back to USB)"
        )

    output = result.stdout.strip() or result.stderr.strip()
    logging.info(f"   ADB connect → {output}")

    if "connected" in output.lower():
        logging.info(f"✅ WiFi ADB connected: {device_id}")
        return device_id

    raise RuntimeError(
        f"❌ WiFi ADB connect failed for {device_id}: {output}"
    )


def get_device_id():
    """
    Returns (device_id, is_emulator).
    is_emulator is True only if we just launched one fresh this run.

    Modes (controlled by WIFI_DEVICE_IP at the top of this file):
      ""        → USB mode. Picks the first device from `adb devices`.
      "auto"    → Auto-WiFi mode. Finds the USB-connected device, reads its
                  current WiFi IP, switches ADB to TCP (adb tcpip), then
                  connects wirelessly. Handles daily DHCP IP changes — no
                  config update needed between runs.
      "x.x.x.x" → Static-IP mode. Connects directly to the given IP.
    """
    logging.info("🔍 Checking for connected devices...")

    # --- Auto-WiFi mode ---
    if WIFI_DEVICE_IP == "auto":
        logging.info("📡 Auto-WiFi mode — checking cached IP first...")

        # ── Step 1: Try cached IP (no USB needed) ──────────────────────────
        cached_ip = _load_cached_ip()
        if cached_ip:
            logging.info(f"   📂 Cached IP found: {cached_ip} — trying without USB...")
            try:
                # Use a short timeout for cached IP — fail fast so USB
                # fallback kicks in quickly if the IP has changed
                device_id = connect_wifi_device(cached_ip, WIFI_ADB_PORT, timeout=5)
                logging.info(f"📡 device_id (cached WiFi — no USB needed): {device_id}")
                return device_id, False
            except RuntimeError:
                logging.warning(
                    f"   ⚠️ Cached IP {cached_ip} unreachable "
                    f"(IP has changed) — falling back to USB detection..."
                )

        # ── Step 2: USB fallback — detect current IP and re-cache ──────────
        logging.info("   🔌 USB detection required — looking for USB device...")
        result = subprocess.check_output([ADB_PATH, "devices"]).decode().splitlines()
        usb_device_id = None
        for line in result[1:]:
            if "\tdevice" in line:
                candidate = line.split()[0]
                # Skip already-connected WiFi devices (IP:port format)
                if ":" not in candidate:
                    usb_device_id = candidate
                    break

        if not usb_device_id:
            # No USB device either — fall through to the emulator path below
            logging.warning(
                "⚠️ Auto-WiFi: cached IP failed and no USB device found "
                "— falling back to emulator..."
            )
        else:
            logging.info(f"   USB device found: {usb_device_id}")

            # Read current WiFi IP from the USB-connected device
            detected_ip = _get_device_wifi_ip(usb_device_id)

            # Switch ADB daemon to TCP mode
            logging.info(f"   🔌 Switching ADB to TCP mode (port {WIFI_ADB_PORT})...")
            subprocess.run(
                [ADB_PATH, "-s", usb_device_id, "tcpip", str(WIFI_ADB_PORT)],
                check=False, timeout=8
            )
            time.sleep(2)   # give the daemon a moment to restart in TCP mode

            # Connect wirelessly and save the new IP
            device_id = connect_wifi_device(detected_ip, WIFI_ADB_PORT)
            _save_cached_ip(detected_ip)
            logging.info(f"📡 device_id (auto-WiFi via USB): {device_id}")
            logging.info("   💡 IP cached — you can unplug USB now. Next run won't need it.")
            return device_id, False     # WiFi = real device, never an emulator

    # --- Static-IP WiFi mode ---
    # `elif` is intentional — prevents "auto" from being used as an IP address
    # if the auto-WiFi block above falls through to the emulator path.
    elif WIFI_DEVICE_IP:
        device_id = connect_wifi_device(WIFI_DEVICE_IP, WIFI_ADB_PORT)
        logging.info(f"📡 device_id (static-WiFi): {device_id}")
        return device_id, False

    # --- USB / emulator mode (default) ---
    result = subprocess.check_output([ADB_PATH, "devices"]).decode().splitlines()

    for line in result[1:]:
        if "\tdevice" in line:
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

    logging.info("📦 Installing APK (may take a moment over WiFi)...")

    result = subprocess.run(
        [ADB_PATH, "-s", device_id, "install", "-r", apk_path],
        capture_output=True,
        text=True,
        timeout=300     # 5 min ceiling — large APKs over WiFi can be slow
    )

    output = (result.stdout + result.stderr).strip()
    if output:
        logging.info(f"   adb install → {output}")

    # adb install can return exit code 0 even on failure — check output too
    failed = (
        result.returncode != 0
        or "Failure" in output
        or "Exception" in output
        or ("error" in output.lower() and "0 errors" not in output.lower())
    )

    if failed:
        raise RuntimeError(f"❌ APK install failed (rc={result.returncode}): {output}")

    # Only save checksum AFTER confirmed success so failed installs
    # don't permanently block future install attempts
    save_checksum(current_checksum)
    logging.info("✅ APK installed successfully")


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
# REVERSE PORT FORWARDING
# device:13000 → host:13000 (AltTester Desktop)
# This lets the game use 127.0.0.1 as the Desktop IP regardless
# of the machine's WiFi address.
# -------------------------------

def setup_reverse_forward(device_id):
    logging.info("🔄 Setting up ADB reverse port forwarding...")
    subprocess.run(
        [ADB_PATH, "-s", device_id, "reverse",
         f"tcp:{ALTTESTER_PORT}", f"tcp:{ALTTESTER_PORT}"],
        check=False, timeout=10
    )
    logging.info(
        f"✅ Reverse forward: device:127.0.0.1:{ALTTESTER_PORT} "
        f"→ host:{ALTTESTER_PORT}"
    )


def teardown_reverse_forward(device_id):
    try:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "reverse",
             "--remove", f"tcp:{ALTTESTER_PORT}"],
            check=False, timeout=5
        )
        logging.info("✅ Reverse port forwarding removed")
    except Exception:
        pass


# -------------------------------
# ALTTESTER POPUP
# -------------------------------



# -------------------------------
# TEST RUNNER
# -------------------------------
# -------------------------------
# TEST RUNNER
# -------------------------------
# -------------------------------
# TEST RUNNER
# -------------------------------
# -----------------------------------------------------------------------
# ALTTESTER HEALTH CHECK
# -----------------------------------------------------------------------
def _alttester_healthy(unity_driver):
    """
    Lightweight liveness probe for the AltTester connection.
    Calls get_current_scene() — fast, read-only, raises immediately
    if the underlying socket is dead.
    Returns True if the connection is alive, False otherwise.
    """
    if unity_driver is None:
        return False
    try:
        unity_driver.get_current_scene()
        return True
    except Exception:
        return False


def run_all_tests(
    unity_driver,
    driver,
    run_type="complete",
    device_info=None,
    device_id="Unknown",
    send_report=True,       # False in parallel mode — caller merges + reports
    individual_tests=None,  # Override: explicit list of TEST_REGISTRY entries to run
):

    # Fresh tracker for every run
    event_tracker.reset()

    test_results = []
    suite_start_time = time.time()

    execution_start = datetime.now()
    logging.info("🚀 STARTING TEST EXECUTION")
    logging.info(f"📂 Run Type: {run_type.upper()}")

    # Store run_type so individual tests can read it
    state.set("run_type", run_type)

    # -------------------------------
    # APK NAME
    # -------------------------------
    apk_name = os.path.basename(get_latest_apk())

    # -------------------------------
    # FILTER TESTS
    # -------------------------------
    if individual_tests is not None:
        # Explicit list supplied — skip the run_type filter entirely
        selected_tests = individual_tests
    else:
        selected_tests = [
            t for t in TEST_REGISTRY if run_type in t.get("type", [])
        ]

    logging.info(f"🧪 Selected Tests: {len(selected_tests)}")

# -------------------------------
# EXECUTE TESTS
# -------------------------------
    for test in selected_tests:
    
        file = test["file"]
        function_name = test["function"]
        display_name = test["name"]
    
        module_name = file[:-3]
        module_path = os.path.join("tests", file)

        try:
            # Use spec_from_file_location so filenames with special characters
            # (e.g. "&") work — importlib.import_module requires valid identifiers.
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(module_name, module_path)
            module = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(module)
    
            test_func = getattr(module, function_name)

            # ---------------------------------
            # ALTTESTER HEALTH CHECK
            # Before every test: verify the AltTester connection is still
            # alive. If stale (e.g. after Season Pass triggers a Unity
            # scene reload), reconnect silently so the test starts clean.
            # ---------------------------------
            if not _alttester_healthy(unity_driver):
                logging.warning(
                    f"⚠️ AltTester connection stale before '{display_name}' "
                    f"— reconnecting..."
                )
                try:
                    unity_driver = reconnect_alttester(unity_driver)
                    state.set("unity_driver", unity_driver)
                    logging.info(
                        f"✅ AltTester reconnected — proceeding with '{display_name}'"
                    )
                except Exception as _reconnect_err:
                    logging.error(
                        f"❌ AltTester reconnect failed before '{display_name}': "
                        f"{_reconnect_err}"
                    )

            logging.info(f"▶️ Running: {display_name}")
    
            # ---------------------------------
            # DYNAMIC TEST STEP COLLECTION
            # ---------------------------------
            from utils.test_logger import TestStepCollector
    
            collector = TestStepCollector()
    
            root_logger = logging.getLogger()
            root_logger.addHandler(collector)
    
            try:
                result = test_func(unity_driver, driver)
    
                # allow tests to refresh unity driver
                if result is not None and hasattr(result, 'wait_for_object'):
                    unity_driver = result
                    logging.info("🔄 unity_driver updated from test return")
    
                logging.info(f"✅ PASS: {display_name}")
    
                test_results.append({
                    "name": display_name,
                    "status": "PASS",
                    "steps": collector.steps if collector.steps else [
                        "Test executed successfully"
                    ]
                })
    
            except Exception as e:
    
                logging.error(f"❌ FAIL: {display_name}")
                logging.error(traceback.format_exc())
    
                fail_steps = collector.steps.copy()
    
                fail_steps.append(f"Error: {str(e)}")
    
                test_results.append({
                    "name": display_name,
                    "status": "FAIL",
                    "steps": fail_steps
                })
    
            finally:
                # IMPORTANT → remove handler after each test
                root_logger.removeHandler(collector)
    
        except Exception as e:
    
            logging.error(f"❌ Failed loading {file}: {e}")
    
            test_results.append({
                "name": display_name,
                "status": "FAIL",
                "steps": [
                    f"Failed loading test module: {str(e)}"
                ]
            })
    
    logging.info("🏁 ALL TESTS FINISHED")

    # -------------------------------
    # EXECUTION TIME
    # -------------------------------
    total_time = int(time.time() - suite_start_time)

    minutes = total_time // 60
    seconds = total_time % 60

    duration_text = f"{minutes}m {seconds}s"

    logging.info(f"⏱️ TOTAL EXECUTION TIME: {duration_text}")

# -------------------------------
# REPORTS (SLACK + HTML CONTROLLED)
# -------------------------------
    if send_report:
        try:
            send_reports(
                results=test_results,
                total_duration=duration_text,
                apk_name=apk_name,
                run_type=run_type,
                device_id=device_id,
                device_info=device_info,
                start_time=execution_start.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            logging.info("✅ Reports processed")
        except Exception as e:
            logging.warning(f"⚠️ Report system failed: {e}")

    return test_results, duration_text, apk_name




# -------------------------------
# PARALLEL — per-device worker
# -------------------------------
def _device_worker(
    device_id,
    run_type,
    app_name,
    shared_results,
    results_lock,
    shared_events,
    events_lock,
    apk_name_holder,   # list of length 1 so the thread can write it back
):
    """
    Full setup + test run for a single device.
    Runs in its own thread in parallel mode.
    Results and events are merged into shared containers under locks.
    """
    thread_name = threading.current_thread().name
    logging.info(f"[{thread_name}] 🚀 Starting device worker for {device_id}")

    driver      = None
    unity_driver = None

    try:
        # ── ADB setup ─────────────────────────────────────────────────────
        usb_id = _get_usb_device_id()
        if usb_id and usb_id != device_id:
            logging.info(f"[{thread_name}] ⚡ Installing APK over USB ({usb_id})")
            install_apk(usb_id)
        else:
            install_apk(device_id)

        setup_reverse_forward(device_id)
        launch_game(device_id)

        logging.info(f"[{thread_name}] ⏳ Waiting for game to register with AltTester...")
        time.sleep(20)

        # ── Drivers ───────────────────────────────────────────────────────
        driver, unity_driver = set_driver(
            device_id=device_id,
            app_package=PACKAGE_NAME,
            app_activity=ACTIVITY_NAME,
            alt_port=ALTTESTER_PORT,
            connect_alt=True,
            app_name=app_name,
        )

        state.set("device_id",      device_id)
        state.set("appium_driver",  driver)
        state.set("unity_driver",   unity_driver)

        # ── Device info ───────────────────────────────────────────────────
        is_emulator  = device_id.startswith("emulator-")
        device_model = driver.capabilities.get("deviceModel",    "Unknown")
        android_ver  = driver.capabilities.get("platformVersion","Unknown")
        device_name  = driver.capabilities.get("deviceName",     "Unknown")
        window_size  = driver.get_window_size()
        resolution   = f"{window_size['width']} x {window_size['height']}"
        device_type  = (
            "Emulator"        if is_emulator
            else "WiFi Device" if ":" in device_id
            else "Real Device (USB)"
        )

        device_info = {
            "device_type":      device_type,
            "device_name":      device_name,
            "device_model":     device_model,
            "android_version":  android_ver,
            "resolution":       resolution,
        }

        # ── Run tests (no report — caller will send combined report) ──────
        results, duration, apk_name = run_all_tests(
            unity_driver,
            driver,
            run_type=run_type,
            device_id=device_id,
            device_info=device_info,
            send_report=False,
        )

        # ── Write back apk_name so the main thread can use it ─────────────
        if apk_name_holder is not None and not apk_name_holder[0]:
            with results_lock:
                apk_name_holder[0] = apk_name

        # ── Merge results into shared lists under locks ────────────────────
        labeled = [
            {**r, "device": device_id}
            for r in results
        ]
        with results_lock:
            shared_results.extend(labeled)

        event_tracker.merge_into(shared_events, lock=events_lock)

        logging.info(f"[{thread_name}] ✅ Device {device_id} complete")

    except Exception as e:
        logging.error(f"[{thread_name}] ❌ Device {device_id} failed: {e}")
        logging.error(traceback.format_exc())

    finally:
        try:
            unity_driver.stop()
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass
        teardown_reverse_forward(device_id)


# -------------------------------
# MAIN FLOW — single device
# -------------------------------
def _run_single_device(run_type="complete", individual_tests=None):
    execution_start = datetime.now()
    start_appium()
    start_alttester()

    device_id, is_emulator = get_device_id()
    state.set("device_id", device_id)
    logging.info(f"📱 device_id stored in state: {device_id}")

    # ── APK install: prefer USB even in WiFi mode (much faster) ──────────
    # device_id may be a WiFi IP (10.x.x.x:5555). If a USB cable is also
    # plugged in, push the APK over USB and let WiFi handle everything else.
    usb_id = _get_usb_device_id()
    if usb_id and usb_id != device_id:
        logging.info(f"⚡ USB detected ({usb_id}) — installing APK over USB (faster)")
        install_apk(usb_id)
    else:
        install_apk(device_id)

    setup_reverse_forward(device_id)
    launch_game(device_id)

    logging.info("⏳ Waiting for game to register with AltTester...")
    time.sleep(20)

    driver, unity_driver = set_driver(
        device_id=device_id,
        app_package=PACKAGE_NAME,
        app_activity=ACTIVITY_NAME,
        alt_port=ALTTESTER_PORT,
        connect_alt=True
    )

    # Store drivers in state so handlers and tests can
    # access and update them without needing them passed as arguments.
    state.set("appium_driver", driver)
    state.set("unity_driver", unity_driver)
    
    # ---------------------------------------------------
    # DEVICE INFO
    # ---------------------------------------------------
    device_model = driver.capabilities.get(
        "deviceModel",
        "Unknown"
    )
    
    android_version = driver.capabilities.get(
        "platformVersion",
        "Unknown"
    )
    
    device_name = driver.capabilities.get(
        "deviceName",
        "Unknown"
    )
    
    window_size = driver.get_window_size()
    
    resolution = (
        f"{window_size['width']} x "
        f"{window_size['height']}"
    )
    
    device_type = (
        "Emulator"        if is_emulator
        else "WiFi Device (auto)" if WIFI_DEVICE_IP == "auto"
        else "WiFi Device"        if WIFI_DEVICE_IP
        else "Real Device (USB)"
    )
    
    logging.info("🎉 SETUP COMPLETE")

    run_all_tests(
        unity_driver,
        driver,
        run_type=run_type,
        device_id=device_id,
        individual_tests=individual_tests,      # None → normal filter; list → override
        device_info={
            "device_type": device_type,
            "device_name": device_name,
            "device_model": device_model,
            "android_version": android_version,
            "resolution": resolution,
            "execution_start": execution_start.strftime("%Y-%m-%d %H:%M:%S")
        }
    )
    
    try:
        unity_driver.stop()
        logging.info("🔌 AltTester driver closed")
    except Exception:
        pass

    try:
        driver.quit()
        logging.info("🔌 Appium driver closed")
    except Exception:
        # Session already dead (e.g. killed by Google Play IAP flow) — not an error
        logging.info("ℹ️ Appium session already closed — nothing to clean up")

    teardown_reverse_forward(device_id)


# -------------------------------
# MAIN FLOW — parallel (multi-device)
# -------------------------------
def _run_parallel(run_types: list, label: str = "Parallel"):
    """
    Run tests on all connected devices simultaneously.

    Parameters
    ----------
    run_types : list of str
        One run-type string per device, e.g. ["smoke", "complete"].
        Device-0 gets run_types[0], Device-1 gets run_types[1], etc.
        If there are more devices than entries, the last entry is reused.
    label : str
        Human-readable label shown in the report header, e.g. "Smoke + Complete".
    """
    execution_start = datetime.now()

    start_appium()
    start_alttester()

    devices = get_all_connected_devices()
    if not devices:
        raise RuntimeError("❌ No devices found")

    logging.info(f"📱 Parallel mode — {len(devices)} device(s) detected: {devices}")

    if len(devices) == 1:
        logging.info("ℹ️ Only one device found — falling back to single-device mode")
        _run_single_device(run_types[0])
        return

    shared_results  = []
    results_lock    = threading.Lock()
    shared_events   = {}
    events_lock     = threading.Lock()
    apk_name_holder = [None]

    threads = []
    for i, device_id in enumerate(devices):
        # Per-device run_type: use last entry if list is shorter than device count
        device_run_type = run_types[i] if i < len(run_types) else run_types[-1]

        app_name = (
            DEVICE_APP_NAMES[i]
            if i < len(DEVICE_APP_NAMES)
            else APP_NAME
        )

        logging.info(
            f"   Device-{i + 1}: {device_id}  |  run_type={device_run_type}  |  app={app_name}"
        )

        t = threading.Thread(
            target=_device_worker,
            kwargs=dict(
                device_id=device_id,
                run_type=device_run_type,
                app_name=app_name,
                shared_results=shared_results,
                results_lock=results_lock,
                shared_events=shared_events,
                events_lock=events_lock,
                apk_name_holder=apk_name_holder,
            ),
            name=f"Device-{i + 1} [{device_run_type}]",
            daemon=True,
        )
        threads.append(t)

    suite_start = time.time()

    for t in threads:
        t.start()
        logging.info(f"▶️  Thread started: {t.name}")

    for t in threads:
        t.join()
        logging.info(f"✅ Thread finished: {t.name}")

    total_time    = int(time.time() - suite_start)
    duration_text = f"{total_time // 60}m {total_time % 60}s"
    apk_name      = apk_name_holder[0] or "unknown.apk"
    device_ids    = ", ".join(devices)

    logging.info(f"🏁 ALL DEVICES FINISHED — combined duration {duration_text}")

    try:
        send_reports(
            results=shared_results,
            total_duration=duration_text,
            apk_name=apk_name,
            run_type=label,
            device_id=device_ids,
            device_info={
                "device_type":     f"Parallel ({label})",
                "device_name":     device_ids,
                "device_model":    "Multiple",
                "android_version": "Multiple",
                "resolution":      "Multiple",
                "execution_start": execution_start.strftime("%Y-%m-%d %H:%M:%S"),
            },
            start_time=execution_start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        logging.info("✅ Combined report sent")
    except Exception as e:
        logging.warning(f"⚠️ Combined report failed: {e}")


# -------------------------------
# DISPATCHER
# -------------------------------
def run_flow(config):
    """
    Entry point — routes to single-device or parallel based on the config
    dict returned by select_run_type().

    config examples
    ───────────────
    Single device:  {"mode": "single",   "run_type": "smoke"}
    Parallel:       {"mode": "parallel",  "run_types": ["smoke", "complete"],
                     "label": "Smoke + Complete"}
    Individual:     {"mode": "individual", "test": <TEST_REGISTRY entry>}
    """
    mode = config.get("mode")

    if mode == "parallel":
        _run_parallel(
            run_types=config["run_types"],
            label=config.get("label", "Parallel"),
        )

    elif mode == "individual":
        selected = config["test"]
        login_entry = TEST_REGISTRY[0]          # test_01_guest_login — always first

        # Always run Guest Login first (sets player_id in state),
        # unless the user specifically selected it (no need to run it twice).
        if selected["file"] == login_entry["file"]:
            tests_to_run = [selected]
        else:
            tests_to_run = [login_entry, selected]

        logging.info(
            f"🎯 Individual mode → "
            + (f"Guest Login + {selected['name']}" if len(tests_to_run) > 1
               else selected['name'])
        )
        _run_single_device(run_type="individual", individual_tests=tests_to_run)

    else:
        _run_single_device(config.get("run_type", "complete"))


# -------------------------------
# SLACK BUILD WATCHER
# -------------------------------
def _download_slack_apk(file_obj, headers, msg_ts):
    """
    Stream-download an APK file from Slack into APK_FOLDER.
    Saves the message timestamp so the next run skips already-seen builds.
    """
    import requests as _req

    fname = file_obj["name"]
    url   = file_obj.get("url_private_download") or file_obj.get("url_private")
    dest  = os.path.join(APK_FOLDER, fname)

    logging.info(f"📥 New build found in Slack: {fname}")
    logging.info(f"   Downloading → {dest}")

    try:
        with _req.get(url, headers=headers, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(dest, "wb") as out:
                for chunk in r.iter_content(chunk_size=8192):
                    out.write(chunk)

        size_mb = os.path.getsize(dest) / (1024 * 1024)
        logging.info(f"✅ Downloaded {fname} ({size_mb:.1f} MB) → {dest}")

        # Persist the message ts so the next run only looks at newer messages
        try:
            open(SLACK_LAST_TS_FILE, "w").write(msg_ts)
        except Exception:
            pass

    except Exception as e:
        logging.warning(f"⚠️  Slack download failed: {e} — continuing with existing APK")


def _slack_keyword_match(text: str) -> bool:
    """
    Return True if any SLACK_MATCH_KEYWORD appears in `text` (case-insensitive).
    Covers: [SAT], AltTester, Alttester, alttester — and any future additions.
    """
    t = text.lower()
    return any(kw.lower() in t for kw in SLACK_MATCH_KEYWORDS)


def fetch_latest_build_from_slack():
    """
    Polls SLACK_BUILD_CHANNEL for APK uploads newer than the last download.

    A build is picked up when ANY keyword from SLACK_MATCH_KEYWORDS appears
    (case-insensitive) in:
      • The message text          → catches tags like [SAT], branch names, CI labels
      • The attached .apk filename → catches builds named with alttester / [SAT]

    If no new build is found the function returns silently and the run
    continues with whatever APK is already in APK_FOLDER.
    """
    import requests as _req

    if not SLACK_BOT_TOKEN or not SLACK_BUILD_CHANNEL:
        logging.info("ℹ️  Slack build watcher not configured — skipping")
        return

    # Only fetch messages newer than the last downloaded build
    last_ts = None
    try:
        last_ts = open(SLACK_LAST_TS_FILE).read().strip() or None
    except FileNotFoundError:
        pass

    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params  = {"channel": SLACK_BUILD_CHANNEL, "limit": 20}
    if last_ts:
        params["oldest"] = last_ts  # Slack returns messages with ts > oldest (exclusive)

    logging.info("🔍 Checking Slack for new builds...")

    try:
        resp = _req.get(
            "https://slack.com/api/conversations.history",
            headers=headers,
            params=params,
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        logging.warning(f"⚠️  Slack API unreachable: {e} — continuing without download")
        return

    if not data.get("ok"):
        logging.warning(f"⚠️  Slack API error: {data.get('error', 'unknown')} — skipping")
        return

    messages = data.get("messages", [])
    if not messages:
        logging.info("✅ No new builds in Slack")
        return

    # Messages are newest-first — pick the first (most recent) matching APK
    for msg in messages:
        text  = msg.get("text", "")
        files = msg.get("files", [])

        # Does the message text (which includes branch names, CI labels, etc.)
        # contain any of our keywords?
        msg_matches = _slack_keyword_match(text)

        for f in files:
            fname = f.get("name", "")
            if not fname.lower().endswith(".apk"):
                continue

            # Match if keyword found in message text OR in the APK filename
            if msg_matches or _slack_keyword_match(fname):
                logging.info(
                    f"   Match → keyword in "
                    f"{'message' if msg_matches else 'filename'}: {fname}"
                )
                _download_slack_apk(f, headers, msg["ts"])
                return  # done — newest matching build downloaded

    logging.info("✅ No new matching builds in Slack")


# -------------------------------
# RUN TYPE MENU
# -------------------------------
def select_run_type():
    """
    Interactive menu — returns a config dict consumed by run_flow().

    Single-device options (1-5) return:
        {"mode": "single", "run_type": "<type>"}

    Parallel options (6-7) return:
        {"mode": "parallel", "run_types": [...], "label": "..."}

    Individual option (8) returns:
        {"mode": "individual", "test": <TEST_REGISTRY entry>}
    """

    print("\n🎮 SELECT TEST RUN TYPE\n")
    print("── Single Device ───────────────────────")
    print("  1. Smoke Checklist")
    print("  2. Regression")
    print("  3. IAP Check")
    print("  4. BAT")
    print("  5. Complete Run")
    print()
    print("── Parallel (2 Devices) ────────────────")
    print("  6. Smoke + Complete    [Device 1: Smoke | Device 2: Complete]")
    print("  7. Smoke + IAP         [Device 1: Smoke | Device 2: IAP]")
    print()
    print("── Individual ──────────────────────────")
    print("  8. Run a single test")
    print()

    choice = input("Enter choice: ").strip()

    # ── Individual test sub-menu ──────────────────────────────────────────
    if choice == "8":
        print("\n── SELECT TEST ─────────────────────────")
        for i, t in enumerate(TEST_REGISTRY, start=1):
            print(f"  {i:2d}. {t['name']}")
        print()
        raw = input("Enter test number: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(TEST_REGISTRY):
                selected = TEST_REGISTRY[idx]
                print(f"\n✅ Selected: {selected['name']}")
                return {"mode": "individual", "test": selected}
        except (ValueError, IndexError):
            pass
        print("⚠️  Invalid selection — defaulting to Complete run")
        return {"mode": "single", "run_type": "complete"}

    single_map = {
        "1": "smoke",
        "2": "regression",
        "3": "iap",
        "4": "bat",
        "5": "complete",
    }

    parallel_map = {
        "6": {"run_types": ["smoke", "complete"], "label": "Smoke + Complete"},
        "7": {"run_types": ["smoke", "iap"],      "label": "Smoke + IAP"},
    }

    if choice in parallel_map:
        cfg = parallel_map[choice]
        return {"mode": "parallel", **cfg}

    # Default to "complete" for any unrecognised input
    run_type = single_map.get(choice, "complete")
    return {"mode": "single", "run_type": run_type}


# -------------------------------
# ENTRY
# -------------------------------
if __name__ == "__main__":

    START_TIME = time.time()

    config = select_run_type()

    # Check Slack for a new build after the user has made their selection.
    # Downloads the APK to APK_FOLDER if a matching file is found;
    # get_latest_apk() will pick it up automatically (newest by ctime).
    fetch_latest_build_from_slack()

    try:
        run_flow(config)

    except Exception as e:
        logging.error("❌ SCRIPT FAILED")
        logging.error(str(e))
        raise

    finally:

        end_time = time.time()
        total = end_time - START_TIME

        mins = int(total // 60)
        secs = int(total % 60)

        print("\n🏁 ALL TESTS FINISHED")
        print(f"⏱️ TOTAL EXECUTION TIME: {mins}m {secs}s")