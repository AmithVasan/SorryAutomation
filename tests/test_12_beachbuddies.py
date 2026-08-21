"""
test_12_beachbuddies.py
───────────────────────
Beach Buddies (CoOp LiveOps event) full-play test.

Flow
────
 1. Ensure Home screen, clear popups.
 2. Log Gold/Gems from UI, Data (UserManager) and DB (Mongo).
 3. Top up event ammo in Mongo (bbData.ammAvail) BEFORE opening the event.
 4. Open Beach Buddies from the lobby; confirm the event screen.
 5. For each castle (1-4):
      • Castles 2-4 first show an Invite-Friends modal → accept one invite,
        then re-tap the castle to enter.
      • Inside: set spin multiplier to x10 (highest), log ammo + progress,
        enable autospin (long-press), and handle each milestone reward.
      • 2 milestones + 1 giftbox per castle.  Giftbox = castle complete.
      • Log reward amounts, card-pack presence and ammo consumed per
        milestone / giftbox.
 6. After all castles → Event Complete screen; log + collect rewards.
 7. Close the event, return to lobby.
 8. Print a full Beach Buddies summary.

Design notes
────────────
• All in-modal lookups use _wait() (direct wait_for_object, no popup
  recovery) so the popup handler cannot close an open Beach Buddies modal.
  Only the lobby icon uses wait_for_safe().
• Autospin is toggled by long-pressing the spin button via AltTester
  hold_button() at the button's screen position.
• The multiplier cycles x1→x2→x3→x10; x10 is detected when the
  value_Highest node becomes active.
"""

import time
import logging

from alttester import By

from utils.state_manager import state
from utils.popup_handler import (
    wait_for_safe, safe_tap, clear_all_popups, close_info_screen,
)
from utils.helpers import fast_text, parse_amount, get_wallet_from_data, get_rewards_from_data
from utils.mongo_helper import get_user_wallet, set_beach_buddies_ammo
import utils.event_tracker as event_tracker
from utils.paths import (
    HOME_BUTTON, HOME_GOLD_TEXT, HOME_GEMS_TEXT,
    BB_ICON, BB_LETS_GO, BB_EVENT_BG, BB_AMMO_EVENT,
    BB_CASTLES, BB_AMMO_CASTLE, BB_MULT_NORMAL, BB_MULT_HIGHEST,
    BB_MULT_BUTTON, BB_PROGRESS, BB_SPIN_BTN,
    BB_MILESTONE_CTA, BB_MILESTONE_AMOUNT, BB_MILESTONE_AMOUNT_ANY,
    BB_GIFTBOX_BG, BB_GIFTBOX_COLLECT, BB_GIFTBOX_AMOUNT, BB_GIFTBOX_AMOUNT_ANY,
    BB_GIFTBOX_CARDPACK,
    BB_INVITE_BG, BB_ACCEPT_INVITE_TMPL, BB_INVITE_CLOSE,
    BB_EVENT_COMPLETE_BG, BB_EVENT_COMPLETE_R1, BB_EVENT_COMPLETE_R2,
    BB_EVENT_COMPLETE_R3_CARDPACK, BB_EVENT_COMPLETE_CTA, BB_CLOSE,
)

# -----------------------------------------------------------------------
# TUNABLES
# -----------------------------------------------------------------------
BB_AMMO_TOPUP           = 3000   # bbData.ammAvail set before opening
NUM_CASTLES             = 4
MAX_SEGMENTS_PER_CASTLE = 8      # safety cap on autospin→milestone loops
AUTOSPIN_TIMEOUT        = 120    # seconds to reach a milestone / giftbox


# -----------------------------------------------------------------------
# LOW-LEVEL HELPERS  (direct — no popup recovery, safe inside modals)
# -----------------------------------------------------------------------
def _wait(unity, path, timeout=5):
    try:
        return unity.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _present(unity, path, timeout=1):
    return _wait(unity, path, timeout) is not None


