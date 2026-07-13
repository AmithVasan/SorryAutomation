import os
import time
import logging
import subprocess

from alttester import By
import utils.popup_handler as popup_handler
from utils.google_play_helper import (
    handle_google_play_purchase,
    close_extra_google_play_popups,
    reconnect_alttester,
)

from utils.state_manager import state
from utils.popup_handler import (
    wait_for_safe,
    safe_tap,
    handle_one_popup,
    clear_all_popups,
    run_handlers,
)

from utils.helpers import (
    get_user_snapshot,
    fast_text,
    get_wallet_from_data,
)

from config import ADB_PATH

from utils.mongo_helper import (
    get_user_wallet,
    unlock_season_pass,
)

from tests.handlers.daily_handler import (
    is_present as daily_login_present,
    handle as daily_login_handle,
)

from utils.paths import (
    SEASON_PASS_ICON,
    SEASON_PASS_CLOSE,
    ACTIVATE_BTN_PATH,
    BUY_BTN_PATH,
    FREE_TIER1_PATH,
    PAID_TIER1_PATH,
    CLAIM_ALL_PATH,
    UNLOCK_ONE_TIER_BTN,
    UNLOCK_CONFIRM_BTN,
    SEASON_PASS_GEM_PRICE,
    SEASON_PASS_PURCHASE_MODAL,
    SEASON_PASS_PURCHASE_OK,
    HOME_BUTTON,
    PAWN_REWARDS_MODAL,
    PAWN_REWARDS_CONTINUE,
    PAWN_REWARDS_EQUIP,
    REWARD_SUMMARY_CTA,
    LOOTBOX_CLAIM,
)

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

APP_PACKAGE = "com.gameberry.sorry.card.board.game"
APP_ACTIVITY = "com.unity3d.player.SorryUnityPlayerActivity"



# ---------------------------------------------------
# RESTART GAME
# ---------------------------------------------------

def restart_game():

    device_id = state.get("device_id")

    if not device_id:

        raise Exception(
            "❌ device_id missing in state"
        )

    logging.info(
        f"🔄 Restarting game on {device_id}..."
    )

    subprocess.run(
        [
            ADB_PATH,
            "-s",
            device_id,
            "shell",
            "am",
            "force-stop",
            APP_PACKAGE
        ],
        check=False
    )

    time.sleep(2)

    subprocess.run(
        [
            ADB_PATH,
            "-s",
            device_id,
            "shell",
            "am",
            "start",
            "-n",
            f"{APP_PACKAGE}/{APP_ACTIVITY}"
        ],
        check=False
    )

    logging.info("🚀 Game relaunched")

    time.sleep(10)


# ---------------------------------------------------
# OPEN SEASON PASS
# ---------------------------------------------------

def open_season_pass(unity_driver):

    logging.info("🎯 Opening Season Pass")

    # ---------------------------------------------------
    # THOROUGH PRE-OPEN CLEARING
    # Run both POPUP_PRIORITY and full handler registry
    # (album, beach_buddies, ftue, etc.) so nothing is
    # stacked on-screen before the season pass icon is tapped.
    # Two consecutive clean passes → UI is clear.
    # ---------------------------------------------------
    logging.info("🧹 Ensuring UI is clear before opening Season Pass...")

    consecutive_clean = 0
    clearing_end = time.time() + 10

    while time.time() < clearing_end:
        # handle_one_popup only — run_handlers is too slow here
        # (each is_present check waits up to 2 s per handler)
        handled = handle_one_popup(unity_driver)
        if not handled:
            consecutive_clean += 1
            if consecutive_clean >= 2:
                break   # two clean passes → nothing blocking
            time.sleep(0.3)
        else:
            consecutive_clean = 0
            time.sleep(0.5)

    logging.info("✅ UI clear — tapping Season Pass icon")

    icon = wait_for_safe(
        unity_driver,
        By.PATH,
        SEASON_PASS_ICON,
        20
    )

    if not icon:

        raise Exception(
            "❌ Season Pass icon not found"
        )

    safe_tap(unity_driver, icon)

    time.sleep(5)


