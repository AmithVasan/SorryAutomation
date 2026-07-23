"""
test_11_city_build.py
─────────────────────
City Build feature test.

Flow
────
 1.  Navigate home + clear any open popups
 2.  Log wallet BEFORE — Gold, Gems, Hammer (UI | Data | DB)
 3.  Tap City Build icon
 4.  Dismiss Build FTUE info screen if shown
 5.  Log current Build Progress Bar
 6.  For each build card (1–5, stops when card not found):
       a. Log hammer cost shown on the card
       b. Read hammer count before starting this card
       c. Tap card → wait 2 s build animation → log per-tap hammer delta
       d. Repeat until tick icon appears on this card
       e. Log Build Progress Bar after tick + total hammers spent on this card
       f. If City Build Reward screen appears at any point → exit loop
 7.  Wait for City Build Reward screen
 8.  Tap Collect Reward → wait 10 s for animation
 9.  Tap Build Close button (returns to lobby)
10.  Clear any post-reward popups
11.  Log wallet AFTER — Gold, Gems, Hammer (UI | Data | DB)
12.  Log side-by-side comparison: Old vs New, delta per city
      — Gold, Gems, Hammer across UI / Data / DB sources
      — Per-card summary (taps, hammers spent)
"""

import time
import logging

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
    HOME_HAMMER_TEXT,
    CB_ICON,
    CB_PROGRESS_BAR,
    CB_CLOSE,
    CB_INFO_SCREEN,
    CB_REWARD_SCREEN,
    CB_COLLECT,
    _CB_CARDS_BASE,
)


# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
MAX_CARDS        = 5    # city can have 3–5 cards; loop breaks when card absent
MAX_TAPS_PER_CARD = 50  # safety ceiling per card


# -----------------------------------------------------------------------
# CARD PATH HELPERS
# Cards are Unity clones:
#   idx 0 → buildCard_Revamped(Clone)
#   idx 1 → buildCard_Revamped(Clone)[1]
#   idx N → buildCard_Revamped(Clone)[N]
# -----------------------------------------------------------------------
def _clone(idx):
    return "buildCard_Revamped(Clone)" + (f"[{idx}]" if idx > 0 else "")


def _card_active(idx):
    return _CB_CARDS_BASE + _clone(idx) + "/buildCardParent/card/activeCard"


def _card_tick(idx):
    return _CB_CARDS_BASE + _clone(idx) + "/buildCardParent/card/bottomContainer/tickIcon"


def _card_hammer(idx):
    return _CB_CARDS_BASE + _clone(idx) + "/buildCardParent/card/bottomContainer/valueTextBlue"


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------
def _wait(unity_driver, path, timeout=5):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _safe_delta(after, before):
    """Return formatted delta string, e.g. '+1500' or '-200'. 'N/A' if either is None."""
    if after is None or before is None:
        return "N/A"
    return f"{after - before:+,}"


def _delta_int(after, before):
    """Return integer delta, or None if either value is missing."""
    if after is None or before is None:
        return None
    return after - before


