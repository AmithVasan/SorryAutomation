"""
test_07_pawn_sale.py
────────────────────
Legendary Pawn Sale IAP test.

Flow
────
1.  Navigate home and clear any open popups
2.  Tap Pawn Sale lobby widget icon
3.  Verify Pawn Sale modal opens
4.  Read pawn name (for logging)
5.  Confirm Buy button is visible
6.  Tap Buy → Google Play purchase sheet
7.  Handle Google Play payment (handle_google_play_purchase)
8.  Reconnect AltTester (game may have gone to background)
9.  Handle Purchase Success modal → tap Equip
10. Capture user snapshot and log newly equipped pawn

The test returns the updated unity_driver so run_this.py can
refresh the reference if needed.
"""

import time
import logging

from alttester import By
import utils.event_tracker as event_tracker

from utils.google_play_helper import (
    handle_google_play_purchase,
    reconnect_alttester,
)
from utils.state_manager import state
from utils.popup_handler import (
    clear_all_popups,
)
from utils.helpers import fast_text, get_user_snapshot
from utils.paths import (
    HOME_BUTTON,
    PAWN_SALE_MODAL,
    PAWN_SALE_CLOSE,
    PAWN_SALE_BUY,
    PAWN_SALE_NAME,
    PAWN_SALE_SUCCESS_MODAL,
    PAWN_SALE_EQUIP_BTN,
    HF_PAWN_ICON,
)


# -----------------------------------------------------------------------
# HELPER
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_pawn_sale(unity_driver, driver):
    """
    Run the Legendary Pawn Sale IAP purchase flow as a standalone test.
    Returns the (possibly refreshed) unity_driver.
    """
    logging.info("🛍️ ── test_07_pawn_sale START ──")

    # ------------------------------------------------------------------
    # 0. Refresh driver references from state (in case a previous test
    #    produced new sessions)
    # ------------------------------------------------------------------
    if driver is None:
        driver = state.get("appium_driver")

    if driver is None:
        raise RuntimeError("❌ [PawnSale] No Appium driver available")

    # ------------------------------------------------------------------
    # 1. Navigate home and clear any open popups
    # ------------------------------------------------------------------
    logging.info("🏠 Navigating to Home screen...")
    home_btn = _wait(unity_driver, HOME_BUTTON, 5)
    if home_btn:
        home_btn.tap()
        time.sleep(1)

    logging.info("🧹 Clearing popups before Pawn Sale flow...")
    clear_all_popups(unity_driver)

    # ------------------------------------------------------------------
    # 2. Tap Pawn Sale lobby widget icon
    #    Primary: full absolute path.
    #    Fallback: By.NAME — resilient to scroll-view object pooling
    #    after a game restart where the widget may not be instantiated
    #    at its expected hierarchy position.
    # ------------------------------------------------------------------
    logging.info("🛍️ Looking for Pawn Sale lobby widget...")
    pawn_icon = _wait(unity_driver, HF_PAWN_ICON, timeout=10)
    if not pawn_icon:
        logging.info("🔄 [PawnSale] Full path not found — trying By.NAME fallback")
        try:
            pawn_icon = unity_driver.find_object(By.NAME, "LegendaryPawnLobbyWidget")
        except Exception:
            pawn_icon = None

    if not pawn_icon:
        logging.warning(
            "⚠️ [PawnSale] Lobby widget not found — "
            "sale may be inactive or path needs updating in paths.py. "
            "Skipping Pawn Sale test."
        )
        event_tracker.record("IAP", "Pawn Sale", "SKIP")
        return unity_driver

    pawn_icon.tap()
    logging.info("✅ Pawn Sale icon tapped")
    time.sleep(2)

    # ------------------------------------------------------------------
    # 3. Verify modal opened
    # ------------------------------------------------------------------
    logging.info("🔍 Waiting for Pawn Sale modal...")
    modal = _wait(unity_driver, PAWN_SALE_MODAL, timeout=10)
    if not modal:
        raise Exception("❌ Pawn Sale modal did not open")
    logging.info("✅ Pawn Sale modal is open")

    # ------------------------------------------------------------------
    # 4. Read pawn name for logging
    # ------------------------------------------------------------------
    pawn_name = fast_text(unity_driver, PAWN_SALE_NAME) or "Unknown"
    logging.info(f"🎭 Pawn on sale: {pawn_name}")

    # ------------------------------------------------------------------
    # 5. Confirm Buy button is visible
    # ------------------------------------------------------------------
    buy_btn = _wait(unity_driver, PAWN_SALE_BUY, timeout=5)
    if not buy_btn:
        logging.warning(
            "⚠️ [PawnSale] Buy button not found — "
            "pawn may already be owned or sale is unavailable"
        )
        close = _wait(unity_driver, PAWN_SALE_CLOSE, 5)
        if close:
            close.tap()
            logging.info("✅ Pawn Sale modal closed (no buy button)")
        event_tracker.record("IAP", f"Pawn Sale ({pawn_name})", "SKIP")
        return unity_driver

    # ------------------------------------------------------------------
    # 6. Tap Buy button
    # ------------------------------------------------------------------
    buy_btn.tap()
    logging.info("✅ Pawn Sale buy tapped — Google Play opening...")
    time.sleep(3)

    # ------------------------------------------------------------------
    # 7. Handle Google Play purchase
    # ------------------------------------------------------------------
    gp_success, driver = handle_google_play_purchase(driver)

    status = "PASS" if gp_success else "FAIL"
    if gp_success:
        logging.info("✅ Google Play purchase completed")
    else:
        logging.warning(
            "⚠️ [PawnSale] Google Play purchase may not have completed"
        )

    event_tracker.record("IAP", f"Pawn Sale ({pawn_name})", status)

    # Update appium driver in state (may be a fresh session after crash-recovery)
    state.set("appium_driver", driver)

    # ------------------------------------------------------------------
    # 8. Reconnect AltTester
    #    Google Play pushes the game to the background; this brings it back.
    # ------------------------------------------------------------------
    unity_driver = reconnect_alttester(unity_driver)
    logging.info("🔄 AltTester reconnected after Pawn Sale purchase")
    state.set("unity_driver", unity_driver)

    # ------------------------------------------------------------------
    # 9. Handle Purchase Success modal → tap Equip
    # ------------------------------------------------------------------
    logging.info("🔍 Waiting for Pawn Sale Purchase Success Modal...")
    success_modal = _wait(unity_driver, PAWN_SALE_SUCCESS_MODAL, timeout=12)

    if success_modal:
        logging.info("✅ Purchase Success Modal detected")

        equip_btn = _wait(unity_driver, PAWN_SALE_EQUIP_BTN, timeout=5)
        if equip_btn:
            equip_btn.tap()
            logging.info(f"✅ Equip tapped — {pawn_name} equipped")
            time.sleep(2)
        else:
            logging.warning("⚠️ [PawnSale] Equip button not found in success modal")
    else:
        logging.warning(
            "⚠️ [PawnSale] Purchase Success Modal not found — continuing"
        )

    # ------------------------------------------------------------------
    # 10. Capture user snapshot and log newly equipped pawn
    # ------------------------------------------------------------------
    try:
        get_user_snapshot(unity_driver)
        equipped_pawn = state.user_info.get("equipped_pawn") or "Unknown"
        logging.info(f"🎭 Now equipped: {equipped_pawn}")
    except Exception as e:
        logging.warning(f"⚠️ [PawnSale] Could not fetch user snapshot: {e}")

    logging.info("🛍️ Pawn Sale purchase flow complete")

    return unity_driver
