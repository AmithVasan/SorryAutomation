import time
import logging


ALLOW_IDS = [
    "com.android.permissioncontroller:id/permission_allow_button",
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
    "com.android.packageinstaller:id/permission_allow_button",
]


def is_present(unity_driver, driver):
    for btn_id in ALLOW_IDS:
        try:
            btn = driver.find_element("id", btn_id)
            if btn:
                return btn
        except:
            continue
    return None


def handle(unity_driver, driver):
    logging.info("🔐 Permission popup detected → Allowing...")

    for btn_id in ALLOW_IDS:
        try:
            btn = driver.find_element("id", btn_id)
            if btn:
                btn.click()
                logging.info(f"✅ Permission allowed via {btn_id}")
                time.sleep(1)
                return True
        except:
            continue

    logging.warning("⚠️ Permission popup found but not clickable")
    return False