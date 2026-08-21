import os
import time
import logging
import subprocess

from alttester import By, AltDriver
from utils.mongo_helper import boost_player_level, get_account_by_device, delete_account_by_device
from utils.state_manager import state
from utils.popup_handler import wait_for_safe, safe_tap, handle_one_popup
from utils.device_helpers import handle_permissions
from utils.helpers import get_user_snapshot, get_device_id
from utils.paths import (
    HOME_BUTTON, LOGIN_SCREEN, GUEST_BUTTON,
    FTUE_INTRO_SKIP, FTUE_SKIP_BUTTON,
    MATCHMAKING_SCREEN, CARD_DRAW_BUTTON,
    INGAME_BURGER_MENU, INGAME_HUD_QUIT, QUIT_CONFIRM,
    BUILD_ACTIVE_CARD, BUILD_INFO_SCREEN, NEXT_BUILD_CARD, BUILD_CLOSE,
    BET_PLAY_BUTTON, BET_CLOSE,
    PIGGY_BANK_INFO,
)
from config import ADB_PATH
from tests.handlers.daily_handler import is_present as daily_login_present, handle as daily_login_handle
from tests.handlers.album_ftue_handler import (
    is_present as album_ftue_present,
    handle as album_ftue_handle
)
from tests.handlers.beach_buddies_handler import (
    is_present as beach_buddies_present,
    handle as beach_buddies_handle
)

import utils.event_tracker as event_tracker

PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"
ALTTESTER_PORT = 13000
APP_NAME = "sorry"


# -------------------------------
# SCREEN TAP HELPER
# Some FTUE info screens require a raw "tap anywhere" to dismiss.
# Tapping the specific element path does not register for these screens.
# -------------------------------
def _tap_screen_center():
    device_id = state.get("device_id")
    if not device_id:
        logging.warning("⚠️ device_id not in state — cannot ADB tap")
        return
    subprocess.run([
        ADB_PATH, "-s", device_id,
        "shell", "input", "tap", "540", "1200"
    ])


# -----------------------------------------------------------------------
# LOADING GATE
# The login screen (/Canvas/midUiLayer/loginScreen) hosts the loading bar and
# stays on screen until the guest login + initial load finish completely.
# Searching for the FTUE intro/skip button — or waiting on the FTUE transition
# animation — while it's still up races the loader: on a slow load the skip
# search times out and the whole FTUE walkthrough cascades into failures.
# So gate on this screen first — its disappearance is the reliable "fully
# loaded" signal — and only then look for FTUE.
# -----------------------------------------------------------------------
def wait_for_login_loading_complete(unity_driver, timeout=90):
    end = time.time() + timeout
    logged = False
    while time.time() < end:
        if not wait_for_safe(unity_driver, By.PATH, LOGIN_SCREEN, 1):
            if logged:
                logging.info("✅ Login/loading screen cleared — proceeding to FTUE")
            return True
        if not logged:
            logging.info("⏳ Login/loading screen still up (loading) — waiting before FTUE...")
            logged = True
        time.sleep(1)
    logging.warning(
        f"⚠️ Login/loading screen still present after {timeout}s — proceeding to FTUE anyway"
    )
    return False


# -------------------------------
# RESTART + RECONNECT
# ADB reverse port forwarding keeps device:127.0.0.1:13000 tunnelled to
# AltTester Desktop — no IP input or manual restart tap needed.
# -------------------------------
def restart_and_reconnect(driver, unity_driver):
    device_id = driver.capabilities.get("udid") or driver.capabilities.get("deviceName")

    logging.info(f"🔄 Restarting game on {device_id}...")

    subprocess.run([ADB_PATH, "-s", device_id, "shell", "am", "force-stop", PACKAGE_NAME])
    time.sleep(2)

    subprocess.run([
        ADB_PATH, "-s", device_id, "shell", "am", "start",
        "-n", f"{PACKAGE_NAME}/{ACTIVITY_NAME}"
    ])

    logging.info("🚀 Game relaunched — waiting for AltTester to register...")
    time.sleep(10)

    try:
        unity_driver.stop()
        logging.info("🔌 Old AltTester driver closed")
    except Exception:
        pass

    for i in range(10):
        try:
            unity_driver = AltDriver(host="127.0.0.1", port=ALTTESTER_PORT, app_name=APP_NAME)
            logging.info(f"✅ AltTester reconnected (attempt {i + 1})")
            return unity_driver
        except Exception as e:
            logging.warning(f"⚠️ Reconnect attempt {i + 1} failed: {e}")
            time.sleep(3)

    raise Exception("❌ AltTester reconnect failed")


