"""
test_10_fire&icemode.py
────────────────────────
Fire & Ice game mode gameplay test.

Flow
────
1.  Log wallet BEFORE (UI, Data, MongoDB)
2.  Tap Play button → Bet screen appears
3.  Tap Fire & Ice mode tab
4.  Log bet amount currently selected
5.  Navigate bet: Prev × 2, Next × 1
6.  Log play-bet text
7.  Tap Play button
8.  Dismiss Fire Rules screen  (appears right after Play — tap Continue)
9.  Dismiss Ice Rules screen   (appears right after Fire Rules — tap Got It)
10. Wait for matchmaking screen to disappear (poll every 2 s, up to 15 s)
11. Wait 2 s for FTUE / transition animations
12. Log in-game gem count
13. Draw card
14. Redraw within 3-second window — log gem cost
15. Chat flow
      a. Emoji  → open chat → tap quick chat → open again → send emoji
      b. Text   → open message icon → tap input → ADB type
                  "Sorry! Automation Fire & Ice Mode" → ADB Enter → close
16. Burger menu → Quit → Confirm quit
17. Log wallet AFTER (UI, Data, MongoDB) + delta
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
    GAME_BET_FIREICE_TAB,
    GAME_FIREICE_RULES_SCREEN,
    GAME_FIREICE_RULES_CTA,
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
    GAME_FIREICE_CARD_DRAW,
    GAME_FIREICE_REDRAW_BTN,
    GAME_FIREICE_REDRAW_GEM,
    GAME_BURGER_MENU,
    GAME_QUIT_ICON,
    GAME_QUIT_CONFIRM,
)

# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
from config import ADB_PATH   # auto-detected (see utils/env_config.py)


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
def test_fire_and_ice(unity_driver, driver):
    """
    Play one Fire & Ice game match, exercise the in-game chat and card redraw,
    then quit via the burger menu.  Logs wallet BEFORE/AFTER for all 3 sources.
    """
    logging.info("🔥🧊 ── test_10_fire&icemode START ──")

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
        raise Exception("❌ [Fire&Ice] Play button not found")
    play_btn.tap()
    time.sleep(2)

    # ------------------------------------------------------------------
    # 4. Tap Fire & Ice mode tab
    # ------------------------------------------------------------------
    logging.info("🔥🧊 Selecting Fire & Ice mode tab...")
    fi_tab = _wait(unity_driver, GAME_BET_FIREICE_TAB, timeout=8)
    if not fi_tab:
        raise Exception("❌ [Fire&Ice] Fire & Ice tab not found on bet screen")
    fi_tab.tap()
    time.sleep(1.5)
    logging.info("   ✅ Fire & Ice tab tapped")

    # ------------------------------------------------------------------
    # 5. Log bet amount currently selected
    # ------------------------------------------------------------------
    bet_amount_text = fast_text(unity_driver, GAME_BET_AMOUNT) or "N/A"
    logging.info(f"🎲 Bet amount selected: {bet_amount_text}")

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
    # 7. Log play-bet text
    # ------------------------------------------------------------------
    play_bet_text = fast_text(unity_driver, GAME_BET_PLAY_TEXT) or "N/A"
    logging.info(f"💰 Play-bet text: {play_bet_text}")

    # ------------------------------------------------------------------
    # 8. Tap Play button on bet screen
    # ------------------------------------------------------------------
    bet_play = _wait(unity_driver, GAME_BET_PLAY_BTN, 8)
    if not bet_play:
        raise Exception("❌ [Fire&Ice] Bet screen Play button not found")
    bet_play.tap()
    logging.info("▶️ Play tapped...")
    time.sleep(2)

    # ------------------------------------------------------------------
    # 9. Dismiss Fire Rules screen  (appears right after Play is tapped)
    # ------------------------------------------------------------------
    fire_rules = _wait(unity_driver, GAME_FIREICE_RULES_SCREEN, timeout=8)
    if fire_rules:
        logging.info("🔥 Fire Rules screen detected — tapping Continue...")
        cta = _wait(unity_driver, GAME_FIREICE_RULES_CTA, timeout=5)
        if cta:
            cta.tap()
            time.sleep(1)
            logging.info("   ✅ Fire Rules dismissed")
        else:
            logging.warning("   ⚠️ Fire Rules CTA not found")
    else:
        logging.info("   ℹ️ Fire Rules screen not shown")

    # ------------------------------------------------------------------
    # 10. Dismiss Ice Rules screen  (appears right after Fire Rules)
    # ------------------------------------------------------------------
    ice_rules = _wait(unity_driver, GAME_FIREICE_RULES_SCREEN, timeout=8)
    if ice_rules:
        logging.info("🧊 Ice Rules screen detected — tapping Got It...")
        cta = _wait(unity_driver, GAME_FIREICE_RULES_CTA, timeout=5)
        if cta:
            cta.tap()
            time.sleep(1)
            logging.info("   ✅ Ice Rules dismissed")
        else:
            logging.warning("   ⚠️ Ice Rules CTA not found")
    else:
        logging.info("   ℹ️ Ice Rules screen not shown")

    # ------------------------------------------------------------------
    # 11. Wait for matchmaking screen to disappear (up to 15 s)
    # ------------------------------------------------------------------
    logging.info("⏳ Waiting for matchmaking to complete (up to 15 s)...")
    for _ in range(8):
        mm = _wait(unity_driver, MATCHMAKING_SCREEN, timeout=2)
        if not mm:
            logging.info("✅ Matchmaking screen gone — game started")
            break
        time.sleep(2)
    else:
        logging.warning("⚠️ [Fire&Ice] Matchmaking screen still visible after 15 s — proceeding anyway")

    # ------------------------------------------------------------------
    # 12. Wait for FTUE / transition animations
    # ------------------------------------------------------------------
    time.sleep(2)

    # ------------------------------------------------------------------
    # 12. Log in-game gem count
    # ------------------------------------------------------------------
    ingame_gems = fast_text(unity_driver, GAME_INGAME_GEM) or "N/A"
    logging.info(f"💎 In-game gem count: {ingame_gems}")

    # ------------------------------------------------------------------
    # 13. Draw card
    # ------------------------------------------------------------------
    logging.info("🃏 Drawing card...")
    draw_btn = _wait(unity_driver, GAME_FIREICE_CARD_DRAW, timeout=15)
    if draw_btn:
        draw_btn.tap()
        logging.info("   ✅ Card drawn")
        time.sleep(1)
    else:
        logging.warning("   ⚠️ Draw card button not found")

    # ------------------------------------------------------------------
    # 14. Redraw within 3 s window — log gem cost
    # ------------------------------------------------------------------
    logging.info("🔄 Checking for redraw button (3 s window)...")
    redraw_gem_text = fast_text(unity_driver, GAME_FIREICE_REDRAW_GEM) or "N/A"
    logging.info(f"   💎 Redraw gem cost: {redraw_gem_text}")

    redraw_btn = _wait(unity_driver, GAME_FIREICE_REDRAW_BTN, timeout=4)
    if redraw_btn:
        redraw_btn.tap()
        logging.info("   ✅ Card redrawn")
        time.sleep(1)
    else:
        logging.warning("   ⚠️ Redraw button not found (window may have passed)")

    # ------------------------------------------------------------------
    # 15a. Emoji chat: open → quick chat → open again → send emoji
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
    # 15b. Text chat: open → tap input → ADB type → ADB Enter → close
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

            # ADB keyboard text input (spaces as %s, & escaped as \& for Android shell)
            message = r"Sorry!%sAutomation%sFire%s\&%sIce%sMode"
            _adb(device_id, "input", "text", message)
            time.sleep(0.5)
            logging.info("   ✍️ Typed: Sorry! Automation Fire & Ice Mode")

            # Send with Enter — chat closes automatically after send
            _adb(device_id, "input", "keyevent", "66")
            time.sleep(1)
            logging.info("   📤 Message sent — chat auto-closed")
        else:
            logging.warning("   ⚠️ Chat input field not found")
    else:
        logging.warning("   ⚠️ Chat message button not found — skipping text chat flow")

    event_tracker.record("Gameplay", "Fire & Ice Match", "PASS")

    # ------------------------------------------------------------------
    # 16. Burger menu → Quit → Confirm
    # ------------------------------------------------------------------
    logging.info("🍔 Quitting via burger menu...")
    burger = _wait(unity_driver, GAME_BURGER_MENU, timeout=10)
    if not burger:
        raise Exception("❌ [Fire&Ice] Burger menu not found — cannot quit")

    burger.tap()
    time.sleep(1)

    quit_icon = _wait(unity_driver, GAME_QUIT_ICON, 5)
    if not quit_icon:
        raise Exception("❌ [Fire&Ice] Quit option not found in burger menu")

    quit_icon.tap()
    time.sleep(1)

    confirm = _wait(unity_driver, GAME_QUIT_CONFIRM, 5)
    if not confirm:
        raise Exception("❌ [Fire&Ice] Quit confirm button not found")

    confirm.tap()
    logging.info("✅ Quit confirmed — returning to lobby")
    time.sleep(3)

    # ------------------------------------------------------------------
    # 17. Wallet AFTER + delta
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

    logging.info("🔥🧊 ── test_10_fire&icemode DONE ──")
    return unity_driver
