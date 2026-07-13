"""
test_02_happy_flow.py
─────────────────────
Happy Flow: smoke-check that every lobby widget opens and closes cleanly.

Executed before test_03_shop, only on the "smoke" checklist.

Order
─────
 01. Season Pass
 02. Treasure Island   (FTUE-aware)
 03. SkyRush / SoapBox
 04. Leagues
 05. Pie Duel
 06. Beach Buddies
 07. Ad Rewards
 08. Welcome Pack  ↔  EDLP  (mutually exclusive — whichever icon is present)
 09. Daily Tasks
 10. Endless Sale
 11. Puzzle Event       (FTUE-aware)
 12. Piggy Bank
 13. Legendary Pawn
 14. BumpToSpin         (FTUE-aware; skips until HF_BTS_ICON is filled in paths.py)

Design
──────
Each feature is a standalone _do_<name>(unity_driver) function that:
  • Returns True  → feature ran successfully
  • Returns False → feature not present / icon not found (SKIP)
  • Raises        → unexpected error (caught by main loop → FAIL)

To add a new feature:
  1. Add its paths to utils/paths.py under the HAPPY FLOW section.
  2. Write a _do_<name>(unity_driver) function here.
  3. Append ("Friendly Name", _do_<name>) to the FEATURES list in test_happy_flow.

All in-modal element lookups use _wait() (direct wait_for_object, no popup
recovery) so POPUP_PRIORITY handlers cannot interfere with an open modal.
wait_for_safe() is used only for icon lookup on the home screen.
Paths whose close buttons sit in POPUP_PRIORITY CRITICAL/HIGH are explicitly
ignored for the duration of that feature's function via ignore_popup/unignore_popup.
"""

import time
import logging

from alttester import By
import utils.popup_handler as popup_handler
import utils.event_tracker as event_tracker

from utils.popup_handler import wait_for_safe, clear_all_popups, close_info_screen
from utils.paths import (
    HOME_BUTTON,
    # Season Pass — reuse existing constants
    SEASON_PASS_ICON,
    SEASON_PASS_CLOSE,
    # Beach Buddies — reuse existing close + start-popup CTA
    BB_LETS_GO,
    BB_CLOSE,
    # Legendary Pawn — reuse existing close
    PAWN_SALE_CLOSE,
    # Piggy Bank — reuse existing close (also in POPUP_PRIORITY HIGH)
    PIGGY_BANK_CLOSE,
    # All new Happy Flow paths
    HF_TI_ICON, HF_TI_INFO_SCREEN, HF_TI_FREE_AMMO_MODAL,
    HF_TI_FREE_AMMO_COUNT, HF_TI_AWESOME_BTN, HF_TI_TOTAL_AMMO,
    HF_TI_CHEST_FTUE, HF_TI_FTUE_CLICK, HF_TI_LEVEL_COMPLETE, HF_TI_CLOSE,
    HF_SKYRUSH_ICON, HF_SKYRUSH_MODAL, HF_SKYRUSH_START,
    HF_SKYRUSH_INFO, HF_SKYRUSH_LEADERBOARD, HF_SKYRUSH_CLOSE,
    HF_LEAGUE_ICON, HF_LEAGUE_RANK, HF_LEAGUE_CLOSE, HF_LEAGUE_INFO,
    HF_PIEDUEL_ICON, HF_PIEDUEL_MODAL, HF_PIEDUEL_CLOSE, HF_PIEDUEL_INFO,
    HF_BB_ICON, HF_BB_INFO,
    HF_AD_ICON, HF_AD_CLOSE,
    HF_EDLP_ICON, HF_EDLP_CLOSE,
    HF_WELCOME_PACK_ICON, HF_WELCOME_PACK_CLOSE,
    HF_DAILY_TASKS_ICON, HF_DAILY_TASKS_CLOSE,
    HF_ENDLESS_SALE_ICON, HF_ENDLESS_SALE_CLOSE,
    HF_PUZZLE_ICON, HF_PUZZLE_FTUE_MODAL, HF_PUZZLE_AMMO_COUNT,
    HF_PUZZLE_COLLECT, HF_PUZZLE_PIECE_FTUE, HF_PUZZLE_ALL_ICON,
    HF_PUZZLE_TOTAL_AMMO, HF_PUZZLE_CLOSE,
    HF_PAWN_ICON,
    HF_BTS_ICON, HF_BTS_INFO, HF_BTS_FTUE_MODAL, HF_BTS_FREE_AMMO_COUNT,
    HF_BTS_CLAIM, HF_BTS_CLOSE,
    HF_SOCIAL_ICON,
    HF_SOCIAL_TAB_RECENT, HF_SOCIAL_TAB_CHAT,
    HF_SOCIAL_TAB_INVITE, HF_SOCIAL_TAB_FRIENDS,
)


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