# -------------------------------
# NAVIGATION
# -------------------------------
def reach_home(unity_driver, driver):
    end = time.time() + 120  # extended — IAP can take up to 60s

    while time.time() < end:
        handle_permissions(driver)

        handled = False

        # -------------------------------
        # DAILY LOGIN (HIGH PRIORITY)
        # -------------------------------
        if daily_login_present(unity_driver):
            logging.info("🎁 Daily Login detected → Handling flow")
            daily_login_handle(unity_driver, driver)
            handled = True

        # -------------------------------
        # ALBUM FTUE (HIGH PRIORITY)
        # -------------------------------
        if album_ftue_present(unity_driver):
            logging.info("📘 Album FTUE detected → Handling flow")
            album_ftue_handle(unity_driver, driver)
            handled = True

        # -------------------------------
        # BEACH BUDDIES (HIGH PRIORITY)
        # -------------------------------
        if beach_buddies_present(unity_driver):
            logging.info("🏖️ Beach Buddies FTUE detected → Handling flow")
            beach_buddies_handle(unity_driver, driver)
            handled = True

        # -------------------------------
        # IMPORTANT FLOW HANDLED
        # -------------------------------
        if handled:
            time.sleep(1)
            continue

        # -------------------------------
        # GENERIC POPUPS
        # -------------------------------
        handle_one_popup(unity_driver)

        # -------------------------------
        # HOME CHECK
        # -------------------------------
        home = wait_for_safe(unity_driver, By.PATH, HOME_BUTTON, 2)

        if home:
            home.tap()
            return unity_driver, driver  # return updated drivers

        time.sleep(0.5)

    raise Exception("❌ Failed to reach home")


