import time
import logging
from alttester import By


# 🔥 High priority (runs early)
PRIORITY = 1

HANDLER_NAME = "Facebook Connect Popup"


# -------------------------------
# DETECTION
# -------------------------------
def is_present(unity_driver, driver):
    popup_path = "/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/darkbg"

    # ✅ Primary: exact path
    try:
        obj = unity_driver.wait_for_object(By.PATH, popup_path, timeout=0.5)
        if obj:
            return obj
    except:
        pass

    # 🔥 Fallback: scan by name (ultra-stable)
    try:
        objs = unity_driver.find_objects_by_component("CanvasGroup")

        for o in objs:
            try:
                name = o.name.lower()
                if "facebook" in name or "connecttofacebook" in name:
                    logging.info("🧠 FB popup detected via fallback scan")
                    return o
            except:
                continue
    except:
        pass

    return None


# -------------------------------
# HANDLER
# -------------------------------
def handle(unity_driver, driver):
    close_path = "/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea"

    logging.info("📘 FB Popup detected → Closing...")

    for i in range(3):  # retry safety
        # ✅ Primary: exact close button path
        try:
            close_btn = unity_driver.wait_for_object(By.PATH, close_path, timeout=1)

            if close_btn:
                close_btn.tap()
                logging.info("❌ FB Popup closed via primary path")
                time.sleep(1)
                return True

        except Exception as e:
            logging.warning(f"⚠️ Primary close failed ({i+1}): {e}")

        # 🔥 Fallback: scan for clickable button
        try:
            buttons = unity_driver.find_objects_by_component("Button")

            for btn in buttons:
                try:
                    name = btn.name.lower()

                    if "close" in name or "cancel" in name or "no" in name:
                        btn.tap()
                        logging.info("❌ FB Popup closed via fallback button")
                        time.sleep(1)
                        return True
                except:
                    continue

        except Exception as e:
            logging.warning(f"⚠️ Fallback scan failed ({i+1}): {e}")

        time.sleep(1)

    logging.warning("⚠️ Failed to close FB popup")
    return False