def _text(unity, path, timeout=3):
    return fast_text(unity, path, timeout=timeout)


def _text_any(unity, paths, timeout=3, retries=4):
    """Return the first non-empty, non-zero text among `paths`, retrying a few
    times to let a reward's count-up animation settle."""
    for _ in range(retries):
        for p in paths:
            t = _text(unity, p, timeout)
            if t and t.strip() and t.strip() not in ("0", "—", "-"):
                return t.strip()
        time.sleep(0.7)
    # last-ditch: return whatever the first path yields (even if empty)
    return _text(unity, paths[0], timeout)


# Reward modals — scope the data reader to these so it reads only the reward
# tiles currently on screen.
BB_GIFTBOX_MODAL        = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)"
BB_REWARD_SUMMARY_MODAL = "/Canvas/ModalLayer/RewardSummaryModal(Clone)"


def _rewards_typed(unity, container):
    """Typed reward (label, amount) tuples read straight from the game data,
    scoped to `container`. Returns [] if the reader finds nothing, so the caller
    falls back to its existing amountText read — this can only improve reads."""
    try:
        data = get_rewards_from_data(unity, container=container)
    except Exception:
        data = []
    return [(r["type"], r["amount"]) for r in data]


def _read_event_ammo(unity):
    return parse_amount(_text(unity, BB_AMMO_EVENT, 2))


def _read_event_ammo_settled(unity, max_expected=None, retries=8):
    """Read the event-screen ammo counter reliably.

    Right after a giftbox is collected the view is still transitioning back to
    the event screen, so a single read of BB_AMMO_EVENT often lands before the
    counter exists and returns 0 — which made `total_used` collapse to the full
    starting ammo.  This waits for the event screen and retries until it gets a
    plausible reading (>0 and, if known, not above the pre-castle ammo)."""
    for _ in range(retries):
        if _present(unity, BB_EVENT_BG, 1):
            val = parse_amount(_text(unity, BB_AMMO_EVENT, 2))
            if val and val > 0 and (max_expected is None or val <= max_expected):
                return val
        time.sleep(0.8)
    # best-effort final read (may still be 0 if the screen never settled)
    return parse_amount(_text(unity, BB_AMMO_EVENT, 2))


def _read_castle_ammo(unity):
    return parse_amount(_text(unity, BB_AMMO_CASTLE, 2))


def _read_progress(unity):
    return _text(unity, BB_PROGRESS, 2) or "?"


# -----------------------------------------------------------------------
# WALLET LOGGING (UI vs Data vs DB)
# -----------------------------------------------------------------------
def _log_wallet(unity, phase):
    gold_ui = parse_amount(fast_text(unity, HOME_GOLD_TEXT))
    gems_ui = parse_amount(fast_text(unity, HOME_GEMS_TEXT))
    data = get_wallet_from_data(unity)
    player_id = state.user_info.get("player_id")
    db = get_user_wallet(player_id) if player_id else {}

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 [BB] Wallet ({phase})")
    logging.info(
        f"   🟡 Gold → UI:{gold_ui:<10} Data:{str(data.get('gold')):<10} "
        f"DB:{db.get('gold')}"
    )
    logging.info(
        f"   💎 Gems → UI:{gems_ui:<10} Data:{str(data.get('gems')):<10} "
        f"DB:{db.get('gems')}"
    )
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return {"gold_ui": gold_ui, "gems_ui": gems_ui, "data": data, "db": db}


# -----------------------------------------------------------------------
# SPIN MULTIPLIER — cycle up to x10 (highest)
# -----------------------------------------------------------------------
def _set_multiplier_max(unity):
    """Tap the multiplier until the value_Highest (x10) node is active."""
    for _ in range(6):
        if _present(unity, BB_MULT_HIGHEST, 1):
            logging.info("🔟 [BB] Spin multiplier at x10 (highest)")
            return True
        cur = _text(unity, BB_MULT_NORMAL, 1)
        logging.info(f"   🔁 [BB] Multiplier {cur or '?'} → tapping to increase")
        btn = _wait(unity, BB_MULT_NORMAL, 2) or _wait(unity, BB_MULT_BUTTON, 2)
        if not btn:
            break
        safe_tap(unity, btn)
        time.sleep(0.8)

    if _present(unity, BB_MULT_HIGHEST, 1):
        logging.info("🔟 [BB] Spin multiplier at x10 (highest)")
        return True
    logging.warning("⚠️ [BB] Could not confirm x10 multiplier — using current value")
    return False