# -----------------------------------------------------------------------
# NEW FTUE FLOW HANDLER
# Detects the new onboarding cinematic and walks through all FTUE steps.
# Returns once the lobby is clear and ready for normal post-login flow.
# -----------------------------------------------------------------------
def handle_new_ftue_flow(unity_driver, driver):
    logging.info("🎬 New FTUE flow detected — starting guided walkthrough")

    # Defensive gate: never wait on the FTUE transition / search the in-game
    # skip button while the login/loading screen is still up (slow loads race
    # these searches). Returns immediately once loading has already cleared.
    wait_for_login_loading_complete(unity_driver)

    # -----------------------------------------------------------------------
    # STEP 1 — Intro skip already tapped before this call; wait for the
    #           transition, then tap the in-game FTUE skip button
    # -----------------------------------------------------------------------
    logging.info("⏳ Waiting for FTUE cinematic transition...")
    time.sleep(3)  # allow animation to settle

    logging.info("🔍 Looking for in-game FTUE skip button...")
    ftue_skip_ingame = wait_for_safe(unity_driver, By.PATH, FTUE_SKIP_BUTTON, 10)
    if ftue_skip_ingame:
        safe_tap(unity_driver, ftue_skip_ingame)
        event_tracker.record("FTUE", "Ingame FTUE", "PASS")
        logging.info("✅ In-game FTUE skip button tapped")
        time.sleep(2)
    else:
        event_tracker.record("FTUE", "Ingame FTUE", "FAIL")
        logging.warning("⚠️ In-game FTUE skip button not found — continuing")

    # -----------------------------------------------------------------------
    # STEP 2 — Wait for matchmaking screen to appear and then disappear
    # -----------------------------------------------------------------------
    logging.info("⏳ Waiting for matchmaking screen...")
    matchmaking_end = time.time() + 15
    while time.time() < matchmaking_end:
        mm = wait_for_safe(unity_driver, By.PATH, MATCHMAKING_SCREEN, 2)
        if mm:
            logging.info("🎯 Matchmaking screen detected — waiting for it to disappear...")
            break
        time.sleep(0.5)

    # Wait for matchmaking to clear (up to 30s)
    mm_gone_end = time.time() + 30
    while time.time() < mm_gone_end:
        mm = wait_for_safe(unity_driver, By.PATH, MATCHMAKING_SCREEN, 2)
        if not mm:
            logging.info("✅ Matchmaking screen gone")
            break
        time.sleep(1)

    time.sleep(2)

    # -----------------------------------------------------------------------
    # STEP 3 — Card Draw button
    # -----------------------------------------------------------------------
    logging.info("🃏 Looking for Card Draw button...")
    card_draw = wait_for_safe(unity_driver, By.PATH, CARD_DRAW_BUTTON, 10)
    if card_draw:
        safe_tap(unity_driver, card_draw)
        logging.info("✅ Card Draw button tapped")
        time.sleep(2)
    else:
        logging.warning("⚠️ Card Draw button not found — continuing")

    # -----------------------------------------------------------------------
    # STEP 4 — Burger menu → Quit → Confirm
    # -----------------------------------------------------------------------
    logging.info("🍔 Looking for in-game burger menu...")
    burger = wait_for_safe(unity_driver, By.PATH, INGAME_BURGER_MENU, 10)
    if burger:
        safe_tap(unity_driver, burger)
        logging.info("✅ Burger menu tapped")
        time.sleep(1)

        quit_btn = wait_for_safe(unity_driver, By.PATH, INGAME_HUD_QUIT, 5)
        if quit_btn:
            safe_tap(unity_driver, quit_btn)
            logging.info("✅ Quit option tapped")
            time.sleep(1)

            confirm = wait_for_safe(unity_driver, By.PATH, QUIT_CONFIRM, 5)
            if confirm:
                safe_tap(unity_driver, confirm)
                logging.info("✅ Quit confirmed")
                time.sleep(3)
            else:
                logging.warning("⚠️ Quit confirm popup not found")
        else:
            logging.warning("⚠️ Quit option not found in menu")
    else:
        logging.warning("⚠️ Burger menu not found — continuing")

    time.sleep(2)

    # -----------------------------------------------------------------------
    # STEP 5 — Build: Active Card → dismiss info → Next Card → dismiss info
    #           → Close tray
    # Info screens are "tap anywhere" screens — unconditionally tap center
    # after each card tap (3s animation settle) instead of relying on path
    # detection which is flaky during FTUE animations.
    # -----------------------------------------------------------------------
    logging.info("🏗️ Looking for Build Active Card...")
    build_card = wait_for_safe(unity_driver, By.PATH, BUILD_ACTIVE_CARD, 10)
    if build_card:
        safe_tap(unity_driver, build_card)
        logging.info("✅ Build Active Card tapped")
        time.sleep(5)  # wait for animation + info screen to fully appear
        _tap_screen_center()  # dismiss info screen (tap anywhere)
        logging.info("✅ Build Info Screen tapped — waiting for it to close...")

        # Confirm info screen is gone before proceeding
        info_gone_end = time.time() + 8
        while time.time() < info_gone_end:
            still_open = wait_for_safe(unity_driver, By.PATH, BUILD_INFO_SCREEN, 1)
            if not still_open:
                logging.info("✅ Build Info Screen confirmed closed")
                break
            _tap_screen_center()
            time.sleep(1)

        time.sleep(1)

        next_card = wait_for_safe(unity_driver, By.PATH, NEXT_BUILD_CARD, 8)
        if next_card:
            safe_tap(unity_driver, next_card)
            logging.info("✅ Next Build Card tapped")
            time.sleep(5)  # wait for animation to complete
        else:
            logging.warning("⚠️ Next Build Card not found — continuing")

        build_close = wait_for_safe(unity_driver, By.PATH, BUILD_CLOSE, 8)
        if build_close:
            safe_tap(unity_driver, build_close)
            logging.info("✅ Build tray closed")
        else:
            logging.warning("⚠️ Build Close not found — continuing")
        time.sleep(2)  # wait for tray to finish closing
    else:
        logging.warning("⚠️ Build Active Card not found — continuing")

    # -----------------------------------------------------------------------
    # STEP 6 — Bet: Play Button → dismiss FTUE overlay → Close bet screen
    # FTUE overlay is also a "tap anywhere" screen.
    # -----------------------------------------------------------------------
    logging.info("🎲 Looking for Bet Play Button...")
    bet_play = wait_for_safe(unity_driver, By.PATH, BET_PLAY_BUTTON, 10)
    if bet_play:
        safe_tap(unity_driver, bet_play)
        logging.info("✅ Bet Play Button tapped")
        time.sleep(3)  # wait for animation + FTUE overlay to appear
        _tap_screen_center()  # dismiss FTUE overlay (tap anywhere)
        logging.info("✅ Bet FTUE overlay dismissed")
        time.sleep(2)  # wait for overlay dismiss animation

        bet_close = wait_for_safe(unity_driver, By.PATH, BET_CLOSE, 8)
        if bet_close:
            safe_tap(unity_driver, bet_close)
            logging.info("✅ Bet screen closed")
        else:
            logging.warning("⚠️ Bet Close not found — continuing")
        time.sleep(2)  # wait for bet screen to close
    else:
        logging.warning("⚠️ Bet Play Button not found — continuing")

    time.sleep(1)

    # -----------------------------------------------------------------------
    # STEP 7 — Daily Login (if present)
    # -----------------------------------------------------------------------
    logging.info("🔍 Checking for Daily Login after FTUE...")
    if daily_login_present(unity_driver):
        logging.info("🎁 Daily Login popup detected after FTUE")
        daily_login_handle(unity_driver, driver)
    else:
        logging.info("ℹ️ No Daily Login popup")

    time.sleep(1)

    # -----------------------------------------------------------------------
    # STEP 8 — Piggy Bank Info Screen (if present)
    # -----------------------------------------------------------------------
    logging.info("🐷 Checking for Piggy Bank info screen...")
    piggy = wait_for_safe(unity_driver, By.PATH, PIGGY_BANK_INFO, 5)
    if piggy:
        _tap_screen_center()  # tap anywhere screen
        logging.info("✅ Piggy Bank info screen dismissed")
        time.sleep(1)
    else:
        logging.info("ℹ️ No Piggy Bank info screen")

    logging.info("✅ New FTUE flow complete")


