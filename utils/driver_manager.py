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
def connect_altunity(alt_port=13000, retries=5):
    ALT_HOST = "127.0.0.1"

    wait_for_altserver(host=ALT_HOST, port=alt_port)

    for attempt in range(retries):
        try:
            logging.info(f"AltUnity connection attempt {attempt + 1} → {ALT_HOST}:{alt_port}")
            unity_driver = AltDriver(host=ALT_HOST, port=alt_port, app_name="sorry")
            logging.info("✅ AltUnity connected successfully")
            return unity_driver
        except Exception as e:
            logging.warning(f"⚠️ AltUnity attempt {attempt + 1} failed: {e}")
            time.sleep(3)

    raise Exception("❌ AltTester connection failed after retries")


# -------------------------------
# SET UP DRIVERS
# -------------------------------
def set_driver(
    device_id,
    app_package,
    app_activity,
    alt_port=13000,
    connect_alt=True
):
    options = UiAutomator2Options()
    options.set_capability("platformName", "Android")
    options.set_capability("automationName", "UiAutomator2")
    options.set_capability("deviceName", device_id)
    options.set_capability("appPackage", app_package)
    options.set_capability("appActivity", app_activity)
    options.set_capability("noReset", True)
    options.set_capability("newCommandTimeout", 300)

    logging.info("🚀 Starting Appium driver...")

    driver = webdriver.Remote(
        command_executor="http://127.0.0.1:4723",
        options=options
    )

    logging.info("✅ Appium driver ready")

    unity_driver = None

    if connect_alt:
        unity_driver = connect_altunity(alt_port)

    return driver, unity_driver