# ---------------------------------------------------
# UNLOCK ONE TIER
# ---------------------------------------------------

def unlock_one_tier_with_gems(unity_driver):

    unlock_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        UNLOCK_ONE_TIER_BTN,
        15
    )

    if not unlock_btn:

        raise Exception(
            "❌ Unlock tier button not found"
        )

    safe_tap(unity_driver, unlock_btn)

    time.sleep(2)

    gem_price = fast_text(
        unity_driver,
        SEASON_PASS_GEM_PRICE,
        timeout=5
    )

    logging.info(
        f"💎 Unlocking tier using gems ({gem_price})"
    )

    confirm_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        UNLOCK_CONFIRM_BTN,
        15
    )

    if not confirm_btn:

        raise Exception(
            "❌ Unlock confirm button not found"
        )

    safe_tap(unity_driver, confirm_btn)

    time.sleep(5)

    logging.info(
        "✅ Tier unlocked using gems"
    )


# ---------------------------------------------------
# PURCHASE SEASON PASS
# ---------------------------------------------------

def purchase_season_pass(
    unity_driver,
    driver
):

    logging.info(
        "💰 Purchasing Season Pass"
    )

    season_pass_popup = (
        "/Canvas/ModalLayer/"
        "SeasonPassPurchaseModal(Clone)"
        "/rootMain/closeCTA/touchArea"
    )

    try:

        # ---------------------------------------------------
        # IGNORE GLOBAL POPUP AUTO CLOSE
        # ---------------------------------------------------

        popup_handler.ignore_popup(
            season_pass_popup
        )

        logging.info(
            "🛡️ Season Pass popup ignored globally"
        )

        # ---------------------------------------------------
        # ACTIVATE BUTTON
        # ---------------------------------------------------

        activate_btn = wait_for_safe(
            unity_driver,
            By.PATH,
            ACTIVATE_BTN_PATH,
            20
        )

        if not activate_btn:

            raise Exception(
                "❌ Activate button not found"
            )

        safe_tap(unity_driver, activate_btn)

        logging.info(
            "✅ Activate button tapped"
        )

        time.sleep(4)

        # ---------------------------------------------------
        # BUY BUTTON
        # ---------------------------------------------------

        buy_btn = wait_for_safe(
            unity_driver,
            By.PATH,
            BUY_BTN_PATH,
            20
        )

        if not buy_btn:

            raise Exception(
                "❌ Buy button not found"
            )

        safe_tap(unity_driver, buy_btn)

        logging.info(
            "✅ Buy button tapped"
        )

        time.sleep(5)

        # ---------------------------------------------------
        # RECOVER APPIUM SESSION IF DEAD
        # ---------------------------------------------------

        try:

            driver.current_activity

            logging.info(
                "✅ Appium session alive"
            )

        except Exception:

            logging.warning(
                "⚠️ Appium session dead → reconnecting"
            )

            from utils.driver_manager import (
                set_driver
            )

            driver, _ = set_driver(
                device_id=state.get("device_id"),
                app_package=APP_PACKAGE,
                app_activity=APP_ACTIVITY,
                connect_alt=False
            )

            logging.info(
                "✅ Appium reconnected"
            )

        # ---------------------------------------------------
        # HANDLE GOOGLE PLAY PURCHASE
        # ---------------------------------------------------

        purchase_success, driver = handle_google_play_purchase(driver)

        if not purchase_success:

            # Before giving up, reconnect AltTester and check whether
            # the in-game purchase success modal is already showing.
            # This handles the case where the purchase completed but
            # Appium lost track of the package state before confirming.
            logging.warning(
                "⚠️ Google Play timed out — checking for in-game success modal..."
            )

            try:
                unity_driver = reconnect_alttester(unity_driver)
                modal_check = wait_for_safe(
                    unity_driver,
                    By.PATH,
                    SEASON_PASS_PURCHASE_MODAL,
                    15
                )
                if modal_check:
                    logging.info(
                        "✅ Purchase success modal found — purchase DID complete"
                    )
                    purchase_success = True
                else:
                    logging.warning(
                        "⚠️ No success modal — purchase genuinely failed"
                    )
            except Exception as fallback_err:
                logging.warning(
                    f"⚠️ Fallback modal check failed: {fallback_err}"
                )

        if not purchase_success:

            raise Exception(
                "❌ Google Play purchase failed"
            )

        logging.info(
            "✅ Google Play purchase completed"
        )

        # ---------------------------------------------------
        # WAIT & CLEAN ANY EXTRA GOOGLE PLAY POPUPS
        # ---------------------------------------------------

        logging.info(
            "🔍 Checking for extra Google Play popups..."
        )

        extra_popup_timeout = (
            time.time() + 8
        )

        while (
            time.time()
            < extra_popup_timeout
        ):

            try:

                current_package = (
                    driver.current_package
                )

                # Still inside Google Play
                if (
                    current_package
                    == "com.android.vending"
                ):

                    logging.info(
                        "🧹 Extra Google Play popup detected"
                    )

                    _, driver = close_extra_google_play_popups(
                        driver,
                        timeout=5
                    )

                else:

                    logging.info(
                        "✅ No extra Google Play popups"
                    )

                    break

            except Exception:
                pass

            time.sleep(1)

        # ---------------------------------------------------
        # WAIT FOR GAME
        # ---------------------------------------------------

        logging.info(
            "🕒 Waiting for game screen..."
        )

        time.sleep(10)

        # ---------------------------------------------------
        # RECONNECT ALTTESTER
        # ---------------------------------------------------

        unity_driver = reconnect_alttester(unity_driver)

        logging.info("✅ AltTester reconnected after purchase")

        # ---------------------------------------------------
        # PURCHASE SUCCESS MODAL
        # After Google Play completes the game shows a
        # PurchaseNotifModal while still on the season pass
        # screen — tap OK and continue directly.
        # ---------------------------------------------------

        logging.info("🔍 Checking for purchase success modal...")

        modal = wait_for_safe(
            unity_driver,
            By.PATH,
            SEASON_PASS_PURCHASE_MODAL,
            15
        )

        if modal:
            logging.info("✅ Purchase success modal detected")
            ok_btn = wait_for_safe(
                unity_driver,
                By.PATH,
                SEASON_PASS_PURCHASE_OK,
                10
            )
            if ok_btn:
                safe_tap(unity_driver, ok_btn)
                logging.info("✅ Purchase OK tapped")
                time.sleep(2)
            else:
                logging.warning("⚠️ OK button not found inside modal — POPUP_PRIORITY will catch it")
        else:
            logging.warning(
                "⚠️ Purchase success modal not found — continuing"
            )

        # Still on the season pass screen — claim_tier1 runs next
        logging.info("✅ Season Pass purchased — proceeding to claim")

        return unity_driver, driver

    finally:

        popup_handler.unignore_popup(
            season_pass_popup
        )

        logging.info(
            "✅ Re-enabled popup handling"
        )


