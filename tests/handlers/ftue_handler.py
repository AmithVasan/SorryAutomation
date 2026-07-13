import logging
from alttester import By
import utils.event_tracker as event_tracker


# -------------------------------
# DETECT FTUE
# -------------------------------
def is_present(unity_driver, driver):
    try:
        unity_driver.wait_for_object(
            By.PATH,
            "/Canvas/ModalLayer/BuildFTUEModal(Clone)/skipGrp/closeCTA/TouchArea",
            timeout=2
        )
        return True
    except:
        return False


# -------------------------------
# HANDLE FTUE
# -------------------------------
def handle(unity_driver, driver=None):
    logging.info("⚡ FTUE detected → Skipping")

    try:
        skip_btn = unity_driver.wait_for_object(
            By.PATH,
            "/Canvas/ModalLayer/BuildFTUEModal(Clone)/skipGrp/closeCTA/TouchArea",
            timeout=5
        )

        skip_btn.tap()

        event_tracker.record("FTUE", "Build FTUE", "PASS")
        logging.info("✅ FTUE skipped successfully")

    except Exception as e:
        event_tracker.record("FTUE", "Build FTUE", "FAIL")
        logging.error(f"❌ FTUE handling failed: {e}")