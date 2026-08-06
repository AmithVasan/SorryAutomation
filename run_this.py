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
import json
import re
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


# --- HTTPS CERTS ---
# Fresh framework Python builds (macOS python.org, and many clean installs) ship
# WITHOUT a default CA file, so slack_sdk's urllib uploads fail with
# "CERTIFICATE_VERIFY_FAILED". Point SSL at certifi's bundle if nothing is set —
# fixes Slack report uploads on every laptop with no manual cert install.
try:
    import certifi as _certifi
    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
except Exception:
    pass


# --- CONFIG ---
# Toolchain paths are auto-detected so the suite runs on any laptop with the
# Android SDK, with no manual input. Env vars (SAT_ADB / ADB_PATH, etc.) or the
# original Mac paths still take precedence — see utils/env_config.py.
from utils.env_config import (
    detect_adb, detect_appium, detect_emulator, detect_apk_folder,
    apply_remote_adb,
)

APK_FOLDER = detect_apk_folder()
ADB_PATH = detect_adb()
APPIUM_PATH = detect_appium()

EMULATOR_NAME = "Tab"
EMULATOR_PATH = detect_emulator()

PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"

APPIUM_URL = os.environ.get("SAT_APPIUM_URL", "http://127.0.0.1:4723")

ALTTESTER_PORT = 13000
APP_NAME = "sorry"

# --- REMOTE DEVICE MODE (Phase 2) ---
# When SAT_ADB_HOST is set, point adb + Appium at a device plugged into a
# teammate's laptop bridge (utils/env_config.apply_remote_adb). Runs at import,
# BEFORE start_appium()/get_device_id(), so every adb call + reverse-forward
# targets the remote device. No-op when unset → local runs are unchanged.
REMOTE_ADB = apply_remote_adb()

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
    status_url = APPIUM_URL.rstrip("/") + "/status"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(status_url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def start_appium():
    logging.info("🚀 Checking Appium server...")

    # Remote Appium (Phase 2): when SAT_APPIUM_URL points off-box, Appium runs
    # on the teammate's laptop next to the device (UiAutomator2 must be
    # co-located with the device). Don't start a local one — just verify it.
    if "127.0.0.1" not in APPIUM_URL and "localhost" not in APPIUM_URL:
        logging.info(f"🌐 Using REMOTE Appium at {APPIUM_URL}")
        if _appium_healthy(timeout=30):
            logging.info("✅ Remote Appium reachable and healthy")
            return
        raise RuntimeError(
            f"❌ Remote Appium at {APPIUM_URL} not reachable — start Appium on the laptop bridge"
        )

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

    # Explicit serial override — makes device selection deterministic, e.g. in
    # remote-device mode where `adb devices` (over the network bridge) may list
    # the teammate's device. Set SAT_DEVICE_ID to pin it.
    _forced = os.getenv("SAT_DEVICE_ID")
    if _forced:
        logging.info(f"🎯 Using forced device id (SAT_DEVICE_ID): {_forced}")
        return _forced, False

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


def _detect_aapt2():
    sdk = (os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
           or os.path.expanduser("~/Library/Android/sdk"))
    cands = sorted(glob.glob(os.path.join(sdk, "build-tools", "*", "aapt2")))
    return cands[-1] if cands else None


def get_apk_version(apk_path):
    """(versionName, versionCode) read from the APK via aapt2, or (None, None)."""
    aapt2 = _detect_aapt2()
    if not aapt2:
        return None, None
    try:
        out = subprocess.run([aapt2, "dump", "badging", apk_path],
                             capture_output=True, text=True, timeout=30).stdout
        m_vn = re.search(r"versionName='([^']*)'", out)
        m_vc = re.search(r"versionCode='([^']*)'", out)
        return (m_vn.group(1) if m_vn else None,
                m_vc.group(1) if m_vc else None)
    except Exception:
        return None, None


INSTALL_RECORD_FILE = "apk_installed.json"


def _load_install_records():
    """Per-device record of the APK checksum WE installed: {device_id: sha256}."""
    try:
        with open(INSTALL_RECORD_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_install_records(records):
    try:
        with open(INSTALL_RECORD_FILE, "w") as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        logging.warning(f"⚠️ could not save install record: {e}")


def is_app_installed(package_name, device_id):
    result = subprocess.run(
        [ADB_PATH, "-s", device_id, "shell", "pm", "list", "packages"],
        capture_output=True,
        text=True
    )
    return package_name in result.stdout


def get_installed_version(package_name, device_id):
    """(versionName, versionCode) of the installed package, or (None, None)."""
    try:
        r = subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "dumpsys", "package", package_name],
            capture_output=True, text=True, timeout=20
        )
        vn = vc = None
        for line in r.stdout.splitlines():
            s = line.strip()
            if vn is None and s.startswith("versionName="):
                vn = s.split("=", 1)[1].strip()
            if vc is None and "versionCode=" in s:
                try:
                    vc = s.split("versionCode=", 1)[1].split()[0]
                except Exception:
                    pass
        return vn, vc
    except Exception:
        return None, None


