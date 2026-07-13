import time
import logging
from alttester import By


def wait_for_safe(unity_driver, by, value, timeout=6):
    try:
        return unity_driver.wait_for_object(by, value, timeout=timeout)
    except:
        return None


def safe_tap(unity_driver, obj):
    if not obj:
        raise Exception("❌ Cannot tap → object is None")

    try:
        obj.tap()
        time.sleep(0.2)
    except Exception as e:
        logging.error(f"[safe_tap] Failed: {e}")
        raise


def fast_wait(unity_driver, path, timeout=1):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except:
        return None