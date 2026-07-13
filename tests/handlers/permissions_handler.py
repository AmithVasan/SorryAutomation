import time
import logging


ALLOW_IDS = [

    # Android 10+
    "com.android.permissioncontroller:id/permission_allow_button",

    # Android 11+
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",

    # Android 12+
    "com.android.permissioncontroller:id/permission_allow_one_time_button",

    # Older Android
    "com.android.packageinstaller:id/permission_allow_button",

    # Continue
    "com.android.permissioncontroller:id/continue_button",

    # Generic OK
    "android:id/button1",
]


def is_present(unity_driver, driver):

    for btn_id in ALLOW_IDS:

        try:
            elements = driver.find_elements("id", btn_id)

            if elements:
                return elements[0]

        except Exception:
            continue

    return None


def handle(unity_driver, driver):

    handled = False

    for btn_id in ALLOW_IDS:

        try:
            elements = driver.find_elements("id", btn_id)

            if elements:

                elements[0].click()

                logging.info(
                    f"✅ Android Permission Allowed → {btn_id}"
                )

                time.sleep(1)

                handled = True

        except Exception:
            continue

    return handled


def start_permission_watcher(unity_driver, driver, stop_event):

    logging.info("👀 Permission watcher started")

    while not stop_event.is_set():

        try:
            handle(unity_driver, driver)
        except Exception:
            pass

        time.sleep(2)