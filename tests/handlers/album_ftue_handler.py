import time
import logging
from alttester import By

from utils.ui_helpers import wait_for_safe, safe_tap
from utils import popup_handler
from utils.popup_handler import handle_one_popup
import utils.event_tracker as event_tracker

# -------------------------------
# PATHS
# -------------------------------
ALBUM_POPUP     = "/Canvas/ModalLayer/CardCollectionNewAlbumPopup(Clone)/root/content/visitAlbumButton/TouchArea"
VISIT_ALBUM     = "/Canvas/ModalLayer/CardCollectionNewAlbumPopup(Clone)/root/content/visitAlbumButton/TouchArea"
PACK_OPEN_BTN   = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/openPackWidget(Clone)/TouchArea"
PACK_SCREEN_BTN = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/cardCollectionCardPack2(Clone)/root/PackIcon"
CLOSE_BTN       = "/Canvas/uiLayer/TableManager/layout/viewPort/content/cardCollectionAlbumModal/rootMain/packOpenScreen/closeButton/packOpenScreenCloseBtn/touchArea"
HOME_ICON       = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon"


# -------------------------------
# DETECTION
# -------------------------------
def is_present(unity_driver, driver=None):
    try:
        obj = unity_driver.wait_for_object(By.PATH, ALBUM_POPUP, timeout=0.5)
        return obj is not None
    except Exception:
        return False


# -------------------------------
# HANDLER
# -------------------------------
def handle(unity_driver, driver=None):
    logging.info("📚 Album FTUE detected → Handling flow")

    # STEP 1: Tap Visit Album
    logging.info("   1️⃣ Tapping Visit Album...")
    visit_btn = wait_for_safe(unity_driver, By.PATH, VISIT_ALBUM, 8)
    if not visit_btn:
        logging.warning("⚠️ Visit Album button not found — skipping Album FTUE")
        event_tracker.record("FTUE", "Album FTUE", "FAIL")
        return False
    safe_tap(unity_driver, visit_btn)
    time.sleep(2)

    # STEP 2: Tap Card Packs Open Button
    logging.info("   2️⃣ Tapping Card Packs Open Button...")
    pack_open_btn = wait_for_safe(unity_driver, By.PATH, PACK_OPEN_BTN, 8)
    if not pack_open_btn:
        logging.warning("⚠️ Card Packs Open button not found")
        return False
    safe_tap(unity_driver, pack_open_btn)
    time.sleep(2)

    # STEP 3: Tap Card Screen Pack Open Button
    logging.info("   3️⃣ Tapping Card Screen Pack Open Button...")
    pack_screen_btn = wait_for_safe(unity_driver, By.PATH, PACK_SCREEN_BTN, 8)
    if not pack_screen_btn:
        logging.warning("⚠️ Card Screen Pack Open button not found")
        return False
    safe_tap(unity_driver, pack_screen_btn)
    time.sleep(2)

    # STEP 4: Tap Card Screen Close Button
    logging.info("   4️⃣ Tapping Card Screen Close Button...")
    close_btn = wait_for_safe(unity_driver, By.PATH, CLOSE_BTN, 8)
    if not close_btn:
        logging.warning("⚠️ Card Screen Close button not found")
        return False
    safe_tap(unity_driver, close_btn)
    time.sleep(2)

    # STEP 5: Handle any random popups before going home
    logging.info("   5️⃣ Clearing any popups...")
    popup_handler.fast_clear_popups(unity_driver)

    # STEP 6: Tap Home Icon to return to lobby
    logging.info("   6️⃣ Tapping Home Icon → returning to lobby...")
    end = time.time() + 30
    while time.time() < end:
        handle_one_popup(unity_driver)

        home_btn = wait_for_safe(unity_driver, By.PATH, HOME_ICON, 2)
        if home_btn:
            safe_tap(unity_driver, home_btn)
            logging.info("   ✅ Back in lobby")
            time.sleep(2)
            break

        time.sleep(0.5)
    else:
        logging.warning("⚠️ Could not find Home Icon after Album FTUE")
        return False

    event_tracker.record("FTUE", "Album FTUE", "PASS")
    logging.info("✅ Album FTUE completed — resuming script")
    return True