import os
import logging
import socket
import time
from appium import webdriver
from appium.options.android import UiAutomator2Options
from alttester import AltDriver


# -------------------------------
# LOCAL IP
# -------------------------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


# -------------------------------
# WAIT FOR ALTTESTER SERVER
# -------------------------------
def wait_for_altserver(host="127.0.0.1", port=13000, timeout=40):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                logging.info("✅ AltTester Desktop server is reachable")
                return True
        except Exception as e:
            logging.debug(f"AltTester not ready yet: {e}")
            time.sleep(2)

    logging.warning("⚠️ AltTester Desktop server not reachable")
    return False


# -------------------------------
# CONNECT ALTTESTER
# -------------------------------
def connect_altunity(alt_port=13000, app_name="sorry", retries=15, host=None):
    # AltTester server host. Defaults to 127.0.0.1 (server runs on THIS machine
    # — the current local setup, unchanged). Set env SAT_ALT_HOST to a central
    # server's LAN IP to drive a device on this laptop against a shared,
    # licensed AltTester server elsewhere on the office LAN.
    ALT_HOST = host or os.getenv("SAT_ALT_HOST", "127.0.0.1")

    wait_for_altserver(host=ALT_HOST, port=alt_port)

    for attempt in range(retries):
        try:
            logging.info(f"AltUnity connection attempt {attempt + 1} → {ALT_HOST}:{alt_port} (app={app_name})")
            unity_driver = AltDriver(host=ALT_HOST, port=alt_port, app_name=app_name)
            logging.info("✅ AltUnity connected successfully")
            return unity_driver
        except Exception as e:
            logging.warning(f"⚠️ AltUnity attempt {attempt + 1} failed: {e}")
            time.sleep(5)

    raise Exception("❌ AltTester connection failed after retries")


# -------------------------------
# SET UP DRIVERS
# -------------------------------
def set_driver(
    device_id,
    app_package,
    app_activity,
    alt_port=13000,
    connect_alt=True,
    app_name="sorry",
    system_port=None,
):
    options = UiAutomator2Options()
    options.set_capability("platformName", "Android")
    options.set_capability("automationName", "UiAutomator2")
    options.set_capability("deviceName", device_id)
    options.set_capability("appPackage", app_package)
    options.set_capability("appActivity", app_activity)
    options.set_capability("noReset", True)

    # Parallel runs: two UiAutomator2 sessions on ONE Appium server must use
    # DIFFERENT systemPorts (default 8200), else the second session clobbers the
    # first. The webapp assigns one per concurrent slot (SAT_SYSTEM_PORT).
    sp = system_port or os.getenv("SAT_SYSTEM_PORT")
    if sp:
        options.set_capability("systemPort", int(sp))
        logging.info(f"🔌 Appium systemPort = {sp}")
    # Long AltTester-only tests (e.g. Happy Flow) never send an Appium command
    # for several minutes.  A short newCommandTimeout lets the UiAutomator2
    # server KILL the idle session, so the next Google Play purchase fails with
    # an "invalid session id" error.  Keep it high so the session survives the
    # whole suite; the purchase flow revives it defensively regardless.
    options.set_capability("newCommandTimeout", 3600)

    # Remote-device mode (Phase 2): Appium runs on the laptop next to the device
    # (via SAT_APPIUM_URL), so its adb is LOCAL and already sees the device —
    # we just pin the exact device by udid. No-op for local runs.
    if os.getenv("SAT_ADB_HOST") or os.getenv("SAT_DEVICE_ID"):
        options.set_capability("udid", device_id)
        logging.info(f"🌐 Remote-device mode → pinned udid {device_id}")

    appium_url = os.getenv("SAT_APPIUM_URL", "http://127.0.0.1:4723")
    logging.info(f"🚀 Starting Appium driver ({appium_url})...")

    driver = webdriver.Remote(
        command_executor=appium_url,
        options=options
    )

    logging.info("✅ Appium driver ready")

    unity_driver = None

    if connect_alt:
        unity_driver = connect_altunity(alt_port, app_name=app_name)

    return driver, unity_driver