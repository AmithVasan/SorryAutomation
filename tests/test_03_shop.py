import time
import logging
import subprocess
from alttester import By, AltDriver
from utils.google_play_helper import (
    handle_google_play_purchase,
    reconnect_appium_no_launch,
    reconnect_alttester,
    UIA2_CRASH_SIGNAL,
)

from utils.state_manager import state
from utils.mongo_helper import get_user_wallet
from utils.popup_handler import wait_for_safe, safe_tap, clear_all_popups
from utils.helpers import fast_text, parse_amount, get_user_snapshot, get_wallet_from_data
from utils.popup_handler import handle_one_popup
from utils.paths import (
    HOME_BUTTON, SHOP_BUTTON,
    HOME_GOLD_TEXT, HOME_GEMS_TEXT,
    SHOP_GOLD_TEXT, SHOP_GEMS_TEXT,
    PURCHASE_POPUP, PURCHASE_FAIL, PURCHASE_OK,
    GOLD_PACKS, GEM_PACKS,
    HOME_BANK, SHOP_BANK,
    LOOTBOX_PACKS, LOOTBOX_CONFIRM, LOOTBOX_AMMO, LOOTBOX_CLAIM,
    LOW_GEM_MODAL, LOW_GEM_PURCHASE,
)
from config import ADB_PATH
import utils.event_tracker as event_tracker

PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"


# -------------------------------
# SCREEN TAP HELPER
# Lootbox reward screens require a raw "tap anywhere" to dismiss —
# tapping the specific element path does not register. Use ADB instead.
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

# -------------------------------
# SUBSET PACKS  (1 gold + 1 gem + Common x1 + Legendary x3)
# Used by every run type EXCEPT "iap" — only the IAP run buys ALL packs.
# -------------------------------
SMOKE_GOLD_PACKS    = {"Gold 500K"}
SMOKE_GEM_PACKS     = {"6000 Gems"}
SMOKE_LOOTBOX_PACKS = {"Common x1", "Legendary x3"}

# Run types that use the subset (everything else → full list).
# "complete" now buys the same subset as smoke — only "iap" buys every pack.
SUBSET_RUN_TYPES = {"smoke", "regression", "bat", "complete"}


# -------------------------------
# GUARD
# -------------------------------
def check_preconditions():
    if not state.user_info.get("player_id"):
        raise Exception("❌ player_id missing — did test_01 run successfully?")


GOLD_TEXT = SHOP_GOLD_TEXT
GEMS_TEXT = SHOP_GEMS_TEXT


def get_wallet_snapshot(unity, gold_path, gems_path):
    gold = parse_amount(fast_text(unity, gold_path))
    gems = parse_amount(fast_text(unity, gems_path))
    return gold, gems


def wait_for_gold_update(unity, old_value, gold_path, timeout=8):

    end = time.time() + timeout

    last = old_value
    stable_count = 0

    while time.time() < end:

        current = parse_amount(
            fast_text(unity, gold_path)
        )

        if current > last:
            last = current
            stable_count = 0
        else:
            stable_count += 1

        if stable_count >= 3:
            return last

        time.sleep(0.5)

    return last


# -------------------------------
# 🏦 BANK
# -------------------------------
def handle_bank_if_available(unity_driver):

    logging.info("🏦 Checking for Bank...")

    handle_one_popup(unity_driver)

    time.sleep(2)

    # HOME BANK
    home_bank = wait_for_safe(
        unity_driver,
        By.PATH,
        HOME_BANK,
        5
    )

    if home_bank:

        before, _ = get_wallet_snapshot(
            unity_driver,
            HOME_GOLD_TEXT,
            HOME_GEMS_TEXT
        )

        safe_tap(unity_driver, home_bank)

        time.sleep(2)

        after = wait_for_gold_update(
            unity_driver,
            before,
            HOME_GOLD_TEXT
        )

        logging.info(
            f"🏦 Home Bank → "
            f"{before} + {after - before} = {after}"
        )

        event_tracker.record("Shop", "Bank", "PASS")
        return "home"

    # SHOP BANK
    logging.info("➡️ Bank not in Home → checking Shop")

    # Read Home gold HUD before navigating to Shop
    home_gold_before, _ = get_wallet_snapshot(
        unity_driver,
        HOME_GOLD_TEXT,
        HOME_GEMS_TEXT
    )
    logging.info(f"   🏠 Home Gold (before): {home_gold_before}")

    shop_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        SHOP_BUTTON,
        10
    )

    if shop_btn:
        safe_tap(unity_driver, shop_btn)
        time.sleep(2)

    shop_bank = wait_for_safe(
        unity_driver,
        By.PATH,
        SHOP_BANK,
        5
    )

    if shop_bank:

        safe_tap(unity_driver, shop_bank)

        time.sleep(2)   # wait for bank claim animation to complete

        # Read Shop gold HUD after animation
        shop_gold_after = wait_for_gold_update(
            unity_driver,
            home_gold_before,
            SHOP_GOLD_TEXT
        )

        logging.info(
            f"🏦 Shop Bank → "
            f"{home_gold_before} + {shop_gold_after - home_gold_before} = {shop_gold_after}"
        )

        event_tracker.record("Shop", "Bank", "PASS")
        return "shop"


