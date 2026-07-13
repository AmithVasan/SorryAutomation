"""
test_09_gameplay.py
────────────────────
Classic game mode gameplay test.

Flow
────
1.  Log wallet BEFORE (UI, Data, MongoDB)
2.  Tap Play button → Bet screen appears
3.  Tap Classic mode tab (NormalBetscreenModesTab) — skips if already active
4.  Log mode name (Classic) and bet amount
5.  Navigate bet: Prev × 2, Next × 1
6.  Log play-bet text
7.  Tap Play button
8.  Wait for matchmaking screen to disappear (poll every 2 s, up to 60 s)
9.  Wait 2 s for FTUE / transition animations
10. Log in-game gem count
11. Chat flow
      a. Emoji  → open chat → tap quick chat → open chat again → send emoji
      b. Text   → open message icon → tap input → ADB type "Sorry! Automation"
                  → ADB Enter → close chat
12. Draw card
13. Redraw within 3-second window — log gem cost
14. Burger menu → Quit → Confirm quit
15. Log wallet AFTER (UI, Data, MongoDB) + delta
"""

import time
import logging
import subprocess

from alttester import By
import utils.event_tracker as event_tracker

from utils.state_manager import state
from utils.mongo_helper import get_user_wallet
from utils.popup_handler import clear_all_popups, wait_for_safe
from utils.helpers import fast_text, parse_amount, get_wallet_from_data
from utils.paths import (
    HOME_BUTTON,
    HOME_GOLD_TEXT,
    HOME_GEMS_TEXT,
    MATCHMAKING_SCREEN,
    GAME_PLAY_BUTTON,
    GAME_BET_CLASSIC_TAB,
    GAME_BET_MODE,
    GAME_BET_AMOUNT,
    GAME_BET_PREV,
    GAME_BET_NEXT,
    GAME_BET_PLAY_TEXT,
    GAME_BET_PLAY_BTN,
    GAME_INGAME_GEM,
    GAME_EMOJI_BTN,
    GAME_QUICK_CHAT,
    GAME_EMOJI_SEND,
    GAME_CHAT_MSG_BTN,
    GAME_CHAT_INPUT,
    GAME_CARD_DRAW,
    GAME_REDRAW_BTN,
    GAME_REDRAW_GEM,
    GAME_BURGER_MENU,
    GAME_QUIT_ICON,
    GAME_QUIT_CONFIRM,
    GAME_OPP_PROFILE_BTN,
    GAME_OPP_ADD_FRIEND,
    GAME_OPP_BLOCK_BTN,
    GAME_OPP_BLOCK_CONFIRM,
    GAME_OPP_UNBLOCK_BTN,
    GAME_OPP_PROFILE_CLOSE,
)

# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
ADB_PATH = "/Users/amithvasan/Library/Android/sdk/platform-tools/adb"


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _adb(device_id, *args):
    """Run an ADB shell command, silently ignoring errors."""
    try:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell"] + list(args),
            check=False, timeout=10
        )
    except Exception as e:
        logging.warning(f"⚠️ ADB command failed: {e}")