# ---------------------------------------------------
# CLAIM TIER 1
# ---------------------------------------------------

def claim_tier1(unity_driver):

    logging.info(
        "🎁 Claiming Tier 1 rewards"
    )

    free_claim = wait_for_safe(
        unity_driver,
        By.PATH,
        FREE_TIER1_PATH,
        15
    )

    if free_claim:

        safe_tap(unity_driver, free_claim)

        logging.info(
            "✅ Free Tier 1 reward claimed"
        )

        time.sleep(3)

    paid_claim = wait_for_safe(
        unity_driver,
        By.PATH,
        PAID_TIER1_PATH,
        15
    )

    if paid_claim:

        safe_tap(unity_driver, paid_claim)

        logging.info(
            "✅ Paid Tier 1 reward claimed"
        )

        time.sleep(2)

        # Pawn Rewards Modal appears after claiming paid tier reward
        # Detect by root, then try Later → Equip as fallback
        pawn_root = wait_for_safe(
            unity_driver, By.PATH, PAWN_REWARDS_MODAL, 8
        )

        if pawn_root:
            logging.info("🐾 Pawn Rewards Modal detected")
            tapped = False

            later_btn = wait_for_safe(
                unity_driver, By.PATH, PAWN_REWARDS_CONTINUE, 5
            )
            if later_btn:
                safe_tap(unity_driver, later_btn)
                tapped = True
                logging.info("✅ Pawn Rewards Modal → Later tapped")

            if not tapped:
                equip_btn = wait_for_safe(
                    unity_driver, By.PATH, PAWN_REWARDS_EQUIP, 5
                )
                if equip_btn:
                    safe_tap(unity_driver, equip_btn)
                    tapped = True
                    logging.info("✅ Pawn Rewards Modal → Equip tapped")

            if not tapped:
                logging.warning("⚠️ Pawn Rewards Modal present but no button found")

            time.sleep(2)
        else:
            logging.info("ℹ️ No Pawn Rewards Modal — continuing")

    end = time.time() + 20

    while time.time() < end:

        handled = handle_one_popup(
            unity_driver
        )

        if not handled:
            break

        time.sleep(1)


