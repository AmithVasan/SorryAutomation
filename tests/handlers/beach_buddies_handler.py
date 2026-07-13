import time
import logging
import subprocess

from alttester import By
from config import ADB_PATH
from utils.state_manager import state
from utils.helpers import fast_text, parse_amount
import utils.event_tracker as event_tracker
from utils.paths import (
    BB_START_MODAL, BB_LETS_GO,
    BB_SCREEN, BB_INVITE_ICON,
    BB_INVITE_MODAL, BB_ACCEPT_INVITE,
    BB_SEND_INVITE, BB_SEND_ALL, BB_INVITE_CLOSE,
    BB_CASTLE_1, BB_CASTLE_2,
    BB_FREE_AMMO_MODAL, BB_FREE_AMMO_COUNT, BB_AWESOME_BTN,
    BB_FTUE_SPIN_WHEEL, BB_SPIN_MULTIPLIER,
    BB_SPIN_WHEEL, BB_CLOSE,
    HOME_BUTTON,
)

__name__ = "beach_buddies_handler"


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _tap_center():
    """Raw ADB screen center tap — for 'tap anywhere' screens."""
    device_id = state.get("device_id")
    if not device_id:
        logging.warning("⚠️ [BeachBuddies] device_id not in state — cannot ADB tap")
        return
    subprocess.run([
        ADB_PATH, "-s", device_id,
        "shell", "input", "tap", "540", "1200"
    ])


# -----------------------------------------------------------------------
# DETECTION
# -----------------------------------------------------------------------
def is_present(unity_driver, driver=None):
    return _wait(unity_driver, BB_START_MODAL, timeout=2) is not None