def _fmt(value):
    """Format int with commas, or return 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _log_snapshot(label, gold_ui, gems_ui, hammer_ui, data, db):
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 Wallet {label}  (UI | Data | DB)")
    logging.info(
        f"   🟡 Gold   → UI: {_fmt(gold_ui):<14} | "
        f"Data: {_fmt(data.get('gold')):<14} | "
        f"DB: {_fmt(db.get('gold') if db else None)}"
    )
    logging.info(
        f"   💎 Gems   → UI: {_fmt(gems_ui):<14} | "
        f"Data: {_fmt(data.get('gems')):<14} | "
        f"DB: {_fmt(db.get('gems') if db else None)}"
    )
    logging.info(
        f"   🔨 Hammer → UI: {_fmt(hammer_ui):<14} | "
        f"Data: {_fmt(data.get('pips')):<14} | "
        f"DB: {_fmt(db.get('pips') if db else None)}"
    )
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def _log_comparison(
    gold_b, gold_a,
    gems_b, gems_a,
    hammer_b, hammer_a,
    data_b, data_a,
    db_b, db_a,
    card_summaries,
):
    sep = "═" * 68
    logging.info(f"\n╔{sep}╗")
    logging.info(f"║{'CITY BUILD — WALLET COMPARISON':^68}║")
    logging.info(f"╠{sep}╣")
    logging.info(f"║  {'SOURCE':<22} {'BEFORE':>12}   {'AFTER':>12}   {'DELTA':>12}  ║")
    logging.info(f"╠{sep}╣")

    rows = [
        ("🟡 Gold    (UI)",    gold_b,                  gold_a,                  None),
        ("🟡 Gold    (Data)",  data_b.get("gold"),      data_a.get("gold"),      None),
        ("🟡 Gold    (DB)",    db_b.get("gold")  if db_b else None, db_a.get("gold")  if db_a else None, None),
        ("💎 Gems    (UI)",    gems_b,                  gems_a,                  None),
        ("💎 Gems    (Data)",  data_b.get("gems"),      data_a.get("gems"),      None),
        ("💎 Gems    (DB)",    db_b.get("gems")  if db_b else None, db_a.get("gems")  if db_a else None, None),
        ("🔨 Hammer  (UI)",    hammer_b,                hammer_a,                None),
        ("🔨 Hammer  (Data)",  data_b.get("pips"),      data_a.get("pips"),      None),
        ("🔨 Hammer  (DB)",    db_b.get("pips")  if db_b else None, db_a.get("pips")  if db_a else None, None),
    ]

    for label, before, after, _ in rows:
        delta = _safe_delta(after, before)
        logging.info(
            f"║  {label:<22} {_fmt(before):>12}   {_fmt(after):>12}   {delta:>12}  ║"
        )

    if card_summaries:
        logging.info(f"╠{sep}╣")
        logging.info(f"║{'PER-CARD SUMMARY':^68}║")
        logging.info(f"╠{sep}╣")
        logging.info(f"║  {'CARD':<10} {'COST/TAP':>10}   {'TAPS':>6}   {'HAMMERS SPENT':>14}  ║")
        logging.info(f"╠{sep}╣")
        total_taps    = 0
        total_hammers = 0
        for card_num, cost_per_tap, taps, hammers_spent in card_summaries:
            total_taps    += taps
            total_hammers += hammers_spent or 0
            logging.info(
                f"║  Card {card_num:<5} {_fmt(cost_per_tap):>10}   {taps:>6}   {_fmt(hammers_spent):>14}  ║"
            )
        logging.info(f"╠{sep}╣")
        logging.info(
            f"║  {'TOTAL':<10} {'':>10}   {total_taps:>6}   {_fmt(total_hammers):>14}  ║"
        )

    logging.info(f"╚{sep}╝\n")


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_city_build(unity_driver, driver):
    """
    Tap through all City Build cards until the city completes,
    collect the reward, and log a full before/after wallet comparison.
    """
    logging.info("🏙️ ── test_11_city_build START ──")

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
    logging.info("📸 Logging wallet BEFORE city build...")
    gold_ui_b   = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
    gems_ui_b   = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
    hammer_ui_b = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))
    data_b      = get_wallet_from_data(unity_driver)
    db_b        = get_user_wallet(player_id) if player_id else {}
    _log_snapshot("BEFORE", gold_ui_b, gems_ui_b, hammer_ui_b, data_b, db_b)

    # ------------------------------------------------------------------
    # 3. Tap City Build icon
    # ------------------------------------------------------------------
    logging.info("🏙️ Tapping City Build icon...")
    cb_icon = wait_for_safe(unity_driver, By.PATH, CB_ICON, 10)
    if not cb_icon:
        raise Exception("❌ City Build icon not found")
    cb_icon.tap()
    time.sleep(2)

    # ------------------------------------------------------------------
    # 4. Dismiss Build FTUE info screen if shown
    # ------------------------------------------------------------------
    info = _wait(unity_driver, CB_INFO_SCREEN, 4)
    if info:
        info.tap()
        logging.info("   ℹ️ Build FTUE info screen dismissed")
        time.sleep(1)

    # ------------------------------------------------------------------
    # 4b. Clear any popups carried over onto the build screen
    #     (e.g. Piggy Bank sale) before starting to tap cards.
    #     The step-1 clear runs on Home, BEFORE entering the build screen,
    #     so sale popups that surface on entry must be cleared here too.
    # ------------------------------------------------------------------
    logging.info("🧹 Clearing any popups on the build screen before starting...")
    time.sleep(1)                       # let a carried-over popup animate in
    clear_all_popups(unity_driver)

    # ------------------------------------------------------------------
    # 5. Log initial Build Progress Bar
    # ------------------------------------------------------------------
    progress = fast_text(unity_driver, CB_PROGRESS_BAR) or "N/A"
    logging.info(f"📊 Build Progress (start): {progress}")

    event_tracker.record("City Build", "Build Started", "PASS", f"Progress: {progress}")

    # ------------------------------------------------------------------
    # 6. Card loop — tap each card until tick appears
    # ------------------------------------------------------------------
    reward_found    = False
    cards_completed = 0
    card_summaries  = []   # [(card_num, cost_per_tap, taps, hammers_spent)]

    for idx in range(MAX_CARDS):

        # ── Does this card exist? ──────────────────────────────────────
        card = _wait(unity_driver, _card_active(idx), timeout=3)
        if not card:
            logging.info(f"   ℹ️ Card {idx + 1} not present — city has {idx} card(s)")
            break

        logging.info(f"\n{'─' * 52}")
        logging.info(f"🏗️  BUILD CARD {idx + 1}")

        # ── a. Log hammer cost for this card ──────────────────────────
        cost_text    = fast_text(unity_driver, _card_hammer(idx))
        cost_per_tap = parse_amount(cost_text) or 0
        logging.info(f"   🔨 Hammer cost per tap: {_fmt(cost_per_tap)}")

        # ── b. Hammer count before starting this card ─────────────────
        hammer_before_card = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))

        tap_count = 0

        # ── c / d. Tap loop until tick or reward screen ───────────────
        for _ in range(MAX_TAPS_PER_CARD):

            # Re-find card each iteration (Unity may refresh the object)
            card = _wait(unity_driver, _card_active(idx), timeout=2)

            if card:
                hammer_pre  = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))
                card.tap()
                tap_count  += 1
                time.sleep(2)   # build animation
                hammer_post = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))
                logging.info(
                    f"   Tap {tap_count:>2} → Hammer: {_fmt(hammer_pre)} → "
                    f"{_fmt(hammer_post)}  (Δ {_safe_delta(hammer_post, hammer_pre)})"
                )
            else:
                # Card object may temporarily disappear during animation
                time.sleep(2)

            # Check for City Build Reward screen (city completed mid-card)
            if _wait(unity_driver, CB_REWARD_SCREEN, timeout=1):
                logging.info("🏆 City Build reward screen appeared!")
                reward_found = True
                break

            # Check for tick icon (this card is fully built)
            if _wait(unity_driver, _card_tick(idx), timeout=1):
                cards_completed += 1
                hammer_after_card  = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))
                hammers_spent_card = abs(_delta_int(hammer_before_card, hammer_after_card) or 0)

                card_summaries.append((idx + 1, cost_per_tap, tap_count, hammers_spent_card))

                # ── e. Log progress after tick ─────────────────────────
                progress = fast_text(unity_driver, CB_PROGRESS_BAR) or "N/A"
                logging.info(f"   ✅ Card {idx + 1} complete!")
                logging.info(f"      Taps: {tap_count}  |  Hammers spent: {_fmt(hammers_spent_card)}")
                logging.info(f"   📊 Build Progress: {progress}")

                event_tracker.record(
                    "City Build",
                    f"Card {idx + 1}",
                    "PASS",
                    f"{tap_count} taps | {_fmt(hammers_spent_card)} 🔨 | progress {progress}",
                )
                break

        if reward_found:
            break

    # ------------------------------------------------------------------
    # 7. Wait for City Build Reward screen + collect
    # ------------------------------------------------------------------
    if not reward_found:
        # Reward screen might appear shortly after the last tick
        logging.info("⏳ Waiting for City Build Reward screen...")
        reward_found = bool(_wait(unity_driver, CB_REWARD_SCREEN, timeout=10))

    if not reward_found:
        raise Exception("❌ City Build Reward screen never appeared")

    logging.info("🎁 Waiting for Collect Reward button (animation may take a moment)...")

    # ------------------------------------------------------------------
    # 8. Poll until Collect Reward button appears, then tap it
    #    No fixed timeout — keeps retrying until the button is visible.
    #    2-minute ceiling is a safety net against genuine failures.
    # ------------------------------------------------------------------
    collect  = None
    deadline = time.time() + 120   # 2-minute safety ceiling
    while time.time() < deadline:
        collect = _wait(unity_driver, CB_COLLECT, timeout=2)
        if collect:
            logging.info("   ✅ Collect Reward button found")
            break
        logging.info("   ⏳ Button not yet visible — waiting for reward animation...")
        time.sleep(1)

    if not collect:
        raise Exception("❌ Collect Reward button never appeared within 2 minutes")

    collect.tap()
    event_tracker.record("City Build", "Reward Collected", "PASS")

    # ------------------------------------------------------------------
    # 9. Poll until Build Close button appears, then tap it
    #    Replaces the hardcoded 10 s sleep — transitions vary in length
    #    on device so we wait until the button is actually visible.
    #    2-minute safety ceiling prevents an infinite wait on failure.
    # ------------------------------------------------------------------
    logging.info("🔙 Waiting for Build Close button (transition animation)...")
    close    = None
    deadline = time.time() + 120
    while time.time() < deadline:
        close = _wait(unity_driver, CB_CLOSE, timeout=2)
        if close:
            logging.info("   ✅ Close button found")
            break
        logging.info("   ⏳ Close button not yet visible — waiting for animation...")
        time.sleep(1)

    if not close:
        logging.warning("⚠️ Close button never appeared within 2 minutes — continuing anyway")
    else:
        close.tap()
        logging.info("   ✅ Build tray closed")
        time.sleep(1)

    # ------------------------------------------------------------------
    # 10. Clear post-reward popups
    # ------------------------------------------------------------------
    clear_all_popups(unity_driver, timeout=10)

    # ------------------------------------------------------------------
    # 11. Wallet AFTER
    # ------------------------------------------------------------------
    logging.info("📸 Logging wallet AFTER city build...")
    gold_ui_a   = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
    gems_ui_a   = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
    hammer_ui_a = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))
    data_a      = get_wallet_from_data(unity_driver)
    db_a        = get_user_wallet(player_id) if player_id else {}
    _log_snapshot("AFTER", gold_ui_a, gems_ui_a, hammer_ui_a, data_a, db_a)

    # ------------------------------------------------------------------
    # 12. Side-by-side comparison
    # ------------------------------------------------------------------
    _log_comparison(
        gold_b=gold_ui_b,   gold_a=gold_ui_a,
        gems_b=gems_ui_b,   gems_a=gems_ui_a,
        hammer_b=hammer_ui_b, hammer_a=hammer_ui_a,
        data_b=data_b,      data_a=data_a,
        db_b=db_b,          db_a=db_a,
        card_summaries=card_summaries,
    )

    event_tracker.record(
        "City Build",
        "City Complete",
        "PASS",
        f"{cards_completed} cards | "
        f"Gold Δ {_safe_delta(gold_ui_a, gold_ui_b)} | "
        f"Hammer Δ {_safe_delta(hammer_ui_a, hammer_ui_b)}",
    )

    logging.info("✅ test_11_city_build COMPLETE")