def _wait(unity_driver, path, timeout=5):
    """Direct wait — no popup recovery.  Safe to call inside open modals."""
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _go_home(unity_driver):
    """Best-effort home navigation used after a feature failure."""
    try:
        home = unity_driver.wait_for_object(By.PATH, HOME_BUTTON, timeout=3)
        if home:
            home.tap()
            time.sleep(1)
    except Exception:
        pass


def _log_text(obj, label):
    """Read get_text() from obj, log it, and return the string."""
    try:
        text = obj.get_text() if obj else "?"
    except Exception:
        text = "?"
    logging.info(f"   📊 {label}: {text}")
    return text


# -----------------------------------------------------------------------
# 01 · SEASON PASS
# -----------------------------------------------------------------------

def _do_season_pass(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, SEASON_PASS_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Season Pass] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    close = _wait(unity_driver, SEASON_PASS_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Season Pass] Close button not found")

    logging.info("✅ Season Pass opened and closed")
    return True


# -----------------------------------------------------------------------
# 02 · TREASURE ISLAND   (FTUE-aware)
#
# Sequence
# ────────
# 1. Tap icon → 2 s opening animation
# 2. Info screen?        → tap once to close
# 3. Free Ammo modal?    → log ammo count → tap Awesome (FTUE first-visit)
# 4. Total Ammo Icon?    → tap once to close FTUE highlight
# 5. Chest FTUE?         → tap  (FortuneIslasedMainModal — typo is in-game)
# 6. Kitty Bag FTUE?     → tap  (FortuneIslandMainModal)
# 7. 2nd Chest FTUE?     → tap  (FortuneIslandMainModal)
# 8. Level Complete?     → tap → 2 s reward animation
# 9. Final FTUE click?   → tap → 2 s transition to next level
# 10. Close
# -----------------------------------------------------------------------