def human_device_name(device_id):
    """Readable device name from adb props (e.g. 'Samsung SM-G991B'); falls back
    to the serial if adb can't answer. Reports then show a real name instead of
    a bare serial like 'sm-53636'."""
    def prop(p):
        try:
            return subprocess.run(
                [ADB_PATH, "-s", device_id, "shell", "getprop", p],
                capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except Exception:
            return ""
    brand = prop("ro.product.brand") or prop("ro.product.manufacturer")
    model = prop("ro.product.model")
    name = " ".join(x for x in [brand.title() if brand else "", model] if x).strip()
    return name or device_id


def uninstall_app(package_name, device_id):
    logging.info(f"🗑️ Uninstalling '{package_name}' from {device_id}...")
    r = subprocess.run(
        [ADB_PATH, "-s", device_id, "uninstall", package_name],
        capture_output=True, text=True, timeout=120
    )
    out = (r.stdout + r.stderr).strip()
    logging.info(f"   adb uninstall → {out or 'done'}")


def _adb_install_once(device_id, apk_path, extra_args):
    """One `adb install` attempt. Returns (ok, combined_output).

    Always passes -r -d:  -d allows a version-code DOWNGRADE, which is essential
    here — the AltTester test build (e.g. 0.59.0/92) is usually OLDER than the
    prod build a personal device already has (e.g. 0.61.1/94), so a plain install
    is rejected as a downgrade (streamed installs report this with an empty
    reason, which is exactly what we saw)."""
    result = subprocess.run(
        [ADB_PATH, "-s", device_id, "install", "-r", "-d", *extra_args, apk_path],
        capture_output=True, text=True, timeout=900,
    )
    output = (result.stdout + result.stderr).strip()
    ok = not (
        result.returncode != 0
        or "Failure" in output
        or "Exception" in output
        or ("error" in output.lower() and "0 errors" not in output.lower())
    )
    return ok, output


def install_apk(device_id):
    """Guarantee THIS device has our exact AltTester APK.

    The install decision is PER-DEVICE (keyed by serial). The old logic compared
    a single global checksum and only checked that the *package* existed — so a
    fresh device that already had the PROD build (same package name) looked
    "already installed", nothing was installed, and the prod (non-AltTester) app
    launched. Now, if the build on this device isn't the exact APK we intend, we
    uninstall whatever's there and install the correct one. Works across
    different devices / laptops, including over the bridge.
    """
    apk_path = get_latest_apk()
    logging.info(f"Using APK: {apk_path}")
    current_checksum = get_apk_checksum(apk_path)

    records = _load_install_records()
    installed = is_app_installed(PACKAGE_NAME, device_id)

    ours_here = False
    if installed:
        if records.get(device_id) == current_checksum:
            ours_here = True
        else:
            # No/old record for THIS device (e.g. first run under per-device
            # records, or the device was set up by another machine). Accept the
            # existing app if its version matches the APK we intend — this avoids
            # a needless uninstall + clean reinstall that wipes a working build
            # (which previously broke AltTester registration).
            want_vn, want_vc = get_apk_version(apk_path)
            have_vn, have_vc = get_installed_version(PACKAGE_NAME, device_id)
            if want_vc and have_vc and want_vc == have_vc and \
               (not want_vn or want_vn == have_vn):
                logging.info(
                    f"📦 {device_id} already has our version ({have_vn}/{have_vc}) "
                    f"→ trusting it (recording, no reinstall)"
                )
                ours_here = True
                records[device_id] = current_checksum
                _save_install_records(records)

    if ours_here:
        logging.info(f"📦 Correct AltTester APK already on {device_id} → skipping install")
        return

    if installed:
        vn, vc = get_installed_version(PACKAGE_NAME, device_id)
        logging.info(
            f"♻️ A different build is on {device_id} (version {vn}, code {vc}) — "
            f"not our AltTester APK → uninstalling it first"
        )
        uninstall_app(PACKAGE_NAME, device_id)
        records.pop(device_id, None)
    else:
        logging.info(f"📦 App not present on {device_id} → installing AltTester APK")

    logging.info("📦 Installing APK (may take a moment over WiFi / bridge)...")

    # Attempt 1: normal (streamed) install, allowing downgrade.
    ok, output = _adb_install_once(device_id, apk_path, [])
    if output:
        logging.info(f"   adb install → {output}")

    # Attempt 2: some devices / links (Android 16, flaky bridge) fail the
    # streamed path — retry pushing the APK first (--no-streaming).
    if not ok:
        logging.warning("⚠️ Install failed → retrying with --no-streaming...")
        ok, output = _adb_install_once(device_id, apk_path, ["--no-streaming"])
        if output:
            logging.info(f"   adb install (no-streaming) → {output}")

    if not ok:
        raise RuntimeError(f"❌ APK install failed: {output or '(no adb output)'}")

    # Record per-device AFTER confirmed success so a failed install never
    # makes us wrongly skip next time.
    records[device_id] = current_checksum
    _save_install_records(records)
    logging.info(f"✅ AltTester APK installed on {device_id}")


# -------------------------------
# LAUNCH GAME
# -------------------------------
def keep_screen_awake(device_id):
    """Stop the device screen from timing out / locking mid-run.

    A screen lock during a long 'complete' run steals focus and taps from the
    game, causing spurious test failures.  We apply three layers:
      • stay_on_while_plugged_in = 7  → never sleep on AC/USB/wireless charging
      • screen_off_timeout = max      → effectively never sleep (WiFi devices
                                         that aren't charging)
      • svc power stayon true         → keep the screen on while powered
    Then wake + unlock the screen so we start from an interactive state.
    """
    cmds = [
        ["settings", "put", "global", "stay_on_while_plugged_in", "7"],
        ["settings", "put", "system", "screen_off_timeout", "2147483647"],
        ["svc", "power", "stayon", "true"],
        ["input", "keyevent", "KEYCODE_WAKEUP"],
        ["wm", "dismiss-keyguard"],
    ]
    for c in cmds:
        try:
            subprocess.run(
                [ADB_PATH, "-s", device_id, "shell", *c],
                check=False, timeout=10
            )
        except Exception as e:
            logging.warning(f"⚠️ keep_screen_awake ({' '.join(c)}) failed: {e}")
    logging.info("🔆 Screen sleep/lock disabled for this run")


def launch_game(device_id):
    keep_screen_awake(device_id)

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
    
            collector = TestStepCollector(driver=driver)
    
            root_logger = logging.getLogger()
            root_logger.addHandler(collector)
    
            try:
                result = test_func(unity_driver, driver)

                # Tests report back in one of two ways:
                #   (a) return the (possibly refreshed) unity_driver object, or
                #   (b) return a result dict {"name","status","steps",...} when
                #       they catch their own exception internally instead of
                #       re-raising (e.g. Season Pass, Lucky Cards).
                # For (b) we MUST honor the dict's own status — otherwise a
                # self-caught failure gets logged as a false PASS.
                reported_status = "PASS"
                if isinstance(result, dict):
                    reported_status = str(
                        result.get("status", "PASS")
                    ).upper()
                    if reported_status not in ("PASS", "FAIL"):
                        reported_status = "FAIL"
                    # a test may hand back a refreshed driver inside the dict
                    ud = result.get("unity_driver")
                    if ud is not None and hasattr(ud, "wait_for_object"):
                        unity_driver = ud
                        logging.info("🔄 unity_driver updated from test return")
                elif result is not None and hasattr(result, 'wait_for_object'):
                    # allow tests to refresh unity driver
                    unity_driver = result
                    logging.info("🔄 unity_driver updated from test return")

                if reported_status == "PASS":
                    logging.info(f"✅ PASS: {display_name}")
                else:
                    logging.error(f"❌ FAIL: {display_name}")

                test_results.append({
                    "name": display_name,
                    "status": reported_status,
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
        device_name  = human_device_name(device_id)
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
        # Reverse port forwarding is intentionally LEFT ACTIVE after the run
        # (not torn down) so the device keeps routing 127.0.0.1:13000 → host.
        # teardown_reverse_forward(device_id)


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
    
    device_name = human_device_name(device_id)

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

    # Reverse port forwarding is intentionally LEFT ACTIVE after the run (not
    # torn down) so the device keeps routing 127.0.0.1:13000 → host.
    # teardown_reverse_forward(device_id)


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
    device_ids    = ", ".join(human_device_name(d) for d in devices)

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

    # Remember the last downloaded build so we don't re-download it.
    #
    # NOTE: we deliberately do NOT pass this as Slack's `oldest` param.
    # When `oldest` is set without `latest`, conversations.history pages
    # FORWARD from that timestamp — it returns the OLDEST messages after it,
    # not the newest. With a stale cache that means brand-new builds never
    # appear on the first page and get missed. Instead we always fetch the
    # most recent messages and compare timestamps client-side below.
    last_ts = None
    try:
        last_ts = open(SLACK_LAST_TS_FILE).read().strip() or None
    except FileNotFoundError:
        pass

    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params  = {"channel": SLACK_BUILD_CHANNEL, "limit": 30}

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
    # that is newer than the last build we already downloaded.
    for msg in messages:
        ts = msg.get("ts", "0")

        # Skip anything we've already downloaded (ts <= last downloaded ts)
        if last_ts and float(ts) <= float(last_ts):
            continue

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
                _download_slack_apk(f, headers, ts)
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
# NON-INTERACTIVE ENTRY (web GUI / CLI / scheduler)
# -------------------------------
def build_config_from_args():
    """
    Build a run_flow() config from command-line args / env — WITHOUT any
    interactive prompt.  Returns None when no run selection was passed, so the
    caller falls back to the interactive menu (select_run_type()).

    This is purely additive: `python run_this.py` with no args behaves exactly
    as before (interactive).  The web GUI / scheduler instead calls e.g.:

        python run_this.py --run-type complete --slack on --report on
        python run_this.py --test "Season Pass" --slack off --report on

    Report toggles are forwarded to report_manager via env vars so no report
    code needs run-specific arguments.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Sorry automation runner (non-interactive mode)"
    )
    parser.add_argument(
        "--run-type",
        choices=["smoke", "regression", "iap", "bat", "complete"],
        help="Single-device run type",
    )
    parser.add_argument(
        "--test",
        help="Run one test by registry name (case-insensitive) or 1-based index",
    )
    parser.add_argument("--slack", choices=["on", "off"], help="Send Slack report")
    parser.add_argument("--report", choices=["on", "off"], help="Generate HTML report")
    parser.add_argument("--screenshots", choices=["on", "off"],
                        help="Capture a screenshot per step (embedded in the HTML report)")
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="Print the test registry (index + name) and exit",
    )
    # parse_known_args so unrelated argv (e.g. from a launcher) never crashes us
    args, _ = parser.parse_known_args()

    if args.list_tests:
        for i, t in enumerate(TEST_REGISTRY, start=1):
            print(f"{i}\t{t['name']}")
        raise SystemExit(0)

    # Report checkboxes → env (report_manager reads these per-run)
    if args.slack is not None:
        os.environ["SAT_ENABLE_SLACK"] = "1" if args.slack == "on" else "0"
    if args.report is not None:
        os.environ["SAT_ENABLE_HTML"] = "1" if args.report == "on" else "0"
    if args.screenshots is not None:
        os.environ["SAT_SCREENSHOTS"] = "1" if args.screenshots == "on" else "0"
        # Screenshots are shown inside the HTML report — ensure it's generated.
        if args.screenshots == "on":
            os.environ["SAT_ENABLE_HTML"] = "1"

    # Individual test (by index or name)
    if args.test:
        selected = None
        if args.test.isdigit():
            idx = int(args.test) - 1
            if 0 <= idx < len(TEST_REGISTRY):
                selected = TEST_REGISTRY[idx]
        if selected is None:
            for t in TEST_REGISTRY:
                if t["name"].lower() == args.test.strip().lower():
                    selected = t
                    break
        if selected is None:
            raise SystemExit(f"❌ Unknown test: {args.test!r} (use --list-tests)")
        return {"mode": "individual", "test": selected}

    if args.run_type:
        return {"mode": "single", "run_type": args.run_type}

    # No run selection on the command line → caller uses the interactive menu
    return None


# -------------------------------
# ENTRY
# -------------------------------
if __name__ == "__main__":

    START_TIME = time.time()

    # Non-interactive selection (web GUI / CLI / scheduler) takes precedence;
    # with no run args this returns None and we fall back to the interactive
    # menu so the existing Eclipse "run" flow is unchanged.
    config = build_config_from_args()
    if config is None:
        config = select_run_type()

    # Check Slack for a new build after the user has made their selection.
    # Downloads the APK to APK_FOLDER if a matching file is found;
    # get_latest_apk() will pick it up automatically (newest by ctime).
    fetch_latest_build_from_slack()

    _exit_code = 0
    try:
        run_flow(config)

    except Exception as e:
        logging.error("❌ SCRIPT FAILED")
        logging.error(str(e))
        _exit_code = 1

    finally:

        end_time = time.time()
        total = end_time - START_TIME

        mins = int(total // 60)
        secs = int(total % 60)

        print("\n🏁 ALL TESTS FINISHED", flush=True)
        print(f"⏱️ TOTAL EXECUTION TIME: {mins}m {secs}s", flush=True)

    # Force the process to exit NOW. Appium / Mongo / AltTester websocket
    # keepalives can leave non-daemon threads running that would otherwise keep
    # this process alive after the run finishes — which left the web GUI stuck
    # showing the device as Busy (Stop active, timer running). The webapp
    # watches for this exit to flip the device back to Free.
    os._exit(_exit_code)