def _log_wallet_comparison(label, gold_ui, gems_ui, wallet_data, wallet_db):
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
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
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def _safe_delta(after, before):
    if after is None or before is None:
        return "N/A"
    return f"{after - before:+}"


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_gameplay(unity_driver, driver):
    """
    Play one Classic game match, exercise the in-game chat and card redraw,
    then quit via the burger menu.  Logs wallet BEFORE/AFTER for all 3 sources.
    """
    logging.info("🎮 ── test_09_gameplay START ──")

    device_id = state.get("device_id") or "Unknown"
    player_id = state.user_info.get("player_id")

    # ------------------------------------------------------------------
    # 1. Navigate home + clear popups
    # ------------------------------------------------------------------
    logging.info("🏠 Navigating to Home screen...")
    home_btn = _wait(unity_driver, HOME_BUTTON, 5)
    if home_btn:
        home_btn.tap()
        time.sleep(1)

    clear_all_popups(unity_driver)

    # ------------------------------------------------------------------
    # 2. Wallet BEFORE
    # ------------------------------------------------------------------
    gold_ui_b     = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
    gems_ui_b     = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
    data_wallet_b = get_wallet_from_data(unity_driver)
    db_wallet_b   = get_user_wallet(player_id) if player_id else {}
    _log_wallet_comparison("BEFORE", gold_ui_b, gems_ui_b, data_wallet_b, db_wallet_b)

    # ------------------------------------------------------------------
    # 3. Tap Play button → bet screen
    # ------------------------------------------------------------------
    logging.info("▶️ Tapping Play button...")
    play_btn = wait_for_safe(unity_driver, By.PATH, GAME_PLAY_BUTTON, 10)
    if not play_btn:
        raise Exception("❌ [Gameplay] Play button not found")
    play_btn.tap()
    time.sleep(2)

    # ------------------------------------------------------------------
    # 4. Select Classic mode tab explicitly
    #    inactiveTab is only present when Classic is NOT already selected;
    #    if it doesn't exist the mode is already active — just proceed.
    # ------------------------------------------------------------------
    logging.info("🎯 Selecting Classic mode tab...")
    classic_tab = _wait(unity_driver, GAME_BET_CLASSIC_TAB, timeout=5)
    if classic_tab:
        classic_tab.tap()
        time.sleep(1)
        logging.info("   ✅ Classic mode tab tapped")
    else:
        logging.info("   ✅ Classic mode already active")

    # ------------------------------------------------------------------
    # 5. Log mode name and bet amount
    # ------------------------------------------------------------------
    bet_mode_text   = fast_text(unity_driver, GAME_BET_MODE)   or "N/A"
    bet_amount_text = fast_text(unity_driver, GAME_BET_AMOUNT)  or "N/A"
    logging.info(f"🎲 Bet screen  |  Mode: {bet_mode_text}  |  Bet: {bet_amount_text}")

    # ------------------------------------------------------------------
    # 6. Navigate bet: Prev × 2, Next × 1
    # ------------------------------------------------------------------
    for i in range(2):
        prev = _wait(unity_driver, GAME_BET_PREV, 5)
        if prev:
            prev.tap()
            time.sleep(0.5)
            logging.info(f"   ⬅️ Prev tap {i + 1}")
        else:
            logging.warning(f"   ⚠️ Prev button not found on tap {i + 1}")

    nxt = _wait(unity_driver, GAME_BET_NEXT, 5)
    if nxt:
        nxt.tap()
        time.sleep(0.5)
        logging.info("   ➡️ Next tap 1")
    else:
        logging.warning("   ⚠️ Next button not found")

    # ------------------------------------------------------------------
    # 7. Log play-bet text (same path as Next; it shows bet value in play btn)
    # ------------------------------------------------------------------
    play_bet_text = fast_text(unity_driver, GAME_BET_PLAY_TEXT) or "N/A"
    logging.info(f"💰 Play-bet text: {play_bet_text}")

    # ------------------------------------------------------------------
    # 8. Tap Play button on bet screen
    # ------------------------------------------------------------------
    bet_play = _wait(unity_driver, GAME_BET_PLAY_BTN, 8)
    if not bet_play:
        raise Exception("❌ [Gameplay] Bet screen Play button not found")
    bet_play.tap()
    logging.info("▶️ Game starting (matchmaking)...")
    time.sleep(2)

    # ------------------------------------------------------------------
    # 8. Wait for matchmaking screen to disappear (up to 60 s)
    # ------------------------------------------------------------------
    logging.info("⏳ Waiting for matchmaking to complete...")
    for _ in range(30):
        mm = _wait(unity_driver, MATCHMAKING_SCREEN, timeout=2)
        if not mm:
            logging.info("✅ Matchmaking screen gone — game started")
            break
        time.sleep(2)
    else:
        logging.warning("⚠️ [Gameplay] Matchmaking screen still visible after 60 s — proceeding anyway")

    # ------------------------------------------------------------------
    # 9. Wait for FTUE / transition animations
    # ------------------------------------------------------------------
    time.sleep(2)

    # ------------------------------------------------------------------
    # 10. Log in-game gem count
    # ------------------------------------------------------------------
    ingame_gems = fast_text(unity_driver, GAME_INGAME_GEM) or "N/A"
    logging.info(f"💎 In-game gem count: {ingame_gems}")

    # ------------------------------------------------------------------
    # 11a. Emoji chat: open → quick chat → open again → send emoji
    # ------------------------------------------------------------------
    logging.info("💬 Emoji chat flow...")

    emoji_btn = _wait(unity_driver, GAME_EMOJI_BTN, 5)
    if emoji_btn:
        emoji_btn.tap()
        time.sleep(1)
        logging.info("   📂 Chat panel opened")

        quick = _wait(unity_driver, GAME_QUICK_CHAT, 5)
        if quick:
            quick.tap()
            time.sleep(1)
            logging.info("   💬 Quick chat tapped")
        else:
            logging.warning("   ⚠️ Quick chat button not found")

        # Re-open chat for emoji
        emoji_btn2 = _wait(unity_driver, GAME_EMOJI_BTN, 5)
        if emoji_btn2:
            emoji_btn2.tap()
            time.sleep(1)

        emoji_send = _wait(unity_driver, GAME_EMOJI_SEND, 5)
        if emoji_send:
            emoji_send.tap()
            time.sleep(1)
            logging.info("   😀 Emoji sent")
        else:
            logging.warning("   ⚠️ Emoji button not found")
    else:
        logging.warning("   ⚠️ Emoji chat button not found — skipping emoji flow")

    # ------------------------------------------------------------------
    # 11b. Text chat: open → tap input → ADB type → ADB Enter → close
    # ------------------------------------------------------------------
    logging.info("⌨️ Text chat flow...")

    chat_msg_btn = _wait(unity_driver, GAME_CHAT_MSG_BTN, 5)
    if chat_msg_btn:
        chat_msg_btn.tap()
        time.sleep(1)
        logging.info("   📂 Message chat panel opened")

        chat_input = _wait(unity_driver, GAME_CHAT_INPUT, 5)
        if chat_input:
            chat_input.tap()
            time.sleep(1)

            # ADB keyboard text input (spaces as %s)
            message = "Sorry!%sAutomation%sClassic%sMode"
            _adb(device_id, "input", "text", message)
            time.sleep(0.5)
            logging.info("   ✍️ Typed: Sorry! Automation Classic Mode")

            # Send with Enter — chat closes automatically after send
            _adb(device_id, "input", "keyevent", "66")
            time.sleep(1)
            logging.info("   📤 Message sent — chat auto-closed")
        else:
            logging.warning("   ⚠️ Chat input field not found")
    else:
        logging.warning("   ⚠️ Chat message button not found — skipping text chat flow")

    # ------------------------------------------------------------------
    # 12. Draw card
    # ------------------------------------------------------------------
    logging.info("🃏 Drawing card...")
    draw_btn = _wait(unity_driver, GAME_CARD_DRAW, timeout=15)
    if draw_btn:
        draw_btn.tap()
        logging.info("   ✅ Card drawn")
        time.sleep(1)
    else:
        logging.warning("   ⚠️ Draw card button not found")

    # ------------------------------------------------------------------
    # 13. Redraw within 3 s window — log gem cost
    # ------------------------------------------------------------------
    logging.info("🔄 Checking for redraw button (3 s window)...")
    redraw_gem_text = fast_text(unity_driver, GAME_REDRAW_GEM) or "N/A"
    logging.info(f"   💎 Redraw gem cost: {redraw_gem_text}")

    redraw_btn = _wait(unity_driver, GAME_REDRAW_BTN, timeout=4)
    if redraw_btn:
        redraw_btn.tap()
        logging.info("   ✅ Card redrawn")
        time.sleep(1)
    else:
        logging.warning("   ⚠️ Redraw button not found (window may have passed)")

    event_tracker.record("Gameplay", "Classic Match", "PASS")

    # ------------------------------------------------------------------
    # 14. Opponent profile flow
    #     Tap profile → Add Friend → Block → Confirm → Unblock → Close
    # ------------------------------------------------------------------
    logging.info("👤 Opponent profile flow...")

    opp_btn = _wait(unity_driver, GAME_OPP_PROFILE_BTN, timeout=8)
    if opp_btn:
        opp_btn.tap()
        time.sleep(1.5)
        logging.info("   ✅ Opponent profile opened")

        # Add Friend
        add_friend = _wait(unity_driver, GAME_OPP_ADD_FRIEND, timeout=5)
        if add_friend:
            add_friend.tap()
            time.sleep(1)
            logging.info("   ➕ Add Friend tapped")
        else:
            logging.warning("   ⚠️ Add Friend button not found")

        # Block
        block_btn = _wait(unity_driver, GAME_OPP_BLOCK_BTN, timeout=5)
        if block_btn:
            block_btn.tap()
            time.sleep(1)
            logging.info("   🚫 Block tapped")

            # Confirm block
            confirm = _wait(unity_driver, GAME_OPP_BLOCK_CONFIRM, timeout=5)
            if confirm:
                confirm.tap()
                time.sleep(1)
                logging.info("   ✅ Block confirmed")
            else:
                logging.warning("   ⚠️ Block confirm button not found")
        else:
            logging.warning("   ⚠️ Block button not found")

        # Unblock
        unblock_btn = _wait(unity_driver, GAME_OPP_UNBLOCK_BTN, timeout=5)
        if unblock_btn:
            unblock_btn.tap()
            time.sleep(1)
            logging.info("   🔓 Unblock tapped")
        else:
            logging.warning("   ⚠️ Unblock button not found")

        # Close profile
        close_btn = _wait(unity_driver, GAME_OPP_PROFILE_CLOSE, timeout=5)
        if close_btn:
            close_btn.tap()
            time.sleep(1)
            logging.info("   ❌ Opponent profile closed")
        else:
            logging.warning("   ⚠️ Profile close button not found")

    else:
        logging.warning("   ⚠️ Opponent profile button not found — skipping profile flow")

    # ------------------------------------------------------------------
    # 15. Burger menu → Quit → Confirm
    # ------------------------------------------------------------------
    logging.info("🍔 Quitting via burger menu...")
    burger = _wait(unity_driver, GAME_BURGER_MENU, timeout=10)
    if not burger:
        raise Exception("❌ [Gameplay] Burger menu not found — cannot quit")

    burger.tap()
    time.sleep(1)

    quit_icon = _wait(unity_driver, GAME_QUIT_ICON, 5)
    if not quit_icon:
        raise Exception("❌ [Gameplay] Quit option not found in burger menu")

    quit_icon.tap()
    time.sleep(1)

    confirm = _wait(unity_driver, GAME_QUIT_CONFIRM, 5)
    if not confirm:
        raise Exception("❌ [Gameplay] Quit confirm button not found")

    confirm.tap()
    logging.info("✅ Quit confirmed — returning to lobby")
    time.sleep(3)

    # ------------------------------------------------------------------
    # 16. Wallet AFTER + delta
    # ------------------------------------------------------------------
    gold_ui_a     = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
    gems_ui_a     = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
    data_wallet_a = get_wallet_from_data(unity_driver)
    db_wallet_a   = get_user_wallet(player_id) if player_id else {}
    _log_wallet_comparison("AFTER", gold_ui_a, gems_ui_a, data_wallet_a, db_wallet_a)

    logging.info("📊 Wallet Delta (AFTER − BEFORE):")
    logging.info(
        f"   🟡 Gold  → UI: {gold_ui_a - gold_ui_b:+}  |  "
        f"Data: {_safe_delta(data_wallet_a.get('gold'), data_wallet_b.get('gold'))}  |  "
        f"DB: {_safe_delta((db_wallet_a or {}).get('gold'), (db_wallet_b or {}).get('gold'))}"
    )
    logging.info(
        f"   💎 Gems  → UI: {gems_ui_a - gems_ui_b:+}  |  "
        f"Data: {_safe_delta(data_wallet_a.get('gems'), data_wallet_b.get('gems'))}  |  "
        f"DB: {_safe_delta((db_wallet_a or {}).get('gems'), (db_wallet_b or {}).get('gems'))}"
    )

    logging.info("🎮 ── test_09_gameplay DONE ──")
    return unity_driver