# ---------------------------------------------------
# CLAIM ALL
# ---------------------------------------------------

def claim_all(unity_driver):

    logging.info(
        "🚀 Claiming all Season Pass rewards"
    )

    claim_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        CLAIM_ALL_PATH,
        25
    )

    if not claim_btn:
        raise Exception(
            "❌ Claim All button not found"
        )

    # ---------------------------------------------------
    # SUPPRESS AUTO-CLOSE FOR REWARD SUMMARY MODAL
    # REWARD_SUMMARY_CTA lives in POPUP_PRIORITY CRITICAL.
    # handle_one_popup (called inside wait_for_safe every
    # 3 s) would dismiss it automatically — causing the
    # wallet delta to read 0.  Ignore it here so the
    # explicit tap in the reward loop fires instead.
    # ---------------------------------------------------
    popup_handler.ignore_popup(REWARD_SUMMARY_CTA)

    try:
        safe_tap(unity_driver, claim_btn)
        time.sleep(3)

        # ---------------------------------------------------
        # DYNAMIC REWARD SCREEN LOOP
        #
        # Claiming all can trigger any number of reward screens
        # in any order.  Each iteration checks (in priority):
        #   1. Reward Summary Modal   → tap CTA   (may appear multiple times)
        #   2. Pawn Rewards Modal     → tap Later / Equip
        #   3. Lootbox Reward Screen  → tap Claim (may appear multiple times)
        #
        # Only when ALL THREE are absent on the same pass do we
        # close the Season Pass modal and navigate home.
        # Safety cap: 120 seconds.
        # ---------------------------------------------------
        logging.info("🎁 Clearing all reward screens dynamically...")

        pawn_count    = 0
        lootbox_count = 0
        summary_count = 0
        safety_end    = time.time() + 120  # hard cap

        while time.time() < safety_end:

            # --- Reward Summary Modal (can appear multiple times) ---
            reward_summary = wait_for_safe(
                unity_driver, By.PATH, REWARD_SUMMARY_CTA, 3
            )
            if reward_summary:
                logging.info(f"   🎬 Reward Summary #{summary_count + 1} — waiting for animation...")
                time.sleep(3)   # let collect animation fully render before tap
                safe_tap(unity_driver, reward_summary)
                summary_count += 1
                logging.info(
                    f"   ✅ Reward Summary #{summary_count} tapped — collecting rewards"
                )
                time.sleep(1)
                continue  # re-check from top

            # --- Pawn Rewards Modal ---
            # Detect by root first (visible early in animation),
            # then try Later button, then Equip as fallback.
            pawn_root = wait_for_safe(
                unity_driver, By.PATH, PAWN_REWARDS_MODAL, 3
            )
            if pawn_root:
                logging.info("🐾 Pawn Rewards Modal detected — waiting for animation...")
                time.sleep(2)   # let pawn reward animation settle before tapping equip
                tapped = False

                # Equip first — expected action after claim all
                equip_btn = wait_for_safe(
                    unity_driver, By.PATH, PAWN_REWARDS_EQUIP, 5
                )
                if equip_btn:
                    safe_tap(unity_driver, equip_btn)
                    tapped = True
                    logging.info("✅ Pawn Rewards Modal → Equip tapped")

                # Fallback: Later (e.g. pawn already owned / equip unavailable)
                if not tapped:
                    later_btn = wait_for_safe(
                        unity_driver, By.PATH, PAWN_REWARDS_CONTINUE, 5
                    )
                    if later_btn:
                        safe_tap(unity_driver, later_btn)
                        tapped = True
                        logging.info("✅ Pawn Rewards Modal → Later tapped")

                if not tapped:
                    logging.warning(
                        "⚠️ Pawn Rewards Modal present but no button found"
                    )

                pawn_count += 1
                dismiss_end = time.time() + 8
                while time.time() < dismiss_end:
                    if not wait_for_safe(
                        unity_driver, By.PATH, PAWN_REWARDS_MODAL, 1
                    ):
                        break
                    time.sleep(0.5)
                time.sleep(1)
                continue  # re-check from top

            # --- Lootbox Reward Screen (can appear multiple times) ---
            lootbox_screen = wait_for_safe(
                unity_driver, By.PATH, LOOTBOX_CLAIM, 3
            )
            if lootbox_screen:
                time.sleep(2)  # let animation settle before tap
                safe_tap(unity_driver, lootbox_screen)
                lootbox_count += 1
                logging.info(f"   ➡️ Lootbox screen #{lootbox_count} tapped")
                dismiss_end = time.time() + 5
                while time.time() < dismiss_end:
                    if not wait_for_safe(
                        unity_driver, By.PATH, LOOTBOX_CLAIM, 1
                    ):
                        logging.info(
                            f"   ✅ Lootbox screen #{lootbox_count} dismissed"
                        )
                        break
                    time.sleep(0.5)
                time.sleep(0.5)
                continue  # re-check from top

            # --- All three absent → thorough cleanup before closing SP ---
            logging.info(
                f"✅ All reward screens cleared "
                f"(Summary: {summary_count} | Pawn: {pawn_count} | "
                f"Lootbox: {lootbox_count}) → final cleanup before closing Season Pass"
            )

            consecutive_clean = 0
            cleanup_end = time.time() + 30
            while time.time() < cleanup_end:
                handled = handle_one_popup(unity_driver)
                if not handled:
                    handled = run_handlers(unity_driver)
                if not handled:
                    consecutive_clean += 1
                    if consecutive_clean >= 2:
                        break
                    time.sleep(0.5)
                else:
                    consecutive_clean = 0
                    time.sleep(1)

            logging.info("✅ Final cleanup done — closing Season Pass modal")

            sp_close = wait_for_safe(
                unity_driver, By.PATH, SEASON_PASS_CLOSE, 5
            )
            if sp_close:
                safe_tap(unity_driver, sp_close)
                logging.info("✅ Season Pass modal closed")
                time.sleep(2)

            home_btn = wait_for_safe(
                unity_driver, By.PATH, HOME_BUTTON, 5
            )
            if home_btn:
                safe_tap(unity_driver, home_btn)
                logging.info("✅ Navigated home after claim all")
                time.sleep(2)
                break

            logging.info("⏳ Waiting for lobby transition — re-checking...")
            time.sleep(1)

        else:
            logging.warning(
                "⚠️ Safety cap reached — could not fully clear all reward screens"
            )

    finally:
        # Always re-enable — POPUP_PRIORITY resumes auto-closing the modal
        # on any future appearance outside the claim-all flow.
        popup_handler.unignore_popup(REWARD_SUMMARY_CTA)
        logging.info("✅ Reward Summary Modal auto-close re-enabled")