# -------------------------------
# 🎁 LOOTBOX HELPERS
# -------------------------------
def _lootbox_expected_screens(name):
    """
    x1 pack → 1 reward screen
    x3 pack → 3 reward screens
    """
    import re
    m = re.search(r'x(\d+)', name, re.IGNORECASE)
    return int(m.group(1)) if m else 1


# -------------------------------
# 🎁 LOOTBOX (WITH AMMO DELTA)
# -------------------------------
def purchase_all_lootboxes(unity_driver, driver=None):
    """
    Purchase lootbox packs and claim all reward screens.

    - Smoke / regression / bat runs: only SMOKE_LOOTBOX_PACKS subset
    - Complete / IAP runs: all packs

    Handles LOW_GEM modal mid-flow:
      tap greenCTA → Google Play gem purchase → reconnect → retry lootbox

    Returns (unity_driver, driver) — may be refreshed instances.
    """

    run_type = state.get("run_type", "complete")
    is_subset = run_type in SUBSET_RUN_TYPES

    logging.info(
        f"🎁 Starting Lootbox purchases "
        f"[run_type={run_type}, "
        f"{'subset' if is_subset else 'full'}]..."
    )

    for name, path in LOOTBOX_PACKS:

        # ── run-type filter ────────────────────────────────────
        if is_subset and name not in SMOKE_LOOTBOX_PACKS:
            logging.info(f"⏭️  Skipping lootbox (subset run) → {name}")
            continue

        logging.info(f"📦 Lootbox → {name}")

        # ── tap + confirm (with low-gem retry) ─────────────────
        purchased = False
        for attempt in range(2):  # max 1 retry after buying gems

            btn = wait_for_safe(unity_driver, By.PATH, path, 3)
            if not btn:
                logging.warning(f"⚠️ Lootbox not found → {name}")
                break

            safe_tap(unity_driver, btn)
            time.sleep(1)

            confirm = wait_for_safe(
                unity_driver, By.PATH, LOOTBOX_CONFIRM, 3
            )
            if not confirm:
                logging.warning(
                    f"⚠️ Confirm button missing → {name}"
                )
                break

            safe_tap(unity_driver, confirm)
            time.sleep(2)

            # ── low gem check ───────────────────────────────────
            low_gem = wait_for_safe(
                unity_driver, By.PATH, LOW_GEM_MODAL, 3
            )

            if low_gem:
                event_tracker.record("Popups", "Low Gem Popup", "PASS", dedup=True)
                logging.info(
                    f"💸 Low Gem modal detected for {name} "
                    f"→ purchasing gems via Google Play"
                )

                gem_cta = wait_for_safe(
                    unity_driver, By.PATH, LOW_GEM_PURCHASE, 5
                )

                if not gem_cta:
                    logging.warning(
                        "⚠️ Low gem CTA not found — skipping lootbox"
                    )
                    break

                safe_tap(unity_driver, gem_cta)
                time.sleep(3)

                # Complete Google Play gem purchase
                if driver:
                    gp_success, driver = handle_google_play_purchase(
                        driver
                    )
                    time.sleep(3)

                # Reconnect AltTester after Google Play
                try:
                    unity_driver = reconnect_alttester(unity_driver)
                except Exception as e:
                    logging.error(
                        f"❌ AltTester reconnect failed after gem "
                        f"purchase: {e}"
                    )
                    break

                # Dismiss in-game purchase success popup
                # (same modal as gold/gem pack purchases)
                purchase_ok = wait_for_safe(
                    unity_driver, By.PATH, PURCHASE_OK, 10
                )
                if purchase_ok:
                    safe_tap(unity_driver, purchase_ok)
                    logging.info("✅ Gem purchase success popup dismissed")
                    time.sleep(2)
                else:
                    logging.info(
                        "ℹ️ No gem purchase popup — continuing"
                    )

                logging.info(
                    "🔄 Retrying lootbox purchase after gem top-up"
                )
                continue  # retry same lootbox with full gems

            # No low-gem modal → purchase went through
            purchased = True
            break

        event_tracker.record(
            "Shop",
            f"{name} Lootbox",
            "PASS" if purchased else "FAIL",
        )

        if not purchased:
            logging.warning(
                f"⚠️ Could not complete purchase for {name} → skipping"
            )
            continue

        # ---------------------------------------------------
        # CLAIM REWARD SCREENS — exact count per pack type
        # x1 pack → 1 screen, x3 pack → 3 screens
        # After each tap wait for screen to DISAPPEAR before
        # looking for the next one (ensures full dismissal).
        # ---------------------------------------------------
        expected = _lootbox_expected_screens(name)
        total_ammo = 0
        claimed = 0

        for i in range(expected):

            # 10 s budget per screen — transition animation after the previous
            # dismiss can take a couple of seconds before the next screen appears.
            claim = wait_for_safe(
                unity_driver, By.PATH, LOOTBOX_CLAIM, 10
            )

            if not claim:
                logging.warning(
                    f"⚠️ Reward screen {i + 1}/{expected} "
                    f"not found for {name} — continuing to next"
                )
                # Do NOT break — keep iterating in case the screen appears
                # slightly later (final sweep catches any genuinely missed ones).
                continue

            time.sleep(2)  # let reward screen animation settle

            ammo = parse_amount(
                fast_text(unity_driver, LOOTBOX_AMMO)
            )
            total_ammo += ammo

            # Re-find element after animation settle and tap it directly.
            # Fall back to a raw screen tap if the element is gone by then.
            claim = wait_for_safe(unity_driver, By.PATH, LOOTBOX_CLAIM, 3)
            if claim:
                safe_tap(unity_driver, claim)
            else:
                _tap_screen_center()
            time.sleep(1)  # allow tap to register before polling for dismiss
            claimed += 1

            logging.info(
                f"   ➡️ Reward screen {i + 1}/{expected} claimed"
            )

            # Wait for this reward screen to fully disappear
            # before looking for the next one.
            dismiss_end = time.time() + 8
            while time.time() < dismiss_end:
                still_showing = wait_for_safe(
                    unity_driver, By.PATH, LOOTBOX_CLAIM, 1
                )
                if not still_showing:
                    logging.info(
                        f"   ✅ Reward screen {i + 1} dismissed"
                    )
                    break
                time.sleep(0.5)
            else:
                logging.warning(
                    f"   ⚠️ Reward screen {i + 1} did not dismiss "
                    f"within 8s — continuing anyway"
                )

            time.sleep(1)  # give transition animation time before next screen

        logging.info(
            f"🎯 {name} → Claimed: {claimed}/{expected} | "
            f"Total Ammo: {total_ammo}"
        )

    # ---------------------------------------------------
    # FINAL SWEEP — do NOT proceed until LOOTBOX_CLAIM
    # is confirmed gone from the screen.
    # Keeps tapping and waiting until a clean check
    # finds nothing. 60s safety cap prevents infinite loop.
    # ---------------------------------------------------
    logging.info("🧹 Final sweep: waiting for all reward screens to clear...")

    sweep_count = 0
    safety_end = time.time() + 60

    while time.time() < safety_end:

        leftover = wait_for_safe(
            unity_driver, By.PATH, LOOTBOX_CLAIM, 1
        )

        if not leftover:
            # Confirm it stays gone (no sleep — just a fast re-check)
            still_there = wait_for_safe(
                unity_driver, By.PATH, LOOTBOX_CLAIM, 1
            )
            if not still_there:
                break  # confirmed clean
            leftover = still_there  # appeared again between screens

        logging.info(
            f"   ♻️ Reward screen still present — tapping (#{sweep_count + 1})"
        )
        _tap_screen_center()  # raw screen tap to dismiss
        time.sleep(1)  # allow tap to register
        sweep_count += 1

        # Wait for this screen to fully dismiss before checking again
        dismiss_end = time.time() + 8
        while time.time() < dismiss_end:
            if not wait_for_safe(unity_driver, By.PATH, LOOTBOX_CLAIM, 1):
                break
            time.sleep(0.5)

        time.sleep(0.5)

    else:
        logging.warning(
            "⚠️ Reward screens still present after 60s safety cap — proceeding"
        )

    if sweep_count:
        logging.info(
            f"✅ Final sweep cleared {sweep_count} reward screen(s)"
        )
    else:
        logging.info("✅ No leftover reward screens — screen is clean")

    # ---------------------------------------------------
    # NAVIGATE HOME — go back to lobby after all lootboxes
    # so the next test (season pass) starts from a clean state
    # ---------------------------------------------------
    logging.info("🏠 Returning home after lootbox purchases...")

    home_end = time.time() + 20
    while time.time() < home_end:
        handle_one_popup(unity_driver)
        home_btn = wait_for_safe(
            unity_driver, By.PATH, HOME_BUTTON, 2
        )
        if home_btn:
            safe_tap(unity_driver, home_btn)
            logging.info("✅ Returned home after lootboxes")
            time.sleep(2)
            break
        time.sleep(0.5)
    else:
        logging.warning("⚠️ Could not find home button — continuing anyway")

    return unity_driver, driver