# -----------------------------------------------------------------------
# HANDLER
# -----------------------------------------------------------------------
def handle(unity_driver, driver=None):
    logging.info("🏖️ Beach Buddies FTUE detected — starting flow")

    # -------------------------------------------------------------------
    # STEP 1 — Tap "Let's Go" on start popup
    # -------------------------------------------------------------------
    lets_go = _wait(unity_driver, BB_LETS_GO, 8)
    if lets_go:
        lets_go.tap()
        logging.info("✅ Beach Buddies Lets GO tapped")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Lets GO button not found — aborting")
        event_tracker.record("FTUE", "Beach Buddies", "FAIL")
        return False

    # -------------------------------------------------------------------
    # STEP 2 — Tap Invite Friend icon on beach buddies screen
    # -------------------------------------------------------------------
    invite_icon = _wait(unity_driver, BB_INVITE_ICON, 8)
    if invite_icon:
        invite_icon.tap()
        logging.info("✅ Beach Buddies Invite icon tapped")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Invite Friend icon not found — aborting")
        return False

    # -------------------------------------------------------------------
    # STEP 3 — Accept friend invite in Invite Friends Modal
    # -------------------------------------------------------------------
    invite_modal = _wait(unity_driver, BB_INVITE_MODAL, 8)
    if invite_modal:
        logging.info("✅ Invite Friends Modal detected")
        accept = _wait(unity_driver, BB_ACCEPT_INVITE, 5)
        if accept:
            accept.tap()
            logging.info("✅ Friend invite accepted")
            time.sleep(2)
        else:
            logging.warning("⚠️ [BeachBuddies] Accept invite button not found")
    else:
        logging.warning("⚠️ [BeachBuddies] Invite Friends Modal not found")

    # -------------------------------------------------------------------
    # STEP 4 — Tap Castle 1
    # -------------------------------------------------------------------
    castle1 = _wait(unity_driver, BB_CASTLE_1, 8)
    if castle1:
        castle1.tap()
        logging.info("✅ Castle 1 tapped")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Castle 1 not found")

    # -------------------------------------------------------------------
    # STEP 5 — Free Ammo Modal: read ammo count → tap Awesome
    # -------------------------------------------------------------------
    free_ammo_modal = _wait(unity_driver, BB_FREE_AMMO_MODAL, 8)
    if free_ammo_modal:
        ammo_text = fast_text(unity_driver, BB_FREE_AMMO_COUNT) or "0"
        ammo = parse_amount(ammo_text)
        logging.info(f"🎯 Free ammo received: {ammo}")

        awesome = _wait(unity_driver, BB_AWESOME_BTN, 5)
        if awesome:
            awesome.tap()
            logging.info("✅ Awesome button tapped")
            time.sleep(2)  # animation after awesome
        else:
            logging.warning("⚠️ [BeachBuddies] Awesome button not found")
    else:
        logging.warning("⚠️ [BeachBuddies] Free Ammo Modal not found")

    # -------------------------------------------------------------------
    # STEP 6 — FTUE Spin Wheel (CommonNudgeModal)
    # -------------------------------------------------------------------
    ftue_spin = _wait(unity_driver, BB_FTUE_SPIN_WHEEL, 8)
    if ftue_spin:
        ftue_spin.tap()
        logging.info("✅ FTUE Spin Wheel tapped")
        time.sleep(2)  # spin animation
    else:
        logging.warning("⚠️ [BeachBuddies] FTUE Spin Wheel not found")

    # -------------------------------------------------------------------
    # STEP 7 — Tap Spin Multiplier
    # -------------------------------------------------------------------
    multiplier = _wait(unity_driver, BB_SPIN_MULTIPLIER, 8)
    if multiplier:
        multiplier.tap()
        logging.info("✅ Spin Multiplier tapped")
        time.sleep(1)
    else:
        logging.warning("⚠️ [BeachBuddies] Spin Multiplier not found")

    # -------------------------------------------------------------------
    # STEP 8 — Spin Wheel again (CoOpEventMainModal)
    # -------------------------------------------------------------------
    spin_wheel = _wait(unity_driver, BB_SPIN_WHEEL, 8)
    if spin_wheel:
        spin_wheel.tap()
        logging.info("✅ Spin Wheel tapped")
        time.sleep(5)  # spin animation takes ~5s
    else:
        logging.warning("⚠️ [BeachBuddies] Spin Wheel not found")

    # -------------------------------------------------------------------
    # STEP 9 — Close Castle Build (CoOpEventMainModal close)
    # -------------------------------------------------------------------
    castle_close = _wait(unity_driver, BB_CLOSE, 8)
    if castle_close:
        castle_close.tap()
        logging.info("✅ Castle Build closed")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Castle Build close button not found")

    # -------------------------------------------------------------------
    # STEP 10 — Tap Castle 2 on beach buddies screen
    # -------------------------------------------------------------------
    castle2 = _wait(unity_driver, BB_CASTLE_2, 8)
    if castle2:
        castle2.tap()
        logging.info("✅ Castle 2 tapped")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Castle 2 not found")

    # -------------------------------------------------------------------
    # STEP 11 — Invite Friends Modal: send invite → send all → close
    #
    # NOTE: the "deny friend invite" step was intentionally removed here.
    # Denying an incoming invite consumed one of the invites that the
    # Beach Buddies test later relies on to open the final castle, leaving
    # it with no invite to accept.  Leaving invites intact lets the test
    # complete all castles.
    # -------------------------------------------------------------------
    invite_modal2 = _wait(unity_driver, BB_INVITE_MODAL, 8)
    if invite_modal2:
        logging.info("✅ Invite Friends Modal (Castle 2) detected")

        send = _wait(unity_driver, BB_SEND_INVITE, 5)
        if send:
            send.tap()
            logging.info("✅ Friend invite sent")
            time.sleep(1)
        else:
            logging.warning("⚠️ [BeachBuddies] Send invite button not found")

        send_all = _wait(unity_driver, BB_SEND_ALL, 5)
        if send_all:
            send_all.tap()
            logging.info("✅ Send All tapped")
            time.sleep(1)
        else:
            logging.warning("⚠️ [BeachBuddies] Send All button not found")

        invite_close = _wait(unity_driver, BB_INVITE_CLOSE, 5)
        if invite_close:
            invite_close.tap()
            logging.info("✅ Invite Friends Modal closed")
            time.sleep(2)
        else:
            logging.warning("⚠️ [BeachBuddies] Invite close button not found")
    else:
        logging.warning("⚠️ [BeachBuddies] Invite Friends Modal (Castle 2) not found")

    # -------------------------------------------------------------------
    # STEP 12 — Close Beach Buddies Screen
    # -------------------------------------------------------------------
    bb_close = _wait(unity_driver, BB_CLOSE, 8)
    if bb_close:
        bb_close.tap()
        logging.info("✅ Beach Buddies screen closed")
        time.sleep(2)
    else:
        logging.warning("⚠️ [BeachBuddies] Beach Buddies close button not found")

    event_tracker.record("FTUE", "Beach Buddies", "PASS")
    logging.info("🏖️ Beach Buddies FTUE flow complete")
    return True