# -----------------------------------------------------------------------
# AUTOSPIN — long-press the spin button to toggle autospin on
#
# Autospin is a TOGGLE, not persistent: the game cancels it whenever a
# milestone reward pops, so it must be re-triggered by a fresh long-press
# after every milestone.  A single long-press can also silently fail to
# register (stale coords / mid-animation), so we verify the wheel is
# actually spinning (ammo dropping) and retry the long-press if not.
# -----------------------------------------------------------------------
HOLD_DURATION = 2.0     # seconds to hold the spin button (long-press)


def _long_press_spin(unity):
    """Perform one long-press on the spin button.  Returns False only if the
    button itself can't be located / pressed."""
    spin = _wait(unity, BB_SPIN_BTN, 5)
    if not spin:
        logging.warning("⚠️ [BB] Spin button not found — cannot autospin")
        return False

    # Preferred: AltTester hold_button at the button's current screen position
    try:
        pos = spin.get_screen_position()
        try:
            x, y = pos[0], pos[1]
        except (TypeError, KeyError, IndexError):
            x, y = spin.x, spin.y
        unity.hold_button({"x": x, "y": y}, duration=HOLD_DURATION)
        return True
    except Exception as e:
        logging.warning(f"⚠️ [BB] hold_button failed ({e}) — trying pointer hold")

    # Fallback: pointer_down → wait → pointer_up on the element itself
    try:
        spin.pointer_down()
        time.sleep(HOLD_DURATION)
        spin.pointer_up()
        return True
    except Exception as e:
        logging.error(f"❌ [BB] long-press failed: {e}")
        return False


def _wheel_spinning(unity, settle=3.0):
    """True if castle ammo drops over `settle` seconds → the wheel is spinning."""
    a0 = _read_castle_ammo(unity)
    time.sleep(settle)
    a1 = _read_castle_ammo(unity)
    if a0 is None or a1 is None:
        return False
    return a1 < a0


def _enable_autospin(unity, retries=4):
    """Long-press the spin button and confirm autospin actually started,
    retrying the long-press if the wheel isn't spinning yet."""
    # Make sure we're back on the spin screen (not still on a closing modal)
    for _ in range(10):
        if _present(unity, BB_SPIN_BTN, 1):
            break
        time.sleep(0.5)

    for attempt in range(1, retries + 1):
        if not _long_press_spin(unity):
            time.sleep(1)
            continue

        # A reward may already be showing (autospin reached it instantly)
        if _present(unity, BB_MILESTONE_CTA, 0.4) or _present(unity, BB_GIFTBOX_BG, 0.4):
            logging.info(f"🌀 [BB] Autospin reached a reward immediately (attempt {attempt})")
            return True

        if _wheel_spinning(unity):
            logging.info(f"🌀 [BB] Autospin enabled (long-press, attempt {attempt})")
            return True

        # Reward could have popped during the verification window
        if _present(unity, BB_MILESTONE_CTA, 0.4) or _present(unity, BB_GIFTBOX_BG, 0.4):
            logging.info(f"🌀 [BB] Autospin reached a reward (attempt {attempt})")
            return True

        logging.warning(
            f"⚠️ [BB] Autospin didn't start (attempt {attempt}/{retries}) — "
            f"re-tapping spin button"
        )

    logging.error("❌ [BB] Autospin failed to start after retries")
    return False