# ---------------------------------------------------
# RETURN HOME
# ---------------------------------------------------

def return_to_home(unity_driver):

    logging.info("🏠 Returning to Home")

    home_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        HOME_BUTTON,
        15
    )

    if home_btn:

        safe_tap(unity_driver, home_btn)

        time.sleep(3)

        logging.info(
            "✅ Returned to Home"
        )


# ---------------------------------------------------
# MAIN TEST
# ---------------------------------------------------

def test_season_pass(
    unity_driver,
    driver, run_type=None
):

    start_time = time.time()

    steps = []

    def add_step(
        message,
        status="INFO"
    ):

        steps.append({
            "timestamp": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "status": status,
            "step": message
        })

        logging.info(message)

    try:

        add_step(
            "🚀 Starting Season Pass Test",
            "PASS"
        )

        logging.info(
            "🎫 Starting Season Pass Check"
        )

        # ---------------------------------------------------
        # PLAYER INFO
        # ---------------------------------------------------

        player_id = state.user_info.get(
            "player_id"
        )

        if not player_id:

            add_step(
                "📸 Fetching user snapshot"
            )

            get_user_snapshot(
                unity_driver
            )

            player_id = state.user_info.get(
                "player_id"
            )

        if not player_id:

            raise Exception(
                "❌ Player ID missing"
            )

        add_step(
            f"✅ Player ID: {player_id}",
            "PASS"
        )

        # ---------------------------------------------------
        # BEFORE WALLET
        # ---------------------------------------------------

        wallet_before = get_user_wallet(
            player_id
        )

        if not wallet_before:

            raise Exception(
                "❌ Failed to fetch BEFORE wallet"
            )

        # Data snapshot (UserManager in-memory) — captured at same point as DB
        wallet_data_before = get_wallet_from_data(unity_driver)

        add_step(
            f"💰 BEFORE Wallet (DB): "
            f"{wallet_before}"
        )
        add_step(
            f"💰 BEFORE Wallet (Data): "
            f"Gold={wallet_data_before.get('gold')}  "
            f"Gems={wallet_data_before.get('gems')}  "
            f"Pips={wallet_data_before.get('pips')}"
        )

        # ---------------------------------------------------
        # OPEN PASS
        # ---------------------------------------------------

        open_season_pass(unity_driver)

        add_step(
            "✅ Season Pass opened",
            "PASS"
        )

        # ---------------------------------------------------
        # UNLOCK ONE TIER
        # ---------------------------------------------------

        unlock_one_tier_with_gems(
            unity_driver
        )

        add_step(
            "✅ One tier unlocked using gems",
            "PASS"
        )

        # ---------------------------------------------------
        # PURCHASE PASS
        # ---------------------------------------------------

        unity_driver, driver = purchase_season_pass(
            unity_driver,
            driver
        )

        add_step(
            "✅ Premium Season Pass purchased",
            "PASS"
        )

        # ---------------------------------------------------
        # CLAIM TIER 1
        # ---------------------------------------------------

        claim_tier1(unity_driver)

        add_step(
            "✅ Tier 1 rewards claimed",
            "PASS"
        )

        # ---------------------------------------------------
        # UNLOCK ALL TIERS VIA MONGODB
        # ---------------------------------------------------

        unlock_season_pass(
            player_id,
            30000
        )

        add_step(
            "✅ Season Pass points updated to 30000",
            "PASS"
        )

        time.sleep(5)

        # ---------------------------------------------------
        # RESTART GAME
        # ---------------------------------------------------

        restart_game()

        # ---------------------------------------------------
        # RECONNECT ALTTESTER
        # ---------------------------------------------------

        unity_driver = reconnect_alttester(unity_driver)

        time.sleep(5)

        # ---------------------------------------------------
        # DAILY LOGIN CHECK
        # Game may show the daily login popup after restart
        # ---------------------------------------------------

        logging.info("🔍 Checking for Daily Login popup after restart...")

        if daily_login_present(unity_driver):
            logging.info("🎁 Daily Login popup detected → handling")
            daily_login_handle(unity_driver, driver)
        else:
            logging.info("ℹ️ No Daily Login popup")

        # ---------------------------------------------------
        # CLEAR ALL LOBBY POPUPS
        # Use both POPUP_PRIORITY and full handler registry
        # (album, beach_buddies, ftue etc.) so any popup
        # that appeared on restart is handled before we try
        # to open the season pass icon.
        # Two consecutive clean passes → lobby is truly clear.
        # ---------------------------------------------------
        logging.info("🧹 Waiting for lobby to be fully clear...")

        popup_end = time.time() + 20
        consecutive_clean = 0
        while time.time() < popup_end:
            handled = handle_one_popup(unity_driver)
            if not handled:
                handled = run_handlers(unity_driver)
            if not handled:
                consecutive_clean += 1
                if consecutive_clean >= 2:
                    break   # two clean passes → lobby clear
                time.sleep(0.3)
            else:
                consecutive_clean = 0
                time.sleep(0.5)

        logging.info("✅ Lobby clear — opening Season Pass")
        time.sleep(2)

        # ---------------------------------------------------
        # REOPEN PASS
        # ---------------------------------------------------

        open_season_pass(unity_driver)

        # Wait for season pass auto-scroll animation to settle
        time.sleep(2)

        # Clear any popup that appeared on top of season pass
        logging.info("🧹 Clearing any popups after opening Season Pass...")
        popup_end = time.time() + 10
        consecutive_clean = 0
        while time.time() < popup_end:
            handled = handle_one_popup(unity_driver)
            if not handled:
                consecutive_clean += 1
                if consecutive_clean >= 2:
                    break
                time.sleep(0.3)
            else:
                consecutive_clean = 0
                time.sleep(0.5)

        time.sleep(2)

        add_step(
            "✅ Season Pass reopened after restart",
            "PASS"
        )

        # ---------------------------------------------------
        # CLAIM ALL
        # ---------------------------------------------------

        claim_all(unity_driver)

        # ---------------------------------------------------
        # CLOSE SEASON PASS MODAL
        # claim_all closes it on a clean exit; if the 120s
        # safety cap was hit the modal is still open.
        # Always try to close before proceeding home.
        # ---------------------------------------------------
        logging.info("🔒 Closing Season Pass modal after claim all...")
        sp_close = wait_for_safe(
            unity_driver, By.PATH, SEASON_PASS_CLOSE, 5
        )
        if sp_close:
            safe_tap(unity_driver, sp_close)
            logging.info("✅ Season Pass modal closed — heading home")
            time.sleep(2)
        else:
            logging.info("ℹ️ Season Pass modal already closed")

        add_step(
            "✅ Claim all completed",
            "PASS"
        )

        # ---------------------------------------------------
        # CLEAR HOME SCREEN POPUPS
        # Season Pass close navigates to the lobby.
        # Multiple popups (events, promos, etc.) may appear
        # there — clear them all and verify home is available
        # before reading the final wallet.
        # ---------------------------------------------------
        logging.info(
            "🧹 Clearing any home screen popups after claim all..."
        )

        home_popup_end = time.time() + 60
        consecutive_clean = 0

        while time.time() < home_popup_end:
            handled = handle_one_popup(unity_driver)
            if not handled:
                handled = run_handlers(unity_driver)
            if not handled:
                consecutive_clean += 1
                if consecutive_clean >= 2:
                    break   # two clean passes → home is clear
                time.sleep(1)
            else:
                consecutive_clean = 0
                time.sleep(1)

        # Verify home screen is genuinely available
        home_confirm = wait_for_safe(
            unity_driver, By.PATH, HOME_BUTTON, 10
        )

        if home_confirm:
            logging.info(
                "✅ Home screen confirmed — all popups cleared"
            )
            add_step(
                "✅ Home screen confirmed available",
                "PASS"
            )
        else:
            logging.warning(
                "⚠️ Home button not visible — "
                "may not be fully on home screen"
            )
            add_step(
                "⚠️ Home button not confirmed visible",
                "INFO"
            )

        # ---------------------------------------------------
        # FINAL WALLET
        # ---------------------------------------------------

        wallet_after = get_user_wallet(
            player_id
        )

        if not wallet_after:

            raise Exception(
                "❌ Failed to fetch AFTER wallet"
            )

        # Data snapshot AFTER (UserManager in-memory)
        wallet_data_after = get_wallet_from_data(unity_driver)

        # ---------------------------------------------------
        # VALIDATION — BEFORE vs AFTER (UI / Data / DB)
        # ---------------------------------------------------

        before_gold = wallet_before.get("gold", 0)
        after_gold  = wallet_after.get("gold", 0)
        before_gems = wallet_before.get("gems", 0)
        after_gems  = wallet_after.get("gems", 0)

        gold_delta = after_gold - before_gold
        gems_delta = after_gems - before_gems

        # Data deltas (may be None if method unavailable)
        data_gold_before = wallet_data_before.get("gold")
        data_gold_after  = wallet_data_after.get("gold")
        data_gems_before = wallet_data_before.get("gems")
        data_gems_after  = wallet_data_after.get("gems")
        data_gold_delta  = (data_gold_after - data_gold_before) if (data_gold_before is not None and data_gold_after is not None) else "N/A"
        data_gems_delta  = (data_gems_after - data_gems_before) if (data_gems_before is not None and data_gems_after is not None) else "N/A"

        logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logging.info("💰 Season Pass Wallet Comparison (DB vs Data)")
        logging.info(
            f"   🟡 Gold  → "
            f"DB   BEFORE: {before_gold:<12} | AFTER: {after_gold:<12} | DELTA: +{gold_delta}"
        )
        logging.info(
            f"             "
            f"Data BEFORE: {str(data_gold_before):<12} | AFTER: {str(data_gold_after):<12} | DELTA: {data_gold_delta}"
        )
        logging.info(
            f"   💎 Gems  → "
            f"DB   BEFORE: {before_gems:<12} | AFTER: {after_gems:<12} | DELTA: +{gems_delta}"
        )
        logging.info(
            f"             "
            f"Data BEFORE: {str(data_gems_before):<12} | AFTER: {str(data_gems_after):<12} | DELTA: {data_gems_delta}"
        )
        logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        add_step(
            f"🟡 Gold  → DB: {before_gold} → {after_gold} (Δ +{gold_delta})  |  Data: {data_gold_before} → {data_gold_after} (Δ {data_gold_delta})",
            "PASS"
        )

        add_step(
            f"💎 Gems  → DB: {before_gems} → {after_gems} (Δ +{gems_delta})  |  Data: {data_gems_before} → {data_gems_after} (Δ {data_gems_delta})",
            "PASS"
        )

        add_step(
            "✅ Season Pass Test Completed",
            "PASS"
        )

        return {
            "name": "Season Pass",
            "status": "PASS",
            "duration": round(
                time.time() - start_time,
                2
            ),
            "steps": steps
        }

    except Exception as e:

        logging.exception(
            "❌ Season Pass Test Failed"
        )

        add_step(
            f"❌ Test failed: {str(e)}",
            "FAIL"
        )

        return {
            "name": "Season Pass",
            "status": "FAIL",
            "duration": round(
                time.time() - start_time,
                2
            ),
            "steps": steps
        }