# -------------------------------
# MAIN TEST
# -------------------------------
def test_guest_login(unity_driver, driver):
    logging.info("🚀 Guest Login Test")

    # -------------------------------
    # ACCOUNT MODE — new / existing / auto (chosen in the webapp; env SAT_ACCOUNT_MODE)
    #   new      → delete any existing account, relaunch, then run the new-user flow
    #   existing → use the account already on the device (skip the new-user FTUE)
    #   auto     → existing if an account is present, else new (default; never deletes)
    # DeviceManager.GetDeviceId() is the stable 1:1 device id; the account lives in
    # sorry_accounts.accounts (deviceID → gameCode → users → name/level).
    # -------------------------------
    mode = (os.environ.get("SAT_ACCOUNT_MODE") or "auto").strip().lower()
    try:
        dev_id = get_device_id(unity_driver)
    except Exception as _e:
        dev_id = None
        logging.warning(f"⚠️ [account] GetDeviceId failed: {_e}")
    acct = get_account_by_device(dev_id) if dev_id else {"exists": False}
    exists = bool(acct.get("exists"))
    logging.info(
        f"🔑 [account] mode={mode}  deviceId={dev_id or 'unknown'}  "
        + (f"existing: {acct.get('name')} (L{acct.get('level')}, {acct.get('gameCode')})"
           if exists else "no existing account")
    )

    if mode == "new" and exists:
        logging.info(f"🗑️ [account] NEW requested + account exists → deleting {acct.get('gameCode')}, then relaunching")
        delete_account_by_device(dev_id)
        # Relaunch so the deletion takes effect — the running client caches the
        # account, same discipline as the level boost.
        unity_driver = restart_and_reconnect(driver, unity_driver)
        exists = False

    if mode == "existing" and not exists:
        logging.warning("⚠️ [account] EXISTING requested but no account present — running new-user flow instead")
    run_existing = exists and mode in ("existing", "auto")
    logging.info(f"🧭 [account] flow → {'EXISTING-USER (skip FTUE)' if run_existing else 'NEW-USER'}")

    # -------------------------------
    # EXISTING-USER — the account auto-logs in and boots straight to the lobby:
    # no login screen, no Guest button, no FTUE / matchmaking / build. Just let
    # the loading bar clear; reach_home() then clears daily-login + popups.
    # -------------------------------
    if run_existing:
        logging.info("👤 Existing-user flow — booting straight to lobby "
                     "(skipping guest login + FTUE)")
        wait_for_login_loading_complete(unity_driver)

    # -------------------------------
    # NEW-USER — login screen → Guest → Android permissions → new-user FTUE
    # -------------------------------
    else:
        login = wait_for_safe(unity_driver, By.PATH, LOGIN_SCREEN, 5)
        if login:
            logging.info("🔐 Login screen found → tapping Guest")
            guest = wait_for_safe(unity_driver, By.PATH, GUEST_BUTTON, 5)
            if not guest:
                raise Exception("❌ Guest button not found")
            guest.tap()
            time.sleep(2)

            from tests.handlers import permissions_handler
            logging.info("🔍 Checking Android permissions...")
            for _ in range(5):
                handled = permissions_handler.handle(unity_driver, driver)
                if not handled:
                    break
                time.sleep(2)

            logging.info("🎬 Following new FTUE flow...")
            wait_for_login_loading_complete(unity_driver)
            ftue_skip = wait_for_safe(unity_driver, By.PATH, FTUE_INTRO_SKIP, 15)
            if ftue_skip:
                safe_tap(unity_driver, ftue_skip)
                event_tracker.record("FTUE", "New User FTUE", "PASS")
                logging.info("✅ FTUE intro skip tapped")
                time.sleep(1)
            else:
                logging.warning(
                    "⚠️ FTUE intro skip not found — proceeding into FTUE flow anyway"
                )
            handle_new_ftue_flow(unity_driver, driver)
        else:
            logging.info("⚡ Already logged in → skipping login screen")

    # -------------------------------
    # POST-LOGIN: DAILY LOGIN CHECK
    # Covered inside handle_new_ftue_flow (step 7).
    # Kept here commented for when old flow is re-enabled:
    # -------------------------------
    # if not is_new_ftue_flow:
    #     logging.info("🔍 Checking for Daily Login popup...")
    #     time.sleep(5)
    #     if daily_login_present(unity_driver):
    #         logging.info("🎁 Daily Login popup detected")
    #         daily_login_handle(unity_driver, driver)
    #     else:
    #         logging.info("ℹ️ No Daily Login popup")

    # -------------------------------
    # REACH HOME (both flows)
    # -------------------------------
    unity_driver, driver = reach_home(unity_driver, driver)

    # -------------------------------
    # SNAPSHOT
    # -------------------------------
    get_user_snapshot(unity_driver)

    player_id = state.user_info.get("player_id")

    # Safe level parsing
    try:
        current_level = int(state.user_info.get("level", 0))
    except Exception:
        current_level = 0

    if not player_id:
        raise Exception("❌ Player ID missing")

    # -------------------------------
    # CONDITIONAL BOOST + RESTART
    # -------------------------------
    boosted = current_level >= 50
    if current_level >= 50:
        logging.info("⚡ Account is already boosted → skipping DB update & restart")

    else:
        logging.info(f"🚀 Current level {current_level} → boosting to 50")

        boost_player_level(player_id)

        unity_driver = restart_and_reconnect(driver, unity_driver)

    # -------------------------------
    # DAILY LOGIN CHECK AFTER RESTART
    # -------------------------------
    logging.info("🔍 Checking for Daily Login popup after restart...")
    time.sleep(5)
    if daily_login_present(unity_driver):
        logging.info("🎁 Daily Login popup detected after restart")
        daily_login_handle(unity_driver, driver)
    else:
        logging.info("ℹ️ No Daily Login popup after restart")

    # After handling → go home
    unity_driver, driver = reach_home(unity_driver, driver)

    # -------------------------------
    # FINAL SNAPSHOT (validation)
    # -------------------------------
    if boosted:
        get_user_snapshot(unity_driver)

    logging.info("✅ Guest Login Test Completed")
    return unity_driver