"""
test_06_piggy_bank.py
─────────────────────
Dedicated Piggy Bank IAP test.

Flow
────
1. Suppress POPUP_PRIORITY auto-close for PIGGY_BANK_CLOSE (entire test)
2. Navigate home and clear any open popups
3. Tap Piggy Bank icon on Home screen
4. Verify Piggy Bank modal opens
5. Confirm Buy button is visible (bank not yet purchased)
6. Tap Buy → Google Play purchase sheet
7. Handle Google Play payment (handle_google_play_purchase)
8. Reconnect AltTester (game may have gone to background)
9. Tap claim screen (darkBG)
10. Close modal if it reappears after the claim animation
11. Re-enable POPUP_PRIORITY auto-close for future appearances (always, via finally)

The test returns the updated unity_driver so run_this.py can
refresh the reference if needed.
"""

import time
import logging

from alttester import By
import utils.popup_handler as popup_handler
import utils.event_tracker as event_tracker

from utils.google_play_helper import (
    handle_google_play_purchase,
    reconnect_alttester,
)
from utils.state_manager import state
from utils.popup_handler import (
    clear_all_popups,
    wait_for_safe,
)
from utils.paths import (
    HOME_BUTTON,
    PIGGY_BANK_ICON,
    PIGGY_BANK_MODAL,
    PIGGY_BANK_BUY,
    PIGGY_BANK_CLOSE,
    PIGGY_BANK_CLAIM_SCREEN,
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
def test_piggy_bank(unity_driver, driver):
    """
    Run the Piggy Bank IAP purchase flow as a standalone test.
    Returns the (possibly refreshed) unity_driver.
    """
    logging.info("🐷 ── test_06_piggy_bank START ──")

    # ------------------------------------------------------------------
    # 0. Refresh driver references from state (in case a previous test
    #    produced new sessions)
    # ------------------------------------------------------------------
    if driver is None:
        driver = state.get("appium_driver")

    if driver is None:
        raise RuntimeError("❌ [PiggyBank] No Appium driver available")

    # ------------------------------------------------------------------
    # 1. Suppress POPUP_PRIORITY auto-close for the entire test so the
    #    modal is never dismissed in the background while we navigate,
    #    wait for the icon, or process the purchase.
    #    unignore_popup is called in the finally block below — it fires
    #    on EVERY exit path (normal completion, early SKIP return, or
    #    any exception).
    # ------------------------------------------------------------------
    popup_handler.ignore_popup(PIGGY_BANK_CLOSE)

    try:
        # --------------------------------------------------------------
        # 2. Navigate home and clear any open popups
        # --------------------------------------------------------------
        logging.info("🏠 Navigating to Home screen...")
        home_btn = _wait(unity_driver, HOME_BUTTON, 5)
        if home_btn:
            home_btn.tap()
            time.sleep(1)

        logging.info("🧹 Clearing popups before Piggy Bank flow...")
        clear_all_popups(unity_driver)

        # --------------------------------------------------------------
        # 3. Tap Piggy Bank icon
        #    Primary: full absolute path.
        #    Fallback: By.NAME — resilient to scroll-view object pooling
        #    after a game restart where the widget may not be instantiated
        #    at its expected hierarchy position.
        # --------------------------------------------------------------
        logging.info("🐷 Tapping Piggy Bank icon...")
        pb_icon = _wait(unity_driver, PIGGY_BANK_ICON, timeout=10)
        if not pb_icon:
            logging.info("🔄 [PiggyBank] Full path not found — trying By.NAME fallback")
            try:
                pb_icon = unity_driver.find_object(By.NAME, "PiggyBankWidget")
            except Exception:
                pb_icon = None

        if not pb_icon:
            logging.warning(
                "⚠️ [PiggyBank] Icon not found on Home screen — "
                "widget may be hidden or path needs updating in paths.py. "
                "Skipping Piggy Bank test."
            )
            event_tracker.record("IAP", "Piggy Bank", "SKIP")
            return unity_driver  # finally block still fires → unignore_popup

        pb_icon.tap()
        logging.info("✅ Piggy Bank icon tapped")
        time.sleep(2)

        # --------------------------------------------------------------
        # 4. Verify modal opened
        # --------------------------------------------------------------
        logging.info("🔍 Waiting for Piggy Bank modal...")
        modal = _wait(unity_driver, PIGGY_BANK_MODAL, timeout=10)
        if not modal:
            raise Exception("❌ Piggy Bank modal did not open")
        logging.info("✅ Piggy Bank modal is open")

        # --------------------------------------------------------------
        # 5. Check Buy button is present (bank not yet purchased)
        # --------------------------------------------------------------
        buy_btn = _wait(unity_driver, PIGGY_BANK_BUY, timeout=5)
        if not buy_btn:
            logging.warning(
                "⚠️ [PiggyBank] Buy button not found — "
                "Piggy Bank may already be purchased or unavailable"
            )
            # Close modal gracefully and exit
            close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
            if close:
                close.tap()
                logging.info("✅ Piggy Bank modal closed (no buy button)")
            event_tracker.record("IAP", "Piggy Bank", "SKIP")
            return unity_driver  # finally block still fires → unignore_popup

        # --------------------------------------------------------------
        # 6. Tap Buy button
        # --------------------------------------------------------------
        buy_btn.tap()
        logging.info("✅ Piggy Bank buy tapped — Google Play opening...")
        time.sleep(3)

        # --------------------------------------------------------------
        # 7. Handle Google Play purchase
        # --------------------------------------------------------------
        gp_success, driver = handle_google_play_purchase(driver)

        status = "PASS" if gp_success else "FAIL"
        if gp_success:
            logging.info("✅ Google Play purchase completed")
        else:
            logging.warning(
                "⚠️ [PiggyBank] Google Play purchase may not have completed"
            )

        event_tracker.record("IAP", "Piggy Bank", status)

        # Update appium driver in state (may be a fresh session after crash-recovery)
        state.set("appium_driver", driver)

        # --------------------------------------------------------------
        # 8. Reconnect AltTester
        #    Google Play pushes the game to the background; this brings it back.
        # --------------------------------------------------------------
        unity_driver = reconnect_alttester(unity_driver)
        logging.info("🔄 AltTester reconnected after Piggy Bank purchase")
        state.set("unity_driver", unity_driver)

        # --------------------------------------------------------------
        # 9. Tap claim screen (darkBG) to collect coins
        # --------------------------------------------------------------
        logging.info("🔍 Waiting for Piggy Bank claim screen...")
        claim = _wait(unity_driver, PIGGY_BANK_CLAIM_SCREEN, timeout=15)
        if claim:
            claim.tap()
            logging.info("✅ Piggy Bank claim screen tapped")
            time.sleep(2)   # let claim animation finish
        else:
            logging.warning(
                "⚠️ [PiggyBank] Claim screen not found — continuing"
            )

        # --------------------------------------------------------------
        # 10. Close modal if it reappears after claim animation
        # --------------------------------------------------------------
        reappear = _wait(unity_driver, PIGGY_BANK_MODAL, timeout=5)
        if reappear:
            close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
            if close:
                close.tap()
                logging.info("✅ Piggy Bank modal closed after purchase")
                time.sleep(1)
        else:
            logging.info(
                "ℹ️ Piggy Bank modal did not reappear — nothing to close"
            )

        logging.info("🐷 Piggy Bank purchase flow complete")

    finally:
        # ------------------------------------------------------------------
        # 11. Re-enable POPUP_PRIORITY so any future Piggy Bank appearances
        #     are auto-closed without entering the purchase flow again.
        #     Fires on every exit path: normal completion, SKIP return,
        #     or any exception raised above.
        # ------------------------------------------------------------------
        popup_handler.unignore_popup(PIGGY_BANK_CLOSE)

    return unity_driver
