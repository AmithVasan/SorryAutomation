import time
import logging

from alttester import By
from utils.state_manager import state
import utils.event_tracker as event_tracker
import utils.popup_handler as popup_handler
from utils.paths import (
    PIGGY_BANK_MODAL,
    PIGGY_BANK_BUY,
    PIGGY_BANK_CLOSE,
    PIGGY_BANK_CLAIM_SCREEN,
)

__name__ = "piggy_bank_handler"


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


# -----------------------------------------------------------------------
# DETECTION
# Only True when the Buy button is visible — i.e. the Piggy Bank has not
# been purchased yet this session.  After purchase the buy button is gone
# so is_present returns False and POPUP_PRIORITY handles any repeat close.
# -----------------------------------------------------------------------
def is_present(unity_driver, driver=None):
    return _wait(unity_driver, PIGGY_BANK_BUY, 2) is not None


# -----------------------------------------------------------------------
# HANDLER
# Lazy-imports from test_03_shop to avoid circular import at module load.
# Returns (unity_driver, driver) — both may be new sessions after IAP.
# Also stores updated drivers in state so callers that can't unpack the
# return value can still refresh via state.get("unity_driver") /
# state.get("appium_driver").
# -----------------------------------------------------------------------
def handle(unity_driver, driver=None):

    from utils.google_play_helper import (
        handle_google_play_purchase,
        reconnect_alttester,
    )

    # Fall back to state-stored driver if not passed (e.g. registry calls)
    if driver is None:
        driver = state.get("appium_driver")

    if driver is None:
        logging.warning(
            "⚠️ [PiggyBank] No Appium driver available — closing modal without buying"
        )
        close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
        if close:
            close.tap()
        return unity_driver, None

    logging.info("🐷 Piggy Bank detected — starting purchase flow")

    # Keep POPUP_PRIORITY from auto-closing the modal while we buy
    popup_handler.ignore_popup(PIGGY_BANK_CLOSE)

    try:
        # -------------------------------------------------------------------
        # Tap Buy button
        # -------------------------------------------------------------------
        buy_btn = _wait(unity_driver, PIGGY_BANK_BUY, 8)
        if not buy_btn:
            logging.warning("⚠️ [PiggyBank] Buy button not found — closing modal")
            close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
            if close:
                close.tap()
            return unity_driver, driver

        buy_btn.tap()
        logging.info("✅ Piggy Bank buy tapped — Google Play opening...")
        time.sleep(3)

        # -------------------------------------------------------------------
        # Handle Google Play purchase
        # -------------------------------------------------------------------
        gp_success, driver = handle_google_play_purchase(driver)

        status = "PASS" if gp_success else "FAIL"
        if gp_success:
            logging.info("✅ Google Play purchase completed")
        else:
            logging.warning(
                "⚠️ [PiggyBank] Google Play purchase may not have completed"
            )

        event_tracker.record("Shop", "Piggy Bank", status)

        # -------------------------------------------------------------------
        # Reconnect AltTester
        # Google Play pushes the game to background; reconnect brings it back.
        # -------------------------------------------------------------------
        unity_driver = reconnect_alttester(unity_driver)
        logging.info("🔄 AltTester reconnected after Piggy Bank purchase")

        # Store updated drivers so other callers can retrieve them from state
        state.set("unity_driver", unity_driver)
        state.set("appium_driver", driver)

        # -------------------------------------------------------------------
        # Piggy Bank Claim Screen
        # Tap anywhere on darkBG to collect; 2-second animation follows.
        # -------------------------------------------------------------------
        logging.info("🔍 Waiting for Piggy Bank claim screen...")
        claim_screen = _wait(unity_driver, PIGGY_BANK_CLAIM_SCREEN, 15)
        if claim_screen:
            claim_screen.tap()
            logging.info("✅ Piggy Bank claim screen tapped")
            time.sleep(2)   # let claim animation finish
        else:
            logging.warning(
                "⚠️ [PiggyBank] Claim screen not found — continuing"
            )

        # -------------------------------------------------------------------
        # Close modal if it reappears after the claim animation
        # -------------------------------------------------------------------
        reappear = _wait(unity_driver, PIGGY_BANK_MODAL, 5)
        if reappear:
            close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
            if close:
                close.tap()
                logging.info("✅ Piggy Bank modal closed after purchase")
                time.sleep(1)
        else:
            logging.info("ℹ️ Piggy Bank modal did not reappear — nothing to close")

        logging.info("🐷 Piggy Bank purchase flow complete")

    finally:
        # Always re-enable POPUP_PRIORITY so any future appearances are
        # auto-closed without going through the full purchase flow again.
        popup_handler.unignore_popup(PIGGY_BANK_CLOSE)

    return unity_driver, driver