def _wait_for_milestone_or_giftbox(unity, timeout=AUTOSPIN_TIMEOUT):
    """Poll until a milestone reward screen OR the giftbox (castle complete)
    appears.  Returns 'giftbox', 'milestone' or None (timed out)."""
    end = time.time() + timeout
    while time.time() < end:
        if _present(unity, BB_GIFTBOX_BG, 0.5):
            return "giftbox"
        if _present(unity, BB_MILESTONE_CTA, 0.5):
            return "milestone"
        time.sleep(1)
    return None


def _wait_for_event_screen(unity, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if _present(unity, BB_EVENT_BG, 1) or _present(unity, BB_EVENT_COMPLETE_BG, 1):
            return True
        time.sleep(1)
    return False


# -----------------------------------------------------------------------
# INVITE FRIENDS (castles 2-4)
# -----------------------------------------------------------------------
def _accept_invite_if_present(unity, castle_num):
    """Handle the Invite-Friends modal for a castle.

    Returns one of:
      • "accepted"       — an invite was accepted (modal closes)
      • "none_available" — modal is up but there's no invite to accept
                           (only Send/Reject items) → modal is closed
      • "no_modal"       — no invite modal was shown
    """
    if not _present(unity, BB_INVITE_BG, 4):
        return "no_modal"

    logging.info(f"👥 [BB] Invite-friends modal for castle {castle_num} — accepting one")
    for n in range(1, 16):
        btn = _wait(unity, BB_ACCEPT_INVITE_TMPL.format(n=n), 0.4)
        if btn:
            safe_tap(unity, btn)
            logging.info(f"   ✅ [BB] Accepted invite (ScrollItem_{n})")
            time.sleep(2)   # modal closes
            return "accepted"

    # No incoming invite to accept — close the modal so the flow can continue
    logging.info(
        f"ℹ️ [BB] No invite to accept for completing castle {castle_num} — moving on"
    )
    close = _wait(unity, BB_INVITE_CLOSE, 3)
    if close:
        safe_tap(unity, close)
        time.sleep(1.5)
    return "none_available"


# -----------------------------------------------------------------------
# OPEN A CASTLE (handles invite gate + entry confirmation)
# -----------------------------------------------------------------------
def _open_castle(unity, castle_num):
    """Open a castle.  Returns:
      • "entered"   — inside the castle (spin screen confirmed)
      • "no_invite" — invite gate had no invite to accept → skip this castle
      • "fail"      — could not open / enter for any other reason
    """
    path = BB_CASTLES[castle_num]

    obj = _wait(unity, path, 8)
    if not obj:
        logging.warning(f"⚠️ [BB] Castle {castle_num} objective not found")
        return "fail"

    safe_tap(unity, obj)
    time.sleep(2)

    # Castles 2-4: an invite gate may appear
    invite = _accept_invite_if_present(unity, castle_num)
    if invite == "none_available":
        return "no_invite"
    if invite == "accepted":
        # re-tap the castle to enter after accepting
        obj = _wait(unity, path, 8)
        if obj:
            safe_tap(unity, obj)
            time.sleep(2)

    if _present(unity, BB_AMMO_CASTLE, 5):
        logging.info(f"🏰 [BB] Inside castle {castle_num}")
        return "entered"

    logging.warning(f"⚠️ [BB] Could not confirm entry into castle {castle_num}")
    return "fail"


# -----------------------------------------------------------------------
# PLAY ONE CASTLE
# -----------------------------------------------------------------------
def _play_castle(unity, castle_num, summary):
    entry = _open_castle(unity, castle_num)

    if entry == "no_invite":
        logging.info(
            f"⏭️ [BB] Castle {castle_num} skipped — no invite to accept for "
            f"completing castle"
        )
        event_tracker.record(
            "Beach Buddies", f"Castle {castle_num}", "SKIP",
            "no invite to accept for completing castle",
        )
        summary.append({"castle": castle_num, "status": "NO_INVITE",
                        "reason": "no invite to accept", "ammo_in": None,
                        "total_used": None, "milestone_deltas": [],
                        "milestone_rewards": [],
                        "giftbox": {"amount": None, "cardpack": False},
                        "giftbox_used": None})
        return False

    if entry != "entered":
        event_tracker.record("Beach Buddies", f"Castle {castle_num}", "FAIL", "could not enter")
        summary.append({"castle": castle_num, "status": "FAIL", "reason": "could not enter",
                        "ammo_in": None, "total_used": None,
                        "milestone_deltas": [], "milestone_rewards": [],
                        "giftbox": {"amount": None, "cardpack": False}, "giftbox_used": None})
        return False

    ammo_in   = _read_castle_ammo(unity)
    progress0 = _read_progress(unity)
    logging.info(f"🏰 [BB] Castle {castle_num} → ammo in hand: {ammo_in} | progress: {progress0}")

    milestone_deltas  = []
    milestone_rewards = []
    giftbox   = {"amount": None, "cardpack": False}
    completed = False

    for seg in range(1, MAX_SEGMENTS_PER_CASTLE + 1):
        _set_multiplier_max(unity)
        seg_ammo_before = _read_castle_ammo(unity)

        if not _enable_autospin(unity):
            break

        outcome = _wait_for_milestone_or_giftbox(unity)

        if outcome == "giftbox":
            time.sleep(5)   # giftbox build animation
            typed    = _rewards_typed(unity, BB_GIFTBOX_MODAL)
            amt      = (", ".join(f"{t}={a}" for t, a in typed)
                        or _text_any(unity, [BB_GIFTBOX_AMOUNT, BB_GIFTBOX_AMOUNT_ANY], 3))
            cardpack = _present(unity, BB_GIFTBOX_CARDPACK, 2)
            giftbox  = {"amount": amt, "cardpack": cardpack}
            logging.info(
                f"🎁 [BB] Castle {castle_num} giftbox → amount:{amt or '—'} "
                f"cardpack:{cardpack}"
            )
            collect = _wait(unity, BB_GIFTBOX_COLLECT, 8)
            if collect:
                safe_tap(unity, collect)
                logging.info("   ✅ [BB] Giftbox collected")
            _wait_for_event_screen(unity, timeout=15)
            completed = True
            break

        if outcome == "milestone":
            time.sleep(2)   # milestone reward animation
            typed = _rewards_typed(unity, BB_REWARD_SUMMARY_MODAL)
            amt = (", ".join(f"{t}={a}" for t, a in typed)
                   or _text_any(unity, [BB_MILESTONE_AMOUNT, BB_MILESTONE_AMOUNT_ANY], 3))
            milestone_rewards.append(amt)
            logging.info(
                f"🏁 [BB] Castle {castle_num} milestone {len(milestone_rewards)} "
                f"reward: {amt or '—'}"
            )
            cta = _wait(unity, BB_MILESTONE_CTA, 8)
            if cta:
                safe_tap(unity, cta)
                time.sleep(3)   # let the modal fully close & spin screen settle

            ammo_after = _read_castle_ammo(unity)
            delta = (seg_ammo_before - ammo_after
                     if seg_ammo_before is not None and ammo_after is not None else None)
            milestone_deltas.append(delta)
            logging.info(
                f"   📊 [BB] Milestone {len(milestone_rewards)} ammo used: {delta} | "
                f"progress now: {_read_progress(unity)}"
            )
            continue

        logging.warning(
            f"⚠️ [BB] Castle {castle_num} seg {seg}: no milestone/giftbox in "
            f"{AUTOSPIN_TIMEOUT}s — stopping this castle"
        )
        break

    # Total + giftbox ammo (event-screen counter shares the same ammo pool as
    # the in-castle counter).  Read it *settled* — a raw read here fires while
    # the view is still returning to the event screen and yields 0, which made
    # total_used wrongly equal the full starting ammo for every castle.
    ammo_after_castle = _read_event_ammo_settled(unity, max_expected=ammo_in)
    total_used = (ammo_in - ammo_after_castle
                  if ammo_in and ammo_after_castle else None)
    giftbox_used = None
    if total_used is not None:
        used_ms = sum(d for d in milestone_deltas if d)
        giftbox_used = total_used - used_ms

    status = "PASS" if completed else "FAIL"
    logging.info("─" * 50)
    logging.info(f"🏰 [BB] Castle {castle_num} SUMMARY  [{status}]")
    for i, (d, r) in enumerate(zip(milestone_deltas, milestone_rewards), 1):
        logging.info(f"   Milestone {i}: reward {r or '—'}, ammo used {d}")
    logging.info(
        f"   Giftbox: reward {giftbox['amount'] or '—'} "
        f"cardpack:{giftbox['cardpack']}, ammo used {giftbox_used}"
    )
    logging.info(f"   Total ammo used this castle: {total_used}")
    logging.info("─" * 50)

    event_tracker.record(
        "Beach Buddies", f"Castle {castle_num}", status,
        f"{len(milestone_rewards)} milestones, ammo used {total_used}",
    )
    summary.append({
        "castle": castle_num, "status": status,
        "ammo_in": ammo_in, "total_used": total_used,
        "milestone_deltas": milestone_deltas, "milestone_rewards": milestone_rewards,
        "giftbox": giftbox, "giftbox_used": giftbox_used,
    })
    return completed


# -----------------------------------------------------------------------
# EVENT COMPLETE
# -----------------------------------------------------------------------
def _handle_event_complete(unity, summary):
    if not _present(unity, BB_EVENT_COMPLETE_BG, 15):
        logging.info("ℹ️ [BB] No event-complete screen detected")
        return

    time.sleep(5)   # completion animation
    # Rewards count up from 0, so a single read lands on "0"/empty and logged
    # "—".  Use the retrying reader that skips 0 to catch the settled value.
    # The event-complete screen is a RewardSummaryModal, so the milestone
    # "any amountText" wildcard is a valid fallback for the first reward.
    typed = _rewards_typed(unity, BB_REWARD_SUMMARY_MODAL)
    if typed:
        parts = [f"{t}={a}" for t, a in typed]
        r1 = parts[0] if len(parts) > 0 else None
        r2 = parts[1] if len(parts) > 1 else None
    else:
        r1 = _text_any(unity, [BB_EVENT_COMPLETE_R1, BB_MILESTONE_AMOUNT_ANY], 3)
        r2 = _text_any(unity, [BB_EVENT_COMPLETE_R2], 3)
    r3_cardpack = _present(unity, BB_EVENT_COMPLETE_R3_CARDPACK, 2)

    logging.info("🎉 [BB] EVENT COMPLETE rewards:")
    logging.info(f"   Reward 1: {r1 or '—'}")
    logging.info(f"   Reward 2: {r2 or '—'}")
    logging.info(f"   Reward 3: {'card pack' if r3_cardpack else '—'}")

    cta = _wait(unity, BB_EVENT_COMPLETE_CTA, 8)
    if cta:
        safe_tap(unity, cta)
        logging.info("   ✅ [BB] Event rewards collected")
        time.sleep(2)

    event_tracker.record(
        "Beach Buddies", "Event Complete", "PASS",
        f"R1:{r1 or '-'} R2:{r2 or '-'} R3:{'cardpack' if r3_cardpack else '-'}",
    )
    summary.append({"event_complete": {"r1": r1, "r2": r2, "cardpack": r3_cardpack}})


# -----------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------
def _print_summary(summary, start_ammo):
    logging.info("=" * 60)
    logging.info("🏖️ BEACH BUDDIES — FINAL SUMMARY")
    logging.info(f"   Starting event ammo: {start_ammo}")
    for entry in summary:
        if "castle" in entry:
            if entry["status"] in ("NO_INVITE", "FAIL"):
                reason = entry.get("reason", "")
                logging.info(
                    f"   🏰 Castle {entry['castle']} [{entry['status']}]"
                    f"{' — ' + reason if reason else ''}"
                )
                continue
            logging.info(
                f"   🏰 Castle {entry['castle']} [{entry['status']}] — "
                f"ammo in:{entry['ammo_in']} used:{entry['total_used']}"
            )
            for i, (d, r) in enumerate(
                zip(entry["milestone_deltas"], entry["milestone_rewards"]), 1
            ):
                logging.info(f"       Milestone {i}: reward {r or '—'}, ammo used {d}")
            gb = entry["giftbox"]
            logging.info(
                f"       Giftbox: reward {gb['amount'] or '—'} "
                f"cardpack:{gb['cardpack']} ammo used {entry['giftbox_used']}"
            )
        elif "event_complete" in entry:
            ec = entry["event_complete"]
            logging.info(
                f"   🎉 Event Complete: R1:{ec['r1'] or '—'} R2:{ec['r2'] or '—'} "
                f"R3:{'cardpack' if ec['cardpack'] else '—'}"
            )
    logging.info("=" * 60)


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_beach_buddies(unity_driver, driver=None):
    logging.info("🏖️ ── test_12_beachbuddies START ──")

    # ── 1. Home + clear popups ───────────────────────────────────────
    home = _wait(unity_driver, HOME_BUTTON, 5)
    if home:
        safe_tap(unity_driver, home)
        time.sleep(1.5)
    clear_all_popups(unity_driver)

    # ── 2. Wallet snapshot (before) ──────────────────────────────────
    _log_wallet(unity_driver, "before Beach Buddies")

    # ── 3. Top up event ammo in Mongo BEFORE opening the event ───────
    player_id = state.user_info.get("player_id")
    if not player_id:
        logging.warning("⚠️ [BB] player_id missing — skipping Mongo ammo top-up")
    else:
        set_beach_buddies_ammo(player_id, BB_AMMO_TOPUP)
        time.sleep(2)

    # ── 4. Open Beach Buddies ────────────────────────────────────────
    icon = wait_for_safe(unity_driver, By.PATH, BB_ICON, 15)
    if not icon:
        raise Exception("❌ [BB] Beach Buddies lobby icon not found")
    safe_tap(unity_driver, icon)
    time.sleep(3)

    # Dismiss a start popup / info screen if one appears
    lets_go = _wait(unity_driver, BB_LETS_GO, 3)
    if lets_go:
        safe_tap(unity_driver, lets_go)
        time.sleep(2)
    clear_all_popups(unity_driver)
    if not _present(unity_driver, BB_EVENT_BG, 8):
        close_info_screen(unity_driver)
        time.sleep(1)

    if not _present(unity_driver, BB_EVENT_BG, 10):
        raise Exception("❌ [BB] Beach Buddies event screen did not open")
    logging.info("🏖️ [BB] Beach Buddies event screen open")

    start_ammo = _read_event_ammo(unity_driver)
    logging.info(f"🔫 [BB] Total ammo in hand (event screen): {start_ammo}")

    # ── 5. Play all castles ──────────────────────────────────────────
    summary = []
    for castle_num in range(1, NUM_CASTLES + 1):
        logging.info(f"▶️ [BB] ── Castle {castle_num} ──")
        _play_castle(unity_driver, castle_num, summary)
        time.sleep(2)
        clear_all_popups(unity_driver)

    # ── 6. Event complete ────────────────────────────────────────────
    _handle_event_complete(unity_driver, summary)

    # ── 7. Close → lobby ─────────────────────────────────────────────
    close = _wait(unity_driver, BB_CLOSE, 8)
    if close:
        safe_tap(unity_driver, close)
        time.sleep(2)
    home = _wait(unity_driver, HOME_BUTTON, 5)
    if home:
        safe_tap(unity_driver, home)
        time.sleep(1)
    clear_all_popups(unity_driver)

    # ── 8. Wallet snapshot (after) + summary ─────────────────────────
    _log_wallet(unity_driver, "after Beach Buddies")
    _print_summary(summary, start_ammo)

    return unity_driver
