import logging
from alttester import By

import utils.event_tracker as event_tracker
from utils.paths import INFO_SCREENS
from utils.popup_handler import wait_for_safe, safe_tap


# -----------------------------------------------------------------------
# INFO SCREEN HANDLER
#
# Handles any "tap anywhere to close" info overlay.
# The full list of screens lives in utils/paths.py → INFO_SCREENS.
# To add a new screen just append a tuple there — no changes needed here.
# -----------------------------------------------------------------------


def is_present(unity_driver, driver=None):
    """Return True as soon as any info screen element is visible."""
    for _, path in INFO_SCREENS:
        if wait_for_safe(unity_driver, By.PATH, path, 1):
            return True
    return False


def handle(unity_driver, driver=None):
    """
    Find the first visible info screen, tap it to close, record it,
    and return True.  Returns False if nothing is found.
    """
    for name, path in INFO_SCREENS:
        obj = wait_for_safe(unity_driver, By.PATH, path, 1)
        if obj:
            logging.info(f"📋 Info Screen detected → tapping to close: {name}")
            safe_tap(unity_driver, obj)
            event_tracker.record(
                "Info Screens", name, status="PASS", dedup=True
            )
            logging.info(f"✅ {name} closed")
            return True
    return False