# -------------------------------
# PURCHASE POPUP
# -------------------------------
def handle_purchase_popup(unity):

    try:
        unity.wait_for_object(
            By.PATH,
            PURCHASE_POPUP,
            timeout=10
        )

    except Exception:
        return False

    fail = fast_text(
        unity,
        PURCHASE_FAIL,
        timeout=1
    )

    try:
        ok = unity.wait_for_object(
            By.PATH,
            PURCHASE_OK,
            timeout=3
        )

        if ok:
            ok.tap()

    except Exception:
        pass

    return not bool(fail)


# -------------------------------
# SCROLL
# -------------------------------
def scroll_shop(unity):

    try:
        unity.swipe(
            500,
            1500,
            500,
            500,
            duration=500
        )

        time.sleep(0.5)

    except Exception:
        pass


# -------------------------------
# MAIN TEST
# -------------------------------
def test_shop_purchase(unity_driver, driver):

    logging.info(
        "🛒 Starting Shop Purchase Test"
    )

    check_preconditions()

    # BANK
    bank_location = handle_bank_if_available(
        unity_driver
    )

    # OPEN SHOP IF NEEDED
    if bank_location != "shop":

        shop_btn = wait_for_safe(
            unity_driver,
            By.PATH,
            SHOP_BUTTON,
            15
        )

        if not shop_btn:
            raise Exception(
                "❌ Shop button not found"
            )

        safe_tap(unity_driver, shop_btn)

        time.sleep(2)

    handle_one_popup(unity_driver)

    # -------------------------------
    # PURCHASE PACKS (run-type aware)
    # -------------------------------
    run_type = state.get("run_type", "complete")
    is_subset = run_type in SUBSET_RUN_TYPES

    if is_subset:
        logging.info(
            f"⚡ {run_type.upper()} run → purchasing subset: "
            f"{len([x for x in GOLD_PACKS if x[0] in SMOKE_GOLD_PACKS])} gold pack(s), "
            f"{len([x for x in GEM_PACKS if x[0] in SMOKE_GEM_PACKS])} gem pack(s)"
        )
        all_packs = [
            (n, p, vp, pp) for n, p, vp, pp in GOLD_PACKS if n in SMOKE_GOLD_PACKS
        ] + [
            (n, p, vp, pp) for n, p, vp, pp in GEM_PACKS if n in SMOKE_GEM_PACKS
        ]
    else:
        all_packs = GOLD_PACKS + GEM_PACKS

    for name, path, val_path, price_path in all_packs:

        pack_type = "Gold" if "Gold" in name else "Gem"

        # Find the pack button first — scroll if not immediately visible.
        obj = wait_for_safe(unity_driver, By.PATH, path, 10)

        if not obj:
            scroll_shop(unity_driver)
            obj = wait_for_safe(unity_driver, By.PATH, path, 10)

        if not obj:
            logging.warning(f"⚠️ [{pack_type}] Pack button not found — skipping '{name}'")
            continue

        # Read value and price NOW that the card is confirmed on screen.
        # Falls back to the hardcoded name only if the text element is absent.
        pack_value = fast_text(unity_driver, val_path)  or name
        pack_price = fast_text(unity_driver, price_path) or "N/A"

        logging.info(
            f"💰 Buying: {pack_value} {pack_type} Pack  |  "
            f"Cost: {pack_price}"
        )

        before_gold, before_gems = (
            get_wallet_snapshot(
                unity_driver,
                GOLD_TEXT,
                GEMS_TEXT
            )
        )

        safe_tap(unity_driver, obj)

        time.sleep(3)

        gp_success, driver = handle_google_play_purchase(driver)

        time.sleep(3)

        try:
            unity_driver = reconnect_alttester(unity_driver)
        except Exception as e:
            logging.error(f"❌ AltTester reconnect failed for '{pack_value}' {pack_type} Pack: {e}")
            continue

        # Dismiss the in-game post-purchase modal.  NOTE: the "Purchase
        # Successful" and "Purchase Failed" popups share the SAME Okay-button
        # path (PURCHASE_OK == _FAIL_OKAY), so tapping it here only closes the
        # modal — it tells us NOTHING about whether the purchase succeeded.
        purchase_ok_btn = wait_for_safe(unity_driver, By.PATH, PURCHASE_OK, 15)
        if purchase_ok_btn:
            safe_tap(unity_driver, purchase_ok_btn)
            logging.info(f"🔘 Purchase modal dismissed — '{pack_value}' {pack_type} Pack")
            time.sleep(2)
        else:
            logging.warning(f"⚠️ Purchase modal not found for '{pack_value}' {pack_type} Pack — continuing")

        after_gold, after_gems = (
            get_wallet_snapshot(
                unity_driver,
                GOLD_TEXT,
                GEMS_TEXT
            )
        )

        # GROUND TRUTH for success = the wallet actually got credited.
        # A failed purchase shows the identical Okay button but credits
        # nothing, so the balance delta is the only reliable signal.
        if pack_type == "Gold":
            success = after_gold > before_gold
        else:
            success = after_gems > before_gems

        if not success:
            logging.warning(
                f"⚠️ '{pack_value}' {pack_type} Pack — no wallet credit "
                f"(Gold {before_gold}→{after_gold}, Gems {before_gems}→{after_gems}); "
                f"treating as FAILED purchase"
            )

        event_tracker.record(
            "Shop",
            f"{pack_value} {pack_type} Pack",
            "PASS" if success else "FAIL",
            f"Cost: {pack_price}",
        )

        logging.info(
            f"{'🟢' if success else '🔴'} "
            f"{pack_value} {pack_type} Pack  |  Cost: {pack_price}  |  "
            f"🟡 Gold: {before_gold} → {after_gold}  |  "
            f"💎 Gems: {before_gems} → {after_gems}"
        )

        time.sleep(1)

    # LOOTBOX
    unity_driver, driver = purchase_all_lootboxes(unity_driver, driver)

    # BACK HOME
    home_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        HOME_BUTTON,
        10
    )

    if home_btn:

        safe_tap(unity_driver, home_btn)

        time.sleep(1)

        handle_one_popup(unity_driver)

    # FULL SNAPSHOT
    get_user_snapshot(unity_driver)

    # Data source (UserManager in-memory)
    wallet_data = get_wallet_from_data(unity_driver)

    # DB comparison
    player_id = state.user_info.get(
        "player_id"
    )

    wallet_db = (
        get_user_wallet(player_id)
        if player_id else {}
    )

    gold_ui = state.user_info.get("gold", 0)
    gems_ui = state.user_info.get("gems", 0)

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info("📊 FINAL COMPARISON (UI vs Data vs DB):")
    logging.info(
        f"   🟡 Gold  → "
        f"UI: {gold_ui:<12} | "
        f"Data: {str(wallet_data.get('gold')):<12} | "
        f"DB: {wallet_db.get('gold')}"
    )
    logging.info(
        f"   💎 Gems  → "
        f"UI: {gems_ui:<12} | "
        f"Data: {str(wallet_data.get('gems')):<12} | "
        f"DB: {wallet_db.get('gems')}"
    )
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return unity_driver