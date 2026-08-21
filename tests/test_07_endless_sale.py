"""
test_07_endless_sale.py
────────────────────────
Endless Sale IAP test.

Flow
────
1.  Log wallet BEFORE (UI, Data, MongoDB)
2.  Navigate home + clear popups
3.  Tap Endless Sale lobby icon
4.  Verify popup opens; log Ammo Progress BEFORE
5.  Tile loop:
      • Detect price text → Free or Paid
      • Log reward count(s) and ammo count (per tile)
      • Free  → tap Claim, wait 3 s for animation, next tile
      • Paid  → Google Play purchase, reconnect AltTester,
                wait 3 s for animation
                  IAP        → buy every paid tile until the complete screen
                  All others → buy 1 paid tile then stop (smoke/complete/regression)
6.  Log Ammo Progress AFTER + delta
7.  Handle complete screen (tap to close) if present
8.  Close popup
9.  Log wallet AFTER (UI, Data, MongoDB) + delta
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
from utils.mongo_helper import get_user_wallet
from utils.popup_handler import clear_all_popups
from utils.helpers import fast_text, parse_amount, get_wallet_from_data, get_rewards_from_data
from utils.paths import (
    HOME_BUTTON,
    HOME_GOLD_TEXT,
    HOME_GEMS_TEXT,
    ES_ICON,
    ES_POPUP,
    ES_CLOSE,
    ES_AMMO_PROGRESS,
    ES_COMPLETE_SCREEN,
    ES_TILE_PRICE,
    ES_TILE_REWARD_1,
    ES_TILE_REWARD_2,
    ES_TILE_AMMO,
    ES_TILE_BUY_BTN,
)


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _read_ammo_progress(unity_driver):
    """Return raw ammo progress text (e.g. '3/10') or 'N/A'."""
    return fast_text(unity_driver, ES_AMMO_PROGRESS) or "N/A"


# The current buyable tile's reward tiles live under slot1's reward container.
ES_TILE_REWARD_CONTAINER = (
    "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/"
    "slot1/EndlessSaleRewardPanel/rewardContainer"
)


def _log_tile(unity_driver, tile_num):
    """Log all available info for the current tile."""
    price = fast_text(unity_driver, ES_TILE_PRICE) or "?"
    ammo  = fast_text(unity_driver, ES_TILE_AMMO)

    is_free = price.strip().lower() == "free"

    logging.info(f"   🎰 Tile {tile_num}  |  Price: {price}  |  Free: {is_free}")

    # Rewards: prefer the game data (typed), fall back to the tile's reward paths.
    try:
        data = get_rewards_from_data(unity_driver, container=ES_TILE_REWARD_CONTAINER)
    except Exception:
        data = []
    if data:
        logging.info("      🎁 Rewards: "
                     + ", ".join(f"{r['type']}={r['amount']}" for r in data))
    else:
        reward1 = fast_text(unity_driver, ES_TILE_REWARD_1)
        reward2 = fast_text(unity_driver, ES_TILE_REWARD_2)
        if reward1:
            logging.info(f"      🎁 Reward 1: {reward1}")
        if reward2:
            logging.info(f"      🎁 Reward 2: {reward2}")

    if ammo:
        logging.info(f"      💣 Ammo in tile: {ammo}")
    else:
        logging.info(f"      💣 No ammo in this tile")

    return is_free, price


def _log_wallet_comparison(label, gold_ui, gems_ui, wallet_data, wallet_db):
    logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 Wallet {label} (UI | Data | DB)")
    logging.info(
        f"   🟡 Gold  → UI: {str(gold_ui):<12} | "
        f"Data: {str(wallet_data.get('gold')):<12} | "
        f"DB: {wallet_db.get('gold') if wallet_db else 'N/A'}"
    )
    logging.info(
        f"   💎 Gems  → UI: {str(gems_ui):<12} | "
        f"Data: {str(wallet_data.get('gems')):<12} | "
        f"DB: {wallet_db.get('gems') if wallet_db else 'N/A'}"
    )
    logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_endless_sale(unity_driver, driver):
    """
    Run the Endless Sale flow.
    IAP run        → claim all free tiles + buy EVERY paid tile until the
                     complete screen appears.
    All other runs → claim all free tiles + buy 1 paid tile, then close
                     (smoke, complete, regression).
    Returns the (possibly refreshed) unity_driver.
    """
    logging.info("♾️ ── test_07_endless_sale START ──")

    run_type = (state.get("run_type") or "complete").lower()
    # Only the IAP run exercises every paid tile. All other runs (smoke,
    # complete, regression) claim the free tiles and buy a SINGLE paid tile.
    buy_all = run_type == "iap"
    logging.info(f"🏃 Run type: {run_type.upper()} — {'buy every paid tile' if buy_all else 'buy 1 paid tile only'}")

    # ------------------------------------------------------------------
    # Refresh driver from state if not passed
    # ------------------------------------------------------------------
    if driver is None:
        driver = state.get("appium_driver")
    if driver is None:
        raise RuntimeError("❌ [EndlessSale] No Appium driver available")

    # ------------------------------------------------------------------
    # Suppress POPUP_PRIORITY auto-close for the entire test
    # (ES_CLOSE is in the HIGH tier — would dismiss the popup mid-test)
    # ------------------------------------------------------------------
    popup_handler.ignore_popup(ES_CLOSE)

    try:
        # --------------------------------------------------------------
        # 1. Navigate home + clear popups
        # --------------------------------------------------------------
        logging.info("🏠 Navigating to Home screen...")
        home_btn = _wait(unity_driver, HOME_BUTTON, 5)
        if home_btn:
            home_btn.tap()
            time.sleep(1)

        clear_all_popups(unity_driver)

        # --------------------------------------------------------------
        # 2. Wallet BEFORE
        # --------------------------------------------------------------
        player_id    = state.user_info.get("player_id")
        gold_ui_b    = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
        gems_ui_b    = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
        data_wallet_b = get_wallet_from_data(unity_driver)
        db_wallet_b  = get_user_wallet(player_id) if player_id else {}
        _log_wallet_comparison("BEFORE", gold_ui_b, gems_ui_b, data_wallet_b, db_wallet_b)

        # --------------------------------------------------------------
        # 3. Open Endless Sale
        # --------------------------------------------------------------
        logging.info("♾️ Tapping Endless Sale icon...")
        es_icon = _wait(unity_driver, ES_ICON, timeout=15)
        if not es_icon:
            logging.warning(
                "⚠️ [EndlessSale] Icon not found — "
                "sale may be inactive or path needs updating in paths.py. "
                "Skipping."
            )
            event_tracker.record("IAP", "Endless Sale", "SKIP")
            return unity_driver

        es_icon.tap()
        time.sleep(2)

        popup = _wait(unity_driver, ES_POPUP, timeout=10)
        if not popup:
            raise Exception("❌ Endless Sale popup did not open")
        logging.info("✅ Endless Sale popup open")

        # --------------------------------------------------------------
        # 4. Log Ammo Progress BEFORE
        # --------------------------------------------------------------
        ammo_before = _read_ammo_progress(unity_driver)
        logging.info(f"💣 Ammo Progress BEFORE: {ammo_before}")

        # --------------------------------------------------------------
        # 5. Tile loop
        #    IAP run        → loops until the complete screen appears (buys all).
        #    All other runs → claim free tiles, buy 1 paid tile, then stop.
        # --------------------------------------------------------------
        paid_bought  = 0
        complete     = False
        tile_num     = 0

        while True:
            tile_num += 1

            # Check for complete screen before inspecting next tile
            if _wait(unity_driver, ES_COMPLETE_SCREEN, 2):
                logging.info("🎉 [EndlessSale] Complete screen detected — all tiles done")
                complete = True
                break

            # Read and log tile info
            price_obj = _wait(unity_driver, ES_TILE_PRICE, timeout=8)
            if not price_obj:
                logging.warning(f"⚠️ [EndlessSale] No tile at position {tile_num} — stopping loop")
                break

            is_free, price_text = _log_tile(unity_driver, tile_num)

            buy_btn = _wait(unity_driver, ES_TILE_BUY_BTN, timeout=5)
            if not buy_btn:
                logging.warning(f"⚠️ [EndlessSale] Buy/Claim button not found at tile {tile_num} — stopping")
                break

            if is_free:
                # ── Free tile — claim and wait for animation ──────────
                buy_btn.tap()
                logging.info(f"   ✅ Free tile {tile_num} claimed")
                time.sleep(3)

            else:
                # ── Paid tile — Google Play purchase ──────────────────
                logging.info(f"   💳 Paid tile {tile_num} — initiating purchase...")
                buy_btn.tap()
                time.sleep(3)

                gp_success, driver = handle_google_play_purchase(driver)
                status = "PASS" if gp_success else "FAIL"
                logging.info(f"   {'✅' if gp_success else '⚠️'} Google Play purchase: {status}")
                event_tracker.record("IAP", f"Endless Sale tile {tile_num}", status)
                state.set("appium_driver", driver)

                unity_driver = reconnect_alttester(unity_driver)
                state.set("unity_driver", unity_driver)
                logging.info("   🔄 AltTester reconnected")
                time.sleep(3)   # claim animation

                paid_bought += 1

                # Log ammo progress immediately after first paid purchase
                if paid_bought == 1:
                    ammo_mid = _read_ammo_progress(unity_driver)
                    logging.info(f"   💣 Ammo Progress after purchase: {ammo_mid}")

                if not buy_all:
                    logging.info(f"   🛑 {run_type.upper()} run — 1 paid tile only, stopping")
                    break

                # Check complete screen right after purchase
                if _wait(unity_driver, ES_COMPLETE_SCREEN, 3):
                    logging.info("🎉 [EndlessSale] Complete screen after purchase — all tiles done")
                    complete = True
                    break

        # --------------------------------------------------------------
        # 6. Log Ammo Progress AFTER + delta
        # --------------------------------------------------------------
        ammo_after = _read_ammo_progress(unity_driver)
        logging.info(f"💣 Ammo Progress AFTER:  {ammo_after}")
        logging.info(f"💣 Ammo Progress: {ammo_before} → {ammo_after}")

        # --------------------------------------------------------------
        # 7. Handle complete screen (tap to dismiss)
        # --------------------------------------------------------------
        if complete:
            cs = _wait(unity_driver, ES_COMPLETE_SCREEN, 5)
            if cs:
                cs.tap()
                logging.info("✅ Complete screen dismissed")
                time.sleep(2)

        # --------------------------------------------------------------
        # 8. Close popup
        # --------------------------------------------------------------
        close_btn = _wait(unity_driver, ES_CLOSE, timeout=5)
        if close_btn:
            close_btn.tap()
            logging.info("✅ Endless Sale popup closed")
            time.sleep(1)
        else:
            logging.warning("⚠️ [EndlessSale] Close button not found — popup may have auto-dismissed")

        # --------------------------------------------------------------
        # 9. Wallet AFTER + delta
        # --------------------------------------------------------------
        gold_ui_a    = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
        gems_ui_a    = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
        data_wallet_a = get_wallet_from_data(unity_driver)
        db_wallet_a  = get_user_wallet(player_id) if player_id else {}
        _log_wallet_comparison("AFTER", gold_ui_a, gems_ui_a, data_wallet_a, db_wallet_a)

        # Deltas
        logging.info("📊 Wallet Delta (AFTER − BEFORE):")
        logging.info(f"   🟡 Gold  → UI: {gold_ui_a - gold_ui_b:+}  |  "
                     f"Data: {_safe_delta(data_wallet_a.get('gold'), data_wallet_b.get('gold'))}  |  "
                     f"DB: {_safe_delta((db_wallet_a or {}).get('gold'), (db_wallet_b or {}).get('gold'))}")
        logging.info(f"   💎 Gems  → UI: {gems_ui_a - gems_ui_b:+}  |  "
                     f"Data: {_safe_delta(data_wallet_a.get('gems'), data_wallet_b.get('gems'))}  |  "
                     f"DB: {_safe_delta((db_wallet_a or {}).get('gems'), (db_wallet_b or {}).get('gems'))}")

        logging.info("♾️ Endless Sale flow complete")

    finally:
        popup_handler.unignore_popup(ES_CLOSE)

    return unity_driver


def _safe_delta(after, before):
    """Return formatted delta string, or 'N/A' if either value is None."""
    if after is None or before is None:
        return "N/A"
    return f"{after - before:+}"