def _do_treasure_island(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_TI_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Treasure Island] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(4)          # opening animation (2s) + info screen load (~3s)

    # ── Step 2: Info screen ──────────────────────────────────────────
    # Screen takes ~3s to load after icon tap; wait generously so it is
    # fully interactive before we attempt to dismiss it.
    info = _wait(unity_driver, HF_TI_INFO_SCREEN, 8)
    if info:
        time.sleep(1)      # let entry animation settle before tapping
        for attempt in range(1, 4):
            close_info_screen(unity_driver)
            if not _wait(unity_driver, HF_TI_INFO_SCREEN, 2):
                break      # confirmed dismissed
            logging.warning(f"⚠️ [TI] Info screen still open after attempt {attempt} — retrying")
            time.sleep(1)
        logging.info("ℹ️ [TI] Info screen dismissed")

    # ── Step 3: FTUE — On-the-House free ammo modal ──────────────────
    ftue_ammo = _wait(unity_driver, HF_TI_FREE_AMMO_MODAL, 8)
    if ftue_ammo:
        ammo_el = _wait(unity_driver, HF_TI_FREE_AMMO_COUNT, 3)
        _log_text(ammo_el, "TI free ammo")

        awesome = _wait(unity_driver, HF_TI_AWESOME_BTN, 5)
        if awesome:
            awesome.tap()
            time.sleep(1)
            logging.info("✅ [TI] Free ammo collected")

    # ── Steps 4–9: FTUE tap sequence ─────────────────────────────────
    # After free ammo is collected every remaining FTUE overlay (Total Ammo
    # highlight, 1st Chest, Kitty Bag, 2nd Chest, Level Complete, Final
    # transition) is dismissed by tapping the topmost rendered layer.
    # Tap 6 times with 2 s gaps — each tap clears one overlay in sequence.
    logging.info("ℹ️ [TI] Running 6-tap FTUE dismissal sequence...")
    for tap_n in range(1, 7):
        close_info_screen(unity_driver)
        logging.info(f"   🖱️ [TI] FTUE tap {tap_n}/6")
        time.sleep(2)
    logging.info("✅ [TI] FTUE sequence complete")

    # ── Step 10: Close ───────────────────────────────────────────────
    close = _wait(unity_driver, HF_TI_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [TI] Close button not found")

    logging.info("✅ Treasure Island opened and closed")
    return True


# -----------------------------------------------------------------------
# 03 · SKYRUSH / SOAPBOX
# -----------------------------------------------------------------------

def _do_skyrush(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_SKYRUSH_ICON, 10)
    if not icon:
        logging.warning("⚠️ [SkyRush] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    # Info screen may appear — tap topmost layer to close
    info = _wait(unity_driver, HF_SKYRUSH_INFO, 4)
    if info:
        close_info_screen(unity_driver)
        logging.info("ℹ️ [SkyRush] Info screen dismissed")

    # Start popup — tap Start Race
    popup_handler.ignore_popup(HF_SKYRUSH_CLOSE)   # keep leaderboard open after start
    try:
        modal = _wait(unity_driver, HF_SKYRUSH_MODAL, 8)
        if modal:
            start = _wait(unity_driver, HF_SKYRUSH_START, 5)
            if start:
                start.tap()
                time.sleep(2)
                logging.info("✅ [SkyRush] Race started")

                # Info screen can surface again AFTER race starts — close it
                info_post = _wait(unity_driver, HF_SKYRUSH_INFO, 4)
                if info_post:
                    close_info_screen(unity_driver)
                    time.sleep(1)
                    logging.info("ℹ️ [SkyRush] Post-start info screen dismissed")

        # Leaderboard confirms race has started
        leaderboard = _wait(unity_driver, HF_SKYRUSH_LEADERBOARD, 10)
        if leaderboard:
            close = _wait(unity_driver, HF_SKYRUSH_CLOSE, 5)
            if close:
                close.tap()
                time.sleep(1)
        else:
            logging.warning("⚠️ [SkyRush] Leaderboard not found")

    finally:
        popup_handler.unignore_popup(HF_SKYRUSH_CLOSE)

    logging.info("✅ SkyRush opened and closed")
    return True


# -----------------------------------------------------------------------
# 04 · LEAGUES
# -----------------------------------------------------------------------

def _do_leagues(unity_driver):
    # HF_LEAGUE_ICON targets the Bronze badge — skips if player is in another tier
    icon = wait_for_safe(unity_driver, By.PATH, HF_LEAGUE_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Leagues] Icon not found — skipping")
        return False

    popup_handler.ignore_popup(HF_LEAGUE_CLOSE)   # in POPUP_PRIORITY MEDIUM
    try:
        icon.tap()
        time.sleep(1.5)

        # Info screen may appear on first open — close it like a lootbox tap
        info = _wait(unity_driver, HF_LEAGUE_INFO, 4)
        if info:
            close_info_screen(unity_driver)
            time.sleep(1)
            logging.info("ℹ️ [Leagues] Info screen dismissed")

        rank_el = _wait(unity_driver, HF_LEAGUE_RANK, 8)
        _log_text(rank_el, "League rank")

        # Info screen may appear again after rank loads — close before dismissing modal
        info_post = _wait(unity_driver, HF_LEAGUE_INFO, 4)
        if info_post:
            close_info_screen(unity_driver)
            time.sleep(1)
            logging.info("ℹ️ [Leagues] Post-rank info screen dismissed")

        close = _wait(unity_driver, HF_LEAGUE_CLOSE, 8)
        if close:
            close.tap()
            time.sleep(1)
        else:
            logging.warning("⚠️ [Leagues] Close button not found")

    finally:
        popup_handler.unignore_popup(HF_LEAGUE_CLOSE)

    logging.info("✅ Leagues opened and closed")
    return True


# -----------------------------------------------------------------------
# 05 · PIE DUEL
# -----------------------------------------------------------------------

def _do_pie_duel(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_PIEDUEL_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Pie Duel] Icon not found — skipping")
        return False

    popup_handler.ignore_popup(HF_PIEDUEL_CLOSE)   # in POPUP_PRIORITY MEDIUM
    try:
        icon.tap()
        time.sleep(1.5)

        # Info screen may appear on first open — close it like a lootbox tap
        info = _wait(unity_driver, HF_PIEDUEL_INFO, 4)
        if info:
            close_info_screen(unity_driver)
            time.sleep(1)
            logging.info("ℹ️ [Pie Duel] Info screen dismissed")

        modal = _wait(unity_driver, HF_PIEDUEL_MODAL, 10)
        if not modal:
            logging.warning("⚠️ [Pie Duel] Modal did not open")
            return True

        # Info screen may appear again after modal loads — close before dismissing
        info_post = _wait(unity_driver, HF_PIEDUEL_INFO, 4)
        if info_post:
            close_info_screen(unity_driver)
            time.sleep(1)
            logging.info("ℹ️ [Pie Duel] Post-modal info screen dismissed")

        close = _wait(unity_driver, HF_PIEDUEL_CLOSE, 5)
        if close:
            close.tap()
            time.sleep(1)
        else:
            logging.warning("⚠️ [Pie Duel] Close button not found")

    finally:
        popup_handler.unignore_popup(HF_PIEDUEL_CLOSE)

    logging.info("✅ Pie Duel opened and closed")
    return True


# -----------------------------------------------------------------------
# 06 · BEACH BUDDIES
# -----------------------------------------------------------------------

def _do_beach_buddies(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_BB_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Beach Buddies] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    # Info screen may appear on first open — close it like a lootbox tap
    info = _wait(unity_driver, HF_BB_INFO, 4)
    if info:
        close_info_screen(unity_driver)
        time.sleep(1)
        logging.info("ℹ️ [Beach Buddies] Info screen dismissed")

    # Handle start popup if present (no dedicated close — must tap Let's Go)
    lets_go = _wait(unity_driver, BB_LETS_GO, 4)
    if lets_go:
        lets_go.tap()
        time.sleep(1)
        logging.info("ℹ️ [Beach Buddies] Start popup handled")

    # Info screen may appear again after start popup — close before dismissing modal
    info_post = _wait(unity_driver, HF_BB_INFO, 4)
    if info_post:
        close_info_screen(unity_driver)
        time.sleep(1)
        logging.info("ℹ️ [Beach Buddies] Post-start info screen dismissed")

    close = _wait(unity_driver, BB_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Beach Buddies] Close button not found")

    logging.info("✅ Beach Buddies opened and closed")
    return True


# -----------------------------------------------------------------------
# 07 · AD REWARDS
# -----------------------------------------------------------------------

def _do_ad_rewards(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_AD_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Ad Rewards] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    close = _wait(unity_driver, HF_AD_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Ad Rewards] Close button not found")

    logging.info("✅ Ad Rewards opened and closed")
    return True


# -----------------------------------------------------------------------
# 08 · WELCOME PACK  ↔  EDLP   (mutually exclusive — only one shown at a time)
#
# Welcome Pack and EDLP occupy the same slot on the RHS icon strip.
# The server shows one or the other — never both.
# Logic: try Welcome Pack first; if its icon is present handle it and skip EDLP.
#        If not present, fall through to EDLP.
# -----------------------------------------------------------------------

def _do_welcome_pack_or_edlp(unity_driver):
    # ── Welcome Pack ────────────────────────────────────────────────────
    wp_icon = wait_for_safe(unity_driver, By.PATH, HF_WELCOME_PACK_ICON, 5)
    if wp_icon:
        logging.info("🎁 [Welcome Pack] Icon found — handling (skipping EDLP)")

        # Ignore the close button so the popup handler doesn't auto-dismiss
        # the modal while we're intentionally interacting with it
        popup_handler.ignore_popup(HF_WELCOME_PACK_CLOSE)
        try:
            wp_icon.tap()
            time.sleep(1.5)

            close = _wait(unity_driver, HF_WELCOME_PACK_CLOSE, 10)
            if close:
                close.tap()
                time.sleep(1)
            else:
                logging.warning("⚠️ [Welcome Pack] Close button not found")

            logging.info("✅ Welcome Pack opened and closed")
        finally:
            popup_handler.unignore_popup(HF_WELCOME_PACK_CLOSE)

        return True

    # ── EDLP (fallback) ─────────────────────────────────────────────────
    logging.info("ℹ️ [Welcome Pack] Icon not found — trying EDLP...")
    edlp_icon = wait_for_safe(unity_driver, By.PATH, HF_EDLP_ICON, 10)
    if not edlp_icon:
        logging.warning("⚠️ [EDLP] Icon not found either — skipping")
        return False

    popup_handler.ignore_popup(HF_EDLP_CLOSE)   # in POPUP_PRIORITY CRITICAL
    try:
        edlp_icon.tap()
        time.sleep(1.5)

        close = _wait(unity_driver, HF_EDLP_CLOSE, 10)
        if close:
            close.tap()
            time.sleep(1)
        else:
            logging.warning("⚠️ [EDLP] Close button not found")

    finally:
        popup_handler.unignore_popup(HF_EDLP_CLOSE)

    logging.info("✅ EDLP opened and closed")
    return True


# -----------------------------------------------------------------------
# 09 · DAILY TASKS
# -----------------------------------------------------------------------

def _do_daily_tasks(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_DAILY_TASKS_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Daily Tasks] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    close = _wait(unity_driver, HF_DAILY_TASKS_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Daily Tasks] Close button not found")

    logging.info("✅ Daily Tasks opened and closed")
    return True


# -----------------------------------------------------------------------
# 10 · ENDLESS SALE
# -----------------------------------------------------------------------

def _do_endless_sale(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_ENDLESS_SALE_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Endless Sale] Icon not found — skipping")
        return False

    popup_handler.ignore_popup(HF_ENDLESS_SALE_CLOSE)   # in POPUP_PRIORITY HIGH
    try:
        icon.tap()
        time.sleep(1.5)

        close = _wait(unity_driver, HF_ENDLESS_SALE_CLOSE, 10)
        if close:
            close.tap()
            time.sleep(1)
        else:
            logging.warning("⚠️ [Endless Sale] Close button not found")

    finally:
        popup_handler.unignore_popup(HF_ENDLESS_SALE_CLOSE)

    logging.info("✅ Endless Sale opened and closed")
    return True


# -----------------------------------------------------------------------
# 11 · PUZZLE EVENT   (FTUE-aware)
# -----------------------------------------------------------------------

def _do_puzzle_event(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_PUZZLE_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Puzzle Event] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    # FTUE: Free Ammo modal (GenericCommonModal with puzzle content)
    ftue_modal = _wait(unity_driver, HF_PUZZLE_FTUE_MODAL, 5)
    if ftue_modal:
        ammo_el = _wait(unity_driver, HF_PUZZLE_AMMO_COUNT, 3)
        _log_text(ammo_el, "Puzzle free ammo")

        collect = _wait(unity_driver, HF_PUZZLE_COLLECT, 5)
        if collect:
            collect.tap()
            time.sleep(1)
            logging.info("✅ [Puzzle] Free ammo collected")

    # FTUE: Puzzle piece reveal nudge
    piece_ftue = _wait(unity_driver, HF_PUZZLE_PIECE_FTUE, 5)
    if piece_ftue:
        piece_ftue.tap()
        time.sleep(1)
        logging.info("ℹ️ [Puzzle] Puzzle piece FTUE tapped")

        # After revealing piece, tap All Puzzles icon to enter full screen
        all_icon = _wait(unity_driver, HF_PUZZLE_ALL_ICON, 5)
        if all_icon:
            all_icon.tap()
            time.sleep(1.5)
            logging.info("ℹ️ [Puzzle] All Puzzles screen opened")

    # Log total ammo in Puzzle screen
    total_el = _wait(unity_driver, HF_PUZZLE_TOTAL_AMMO, 5)
    _log_text(total_el, "Puzzle total ammo")

    close = _wait(unity_driver, HF_PUZZLE_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Puzzle] Close button not found")

    logging.info("✅ Puzzle Event opened and closed")
    return True


# -----------------------------------------------------------------------
# 12 · PIGGY BANK
# -----------------------------------------------------------------------

def _do_piggy_bank(unity_driver):
    from utils.paths import PIGGY_BANK_ICON, PIGGY_BANK_MODAL

    icon = wait_for_safe(unity_driver, By.PATH, PIGGY_BANK_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Piggy Bank] Icon not found — skipping")
        return False

    popup_handler.ignore_popup(PIGGY_BANK_CLOSE)   # in POPUP_PRIORITY HIGH
    try:
        icon.tap()
        time.sleep(1.5)

        modal = _wait(unity_driver, PIGGY_BANK_MODAL, 8)
        if not modal:
            logging.warning("⚠️ [Piggy Bank] Modal did not open")
            return True

        close = _wait(unity_driver, PIGGY_BANK_CLOSE, 5)
        if close:
            close.tap()
            time.sleep(1)
        else:
            logging.warning("⚠️ [Piggy Bank] Close button not found")

    finally:
        popup_handler.unignore_popup(PIGGY_BANK_CLOSE)

    logging.info("✅ Piggy Bank opened and closed")
    return True


# -----------------------------------------------------------------------
# 13 · LEGENDARY PAWN SALE
# -----------------------------------------------------------------------

def _do_legendary_pawn(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_PAWN_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Legendary Pawn] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    close = _wait(unity_driver, PAWN_SALE_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [Legendary Pawn] Close button not found")

    logging.info("✅ Legendary Pawn Sale opened and closed")
    return True


# -----------------------------------------------------------------------
# 14 · BUMPTOPIN (BTS)   (FTUE-aware)
# -----------------------------------------------------------------------

def _do_bts(unity_driver):
    if not HF_BTS_ICON:
        logging.info(
            "ℹ️ [BumpToSpin] HF_BTS_ICON is blank — fill it in paths.py to enable"
        )
        return False

    icon = wait_for_safe(unity_driver, By.PATH, HF_BTS_ICON, 10)
    if not icon:
        logging.warning("⚠️ [BumpToSpin] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(2)

    # Info screen may appear on first open — close it like a lootbox tap
    info = _wait(unity_driver, HF_BTS_INFO, 4)
    if info:
        close_info_screen(unity_driver)
        time.sleep(1)
        logging.info("ℹ️ [BumpToSpin] Info screen dismissed")

    # FTUE: Free Ammo claim modal (1 sec animation after claim)
    ftue_modal = _wait(unity_driver, HF_BTS_FTUE_MODAL, 5)
    if ftue_modal:
        ammo_el = _wait(unity_driver, HF_BTS_FREE_AMMO_COUNT, 3)
        _log_text(ammo_el, "BTS free ammo")

        claim = _wait(unity_driver, HF_BTS_CLAIM, 5)
        if claim:
            claim.tap()
            time.sleep(1)
            logging.info("✅ [BTS] Free ammo claimed")

    # Info screen may appear again after claim — close before dismissing modal
    info_post = _wait(unity_driver, HF_BTS_INFO, 4)
    if info_post:
        close_info_screen(unity_driver)
        time.sleep(1)
        logging.info("ℹ️ [BumpToSpin] Post-claim info screen dismissed")

    close = _wait(unity_driver, HF_BTS_CLOSE, 10)
    if close:
        close.tap()
        time.sleep(1)
    else:
        logging.warning("⚠️ [BumpToSpin] Close button not found")

    logging.info("✅ BumpToSpin opened and closed")
    return True


# -----------------------------------------------------------------------
# 15 · SOCIAL LOBBY
# -----------------------------------------------------------------------

def _do_social(unity_driver):
    icon = wait_for_safe(unity_driver, By.PATH, HF_SOCIAL_ICON, 10)
    if not icon:
        logging.warning("⚠️ [Social] Icon not found — skipping")
        return False

    icon.tap()
    time.sleep(1.5)

    # Tap each tab in sequence with 1 s delay between each
    tabs = [
        ("Recent",  HF_SOCIAL_TAB_RECENT),
        ("Chat",    HF_SOCIAL_TAB_CHAT),
        ("Invites", HF_SOCIAL_TAB_INVITE),
        ("Friends", HF_SOCIAL_TAB_FRIENDS),
    ]
    for tab_name, tab_path in tabs:
        tab = _wait(unity_driver, tab_path, 5)
        if tab:
            tab.tap()
            logging.info(f"   📋 [Social] {tab_name} tab tapped")
        else:
            logging.warning(f"   ⚠️ [Social] {tab_name} tab not found")
        time.sleep(1)

    # Navigate back to home / lobby
    home = _wait(unity_driver, HOME_BUTTON, 5)
    if home:
        home.tap()
        time.sleep(1)
        logging.info("🏠 [Social] Returned to lobby")
    else:
        logging.warning("⚠️ [Social] Home button not found after Social screen")

    logging.info("✅ Social Lobby opened and closed")
    return True


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------

# Ordered list of features executed in sequence.
# To add a new feature: write a _do_<name> function above and append here.
FEATURES = [
    ("Season Pass",      _do_season_pass),
    ("Treasure Island",  _do_treasure_island),
    ("SkyRush",          _do_skyrush),
    ("Leagues",          _do_leagues),
    ("Pie Duel",         _do_pie_duel),
    ("Beach Buddies",    _do_beach_buddies),
    ("Ad Rewards",       _do_ad_rewards),
    ("Welcome Pack / EDLP", _do_welcome_pack_or_edlp),
    ("Daily Tasks",      _do_daily_tasks),
    ("Endless Sale",     _do_endless_sale),
    ("Puzzle Event",     _do_puzzle_event),
    ("Piggy Bank",       _do_piggy_bank),
    ("Legendary Pawn",   _do_legendary_pawn),
    ("BumpToSpin",       _do_bts),
    ("Social Lobby",     _do_social),
]


def test_happy_flow(unity_driver, driver):
    """
    Smoke-check every lobby widget: open → interact (if FTUE) → close.
    Each feature is isolated — a failure or skip does not stop the rest.
    Returns unity_driver (unchanged, but convention matches other tests).
    """
    logging.info("🎮 ── test_02_happy_flow START ──")

    # ------------------------------------------------------------------
    # Pre-flight: navigate to lobby and clear ALL popups before starting.
    # Two consecutive clean passes confirm the lobby is truly clear.
    # ------------------------------------------------------------------
    logging.info("🏠 Navigating to lobby...")
    home_btn = _wait(unity_driver, HOME_BUTTON, 5)
    if home_btn:
        home_btn.tap()
        time.sleep(1.5)

    logging.info("🧹 Clearing all lobby popups before Happy Flow...")
    clean_passes = 0
    end = time.time() + 30          # hard ceiling — never hang more than 30 s
    while time.time() < end:
        from utils.popup_handler import handle_one_popup
        if handle_one_popup(unity_driver):
            clean_passes = 0        # something was closed — reset clean counter
            time.sleep(0.3)
        else:
            clean_passes += 1
            if clean_passes >= 2:   # two consecutive clean passes → lobby is clear
                break
            time.sleep(0.3)

    logging.info("✅ Lobby is clear — starting Happy Flow")

    passed  = []
    skipped = []
    failed  = []

    for name, fn in FEATURES:
        logging.info(f"▶️  [{name}]")
        try:
            result = fn(unity_driver)
            if result:
                event_tracker.record("Happy Flow", name, "PASS")
                passed.append(name)
            else:
                event_tracker.record("Happy Flow", name, "SKIP")
                skipped.append(name)
        except Exception as e:
            logging.warning(f"⚠️ [{name}] Unexpected error: {e}")
            event_tracker.record("Happy Flow", name, "FAIL")
            failed.append(name)
            # Navigate home to recover before the next feature
            _go_home(unity_driver)
            clear_all_popups(unity_driver)

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info("🎮 Happy Flow Results")
    logging.info(f"   ✅ Passed  ({len(passed)})  : {', '.join(passed)  if passed  else '—'}")
    logging.info(f"   ⏭  Skipped ({len(skipped)}) : {', '.join(skipped) if skipped else '—'}")
    logging.info(f"   ❌ Failed  ({len(failed)})  : {', '.join(failed)  if failed  else '—'}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return unity_driver
