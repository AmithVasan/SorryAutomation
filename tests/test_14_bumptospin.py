"""
test_14_bumptospin.py
─────────────────────
Bump To Spin (BTS) full-play test.

Flow
────
 1. Ensure lobby + clear popups.  Open profile → log the equipped cosmetic
    (before).  Close profile → log wallet (UI / Data / DB).
 2. Open BTS.  Handle the FTUE free-ammo claim modal (log the free ammo, claim).
 3. Log total ammo in hand.
 4. KILL game → boost ammo in Mongo (bmpToSpn.ammo = 500) → LAUNCH → reconnect
    AltTester → clear lobby popups → reopen BTS.
 5. Set the spin multiplier to x10 (highest).
 6. Hold-to-autospin until every tier unlocks — detected by autospin stopping
    (ammo stops dropping) and/or the progress tooltip reading a full "xxx/xxx".
    Log "All tiers unlocked".
 7. Buy the Royal Pass:
      • disable (ignore) the Royal Pass close in the popup handler,
      • Activate → Royal Pass modal → Buy → Google Play purchase (handled like
        every other IAP) → in-game purchase-success modal → OK.
 8. Claim every tier (scales automatically to however many exist): read + log
    each tier's reward values, tap the free + royal/paid claim buttons.  Dismiss
    any Lootbox reward screen and Equip the Pawn cosmetic as they surface.
 9. Confirm no tier still has a claimable state — cross-checked against the DB
    (bmpToSpn.frePsClms / rylPsClms / isRylPsActv).  If the royal/paid rewards
    never became claimable the Royal Pass purchase FAILED.
10. Re-enable the Royal Pass close handler, close BTS → lobby.
11. Open profile → confirm the cosmetic is now equipped (changed).
12. Summary: per-tier reward values, free/paid tiers claimed, wallet delta
    (UI / Data / DB).

Design notes
────────────
• Multiplier + autospin are the SAME mechanic as Beach Buddies (test_12).
• There is a game RELAUNCH after the ammo boost — the reconnected unity_driver
  is returned so the runner keeps using the live one.
• The reward track is a scrollView; the claim loop scans the rendered tiers and
  swipes to reveal the rest, indexing tiers dynamically, so it keeps working if
  tiers are added or removed.
• DB fields verified against a live doc:  bmpToSpn.ammo (spins),
  bmpToSpn.pnts (tier points), bmpToSpn.isRylPsActv (royal pass bought),
  bmpToSpn.frePsClms / rylPsClms  ({tier: {}} maps of claimed tiers).
"""

import re
import time
import logging
import subprocess

from alttester import By

from utils.state_manager import state
import utils.popup_handler as popup_handler
from utils.popup_handler import (
    wait_for_safe, safe_tap, clear_all_popups, handle_one_popup, close_info_screen,
)
from utils.helpers import (
    fast_text, safe_text, parse_amount, get_wallet_from_data, get_user_snapshot,
    get_rewards_from_data,
)
from utils.mongo_helper import (
    get_user_wallet, get_user_from_db, set_bump_to_spin_ammo,
)
from utils.driver_manager import connect_altunity
from utils.google_play_helper import (
    handle_google_play_purchase, close_extra_google_play_popups, reconnect_alttester,
)
import utils.event_tracker as event_tracker
from config import ADB_PATH, PACKAGE_NAME, ACTIVITY_NAME, ALTTESTER_PORT, APP_NAME
from utils.paths import (
    HOME_BUTTON, HOME_GOLD_TEXT, HOME_GEMS_TEXT, HOME_HAMMER_TEXT,
    PROFILE_BUTTON, PROFILE_CLOSE, PROFILE_PAWN,
    BTS_ICON, BTS_MODAL, BTS_FTUE_MODAL, BTS_FREE_AMMO_MODAL,
    BTS_FREE_AMMO_CONTAINER, BTS_FREE_AMMO_COUNT, BTS_CLAIM, BTS_TOTAL_AMMO,
    BTS_MULT_HIGHEST, BTS_MULT_NORMAL, BTS_MULT_BUTTON, BTS_SPIN_BTN, BTS_PROGRESS,
    BTS_ACTIVATE_BTN, BTS_ROYAL_MODAL, BTS_ROYAL_CLOSE, BTS_ROYAL_BUY,
    BTS_PURCHASE_SUCCESS, BTS_PURCHASE_OK,
    BTS_TIER_CONTENT, BTS_TIER_ITEM_TMPL, BTS_CLOSE,
    PAWN_REWARDS_MODAL, PAWN_REWARDS_EQUIP, PAWN_REWARDS_CONTINUE,
    REWARD_SUMMARY_CTA, LOOTBOX_CLAIM,
)

# -----------------------------------------------------------------------
# TUNABLES
# -----------------------------------------------------------------------
BTS_AMMO_TOPUP    = 500    # bmpToSpn.ammo set before relaunch
MAX_TIERS         = 20     # safety cap on the tier loop (15 today; headroom)
MULT_TAPS         = 8      # max multiplier cycles to reach x10
AUTOSPIN_TIMEOUT  = 300    # secs allowed to reach "all tiers unlocked"
HOLD_DURATION     = 2.0    # spin-button long-press duration (autospin)


# -----------------------------------------------------------------------
# LOW-LEVEL HELPERS  (direct wait_for_object — safe inside the BTS modal)
# -----------------------------------------------------------------------
def _wait(unity, path, timeout=5):
    try:
        return unity.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


def _present(unity, path, timeout=1):
    return _wait(unity, path, timeout) is not None


def _text(unity, path, timeout=2):
    return fast_text(unity, path, timeout=timeout)


def _num(unity, path, timeout=2):
    return parse_amount(_text(unity, path, timeout))


def _obj_text(obj):
    """Read the TMP text off an AltObject (get_text, then component property)."""
    try:
        t = obj.get_text()
        if t is not None and str(t).strip() not in ("", "N/A"):
            return str(t).strip()
    except Exception:
        pass
    return safe_text(obj)


def _scan_amounts(unity, container_path):
    """Pull every reward AMOUNT under a container as (raw_text, number), WITHOUT
    logging.  Index-independent (grabs all `amountText` value nodes rather than
    an exact `.../SpriteRewardItem_N/...` path).  parse_amount handles plain
    numbers and the 1.3k / 2.05M shorthand."""
    nodes = []
    for pat in ("//amountText/text", "//amountText"):
        try:
            found = unity.find_objects(By.PATH, container_path + pat)
        except Exception:
            found = []
        if found:
            nodes = found
            break

    out = []
    for n in nodes:
        raw = _obj_text(n)
        if raw:
            out.append((raw, parse_amount(raw)))
    return out


def _rewards(unity, container_path):
    """Reward (label, amount) pairs for the reward area currently showing.

    Prefers reading the game's reward components directly via
    get_rewards_from_data() — returns the reward TYPE name + raw amount, e.g.
    ("Gold", 1500) — scoped to `container_path`. Falls back to scanning the UI
    amountText under `container_path` when that returns nothing, so it can only
    improve the reads, never regress them."""
    try:
        data = get_rewards_from_data(unity, container=container_path)
    except Exception:
        data = []
    if data:
        return [(r["type"], r["amount"]) for r in data]
    return _scan_amounts(unity, container_path)


def _read_progress_pair(unity):
    """Parse the tier-progress tooltip ('910/910') → (num, den, raw)."""
    raw = _text(unity, BTS_PROGRESS, 2) or ""
    nums = re.findall(r"\d[\d,]*", raw)
    if len(nums) >= 2:
        return parse_amount(nums[0]), parse_amount(nums[1]), raw.strip()
    return None, None, raw.strip()


# -----------------------------------------------------------------------
# WALLET LOGGING (UI / Data / DB)
# -----------------------------------------------------------------------
def _log_wallet(unity, phase, player_id):
    gold_ui   = parse_amount(fast_text(unity, HOME_GOLD_TEXT))
    gems_ui   = parse_amount(fast_text(unity, HOME_GEMS_TEXT))
    hammer_ui = parse_amount(fast_text(unity, HOME_HAMMER_TEXT))
    data = get_wallet_from_data(unity)                       # gold / gems / pips
    db   = get_user_wallet(player_id) if player_id else {}   # gold / gems / pips

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 [BTS] Wallet ({phase})")
    logging.info(f"   🟡 Gold   → UI:{gold_ui:<10} Data:{str(data.get('gold')):<10} DB:{db.get('gold')}")
    logging.info(f"   💎 Gems   → UI:{gems_ui:<10} Data:{str(data.get('gems')):<10} DB:{db.get('gems')}")
    logging.info(f"   🔨 Hammer → UI:{hammer_ui:<10} Data:{str(data.get('pips')):<10} DB:{db.get('pips')}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return {"gold_ui": gold_ui, "gems_ui": gems_ui, "hammer_ui": hammer_ui,
            "data": data, "db": db}


# -----------------------------------------------------------------------
# PROFILE — read the equipped cosmetic
# -----------------------------------------------------------------------
def _read_equipped_cosmetic(unity):
    """Open the profile, read the equipped pawn cosmetic name, close it."""
    prof = wait_for_safe(unity, By.PATH, PROFILE_BUTTON, 6)
    if not prof:
        logging.warning("⚠️ [BTS] Profile button not found")
        return None
    safe_tap(unity, prof)
    time.sleep(1.2)
    name = fast_text(unity, PROFILE_PAWN, 4)
    close = wait_for_safe(unity, By.PATH, PROFILE_CLOSE, 4)
    if close:
        safe_tap(unity, close)
        time.sleep(0.8)
    return name


# -----------------------------------------------------------------------
# OPEN BTS  +  FTUE FREE-AMMO CLAIM
# -----------------------------------------------------------------------
def _handle_free_ammo_ftue(unity):
    """First open shows a free-ammo claim modal — log the amount, claim it."""
    if _present(unity, BTS_FTUE_MODAL, 4) or _present(unity, BTS_FREE_AMMO_MODAL, 2):
        amounts = _rewards(unity, BTS_FREE_AMMO_CONTAINER)
        raw = (", ".join(f"{r}={v}" for r, v in amounts)
               or (fast_text(unity, BTS_FREE_AMMO_COUNT) or "—"))
        logging.info(f"🎁 [BTS] FTUE free ammo: {raw}")
        claim = wait_for_safe(unity, By.PATH, BTS_CLAIM, 8)
        if claim:
            safe_tap(unity, claim)
            time.sleep(1.5)   # ~1s claim animation
            logging.info("✅ [BTS] Free ammo claimed")
        return True
    logging.info("ℹ️ [BTS] No FTUE free-ammo modal (already claimed)")
    return False


def _open_bts(unity):
    """Tap the lobby icon, handle the FTUE free-ammo modal, confirm the modal."""
    icon = wait_for_safe(unity, By.PATH, BTS_ICON, 15)
    if not icon:
        return False
    safe_tap(unity, icon)
    time.sleep(4)             # open animation + screen load
    _handle_free_ammo_ftue(unity)
    clear_all_popups(unity)   # any lobby popup that rode in
    return (_present(unity, BTS_MODAL, 8)
            or _present(unity, BTS_TOTAL_AMMO, 4)
            or _present(unity, BTS_SPIN_BTN, 4))


# -----------------------------------------------------------------------
# KILL → BOOST → LAUNCH   (see the identical note in Treasure Island)
# -----------------------------------------------------------------------
def _kill_game(unity_driver):
    device_id = state.get("device_id")
    try:
        unity_driver.stop()
    except Exception:
        pass
    if device_id:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "am", "force-stop", PACKAGE_NAME],
            check=False,
        )
        logging.info("🛑 [BTS] Game force-stopped")
        time.sleep(3)   # let the process fully die before we write the boost
    else:
        logging.warning("⚠️ [BTS] device_id missing — cannot force-stop via ADB")
    return device_id


def _launch_and_reconnect(device_id):
    if device_id:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "am", "start",
             "-n", f"{PACKAGE_NAME}/{ACTIVITY_NAME}"],
            check=False,
        )
    logging.info("🎮 [BTS] Game launched — waiting for AltTester to register...")
    time.sleep(10)
    new_driver = connect_altunity(alt_port=ALTTESTER_PORT, app_name=APP_NAME)
    state.set("unity_driver", new_driver)
    logging.info("✅ [BTS] AltTester reconnected after launch")
    return new_driver


# -----------------------------------------------------------------------
# SPIN MULTIPLIER — cycle up to x10 (highest)  [same as Beach Buddies]
# -----------------------------------------------------------------------
def _set_multiplier_max(unity):
    for _ in range(MULT_TAPS):
        if _present(unity, BTS_MULT_HIGHEST, 1):
            logging.info("🔟 [BTS] Spin multiplier at x10 (highest)")
            return True
        cur = _text(unity, BTS_MULT_NORMAL, 1)
        btn = _wait(unity, BTS_MULT_BUTTON, 2) or _wait(unity, BTS_MULT_NORMAL, 2)
        if not btn:
            break
        logging.info(f"   🔁 [BTS] Multiplier {cur or '?'} → tapping to increase")
        safe_tap(unity, btn)
        time.sleep(0.8)

    if _present(unity, BTS_MULT_HIGHEST, 1):
        logging.info("🔟 [BTS] Spin multiplier at x10 (highest)")
        return True
    logging.warning("⚠️ [BTS] Could not confirm x10 multiplier — using current value")
    return False


# -----------------------------------------------------------------------
# AUTOSPIN — long-press the spin button  [same as Beach Buddies]
# -----------------------------------------------------------------------
def _long_press_spin(unity):
    spin = _wait(unity, BTS_SPIN_BTN, 5)
    if not spin:
        logging.warning("⚠️ [BTS] Spin button not found — cannot autospin")
        return False
    try:
        pos = spin.get_screen_position()
        try:
            x, y = pos[0], pos[1]
        except (TypeError, KeyError, IndexError):
            x, y = spin.x, spin.y
        unity.hold_button({"x": x, "y": y}, duration=HOLD_DURATION)
        return True
    except Exception as e:
        logging.warning(f"⚠️ [BTS] hold_button failed ({e}) — trying pointer hold")
    try:
        spin.pointer_down()
        time.sleep(HOLD_DURATION)
        spin.pointer_up()
        return True
    except Exception as e:
        logging.error(f"❌ [BTS] long-press failed: {e}")
        return False


def _clear_bts_overlays(unity, rounds=4):
    """Close popups / info screens that surface ON the BTS modal (they block the
    spin button and interrupt autospin — e.g. the BumpToSpin info modal, League,
    Edlp).  Uses the popup handler + the topmost-tap info closer.  Never taps the
    BTS modal's own close / spin / activate.  Returns True if it dismissed
    anything."""
    acted = False
    for _ in range(rounds):
        did = False
        if _present(unity, "/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)", 0.4):
            close_info_screen(unity)
            did = acted = True
            time.sleep(0.6)
        if handle_one_popup(unity):     # League / Edlp / Fortune Island / etc.
            did = acted = True
            time.sleep(0.4)
        if not did:
            break
    return acted


def _autospin_until_unlocked(unity, player_id):
    """Autospin until every tier is unlocked.

    IMPORTANT: autospin is a TOGGLE — a long-press STARTS it and a second
    long-press STOPS it.  So we press ONCE, then just watch progress; we only
    ever re-hold after the wheel has genuinely gone idle (which usually means an
    overlay interrupted it — so we clear overlays first).  "Spinning" is
    detected by on-screen ammo dropping OR the DB tier-points increasing
    (authoritative), so a laggy on-screen counter never triggers a false
    re-hold that would toggle autospin off.  There is no completion screen — the
    wheel simply stops once all tiers unlock (or the progress tooltip reads a
    full 'xxx/xxx')."""

    def _db_points():
        try:
            d = get_user_from_db(player_id) or {}
            return (d.get("bmpToSpn") or {}).get("pnts")
        except Exception:
            return None

    _clear_bts_overlays(unity)             # nothing on top of the spin button
    ammo_prev = _num(unity, BTS_TOTAL_AMMO, 2)
    pts_prev  = _db_points()
    _long_press_spin(unity)                # START autospin (ONCE)
    logging.info(f"🌀 [BTS] Autospin started (ammo {ammo_prev}, points {pts_prev})")

    end         = time.time() + AUTOSPIN_TIMEOUT
    last_change = time.time()
    reholds     = 0
    spun        = False

    while time.time() < end:
        # 1. Progress tooltip full → definitely done
        pa, pb, raw = _read_progress_pair(unity)
        if pa is not None and pb and pa >= pb:
            logging.info(f"🎯 [BTS] Tier progress full ({raw}) — all tiers unlocked")
            return True

        time.sleep(5)
        ammo = _num(unity, BTS_TOTAL_AMMO, 2)
        moved = (ammo is not None and ammo_prev is not None and ammo < ammo_prev)
        if ammo is not None:
            ammo_prev = ammo if ammo_prev is None else min(ammo_prev, ammo)

        if moved:
            spun = True
            last_change = time.time()
            logging.info(f"🌀 [BTS] autospin… ammo now {ammo} | progress {raw or '?'}")
            continue

        # ammo not visibly dropping — cross-check DB tier-points before deciding
        pts = _db_points()
        if pts is not None and pts_prev is not None and pts > pts_prev:
            spun = True
            pts_prev = pts
            last_change = time.time()
            logging.info(f"🌀 [BTS] autospin… points now {pts}")
            continue
        if pts is not None:
            pts_prev = pts

        # ammo exhausted → done
        if ammo is not None and ammo <= 0:
            logging.info("🎯 [BTS] Ammo exhausted — autospin done")
            return spun

        idle = time.time() - last_change
        # Genuinely idle → an overlay may have interrupted autospin, or it
        # stopped because all tiers unlocked.  Clear overlays and re-hold ONCE
        # to resume; bounded so we never sit toggling it on/off.
        if idle > 10 and reholds < 4:
            logging.info(
                f"🔁 [BTS] Wheel idle {idle:.0f}s — clearing overlays & re-holding "
                f"({reholds + 1})"
            )
            _clear_bts_overlays(unity)
            _long_press_spin(unity)
            reholds += 1
            last_change = time.time()
            continue
        if idle > 28:
            logging.info("🎯 [BTS] Autospin stopped (idle) — assuming all tiers unlocked")
            return spun

    logging.warning("⚠️ [BTS] Autospin timed out before confirming all tiers unlocked")
    return spun


# -----------------------------------------------------------------------
# BUY THE ROYAL PASS  (mirrors the Season Pass IAP flow)
# -----------------------------------------------------------------------
def _buy_royal_pass(unity, driver):
    """Activate → Royal Pass modal → Buy → Google Play → success → OK.

    Assumes BTS_ROYAL_CLOSE has already been ignore_popup()'d by the caller so
    the popup handler doesn't auto-close the modal mid-purchase.
    Returns (unity_driver, driver, success).
    """
    logging.info("💰 [BTS] Buying Royal Pass")

    # Activate → opens the Royal Pass purchase modal
    activate = wait_for_safe(unity, By.PATH, BTS_ACTIVATE_BTN, 20)
    if not activate:
        raise Exception("❌ [BTS] Activate button not found")
    safe_tap(unity, activate)
    time.sleep(4)

    if not _present(unity, BTS_ROYAL_MODAL, 10):
        logging.warning("⚠️ [BTS] Royal Pass modal not detected after Activate")

    buy = wait_for_safe(unity, By.PATH, BTS_ROYAL_BUY, 20)
    if not buy:
        raise Exception("❌ [BTS] Royal Pass buy button not found")
    safe_tap(unity, buy)
    logging.info("✅ [BTS] Royal Pass buy tapped")
    time.sleep(5)

    # Recover the Appium session if the buy tap killed it
    try:
        driver.current_activity
        logging.info("✅ [BTS] Appium session alive")
    except Exception:
        logging.warning("⚠️ [BTS] Appium session dead → reconnecting")
        from utils.driver_manager import set_driver
        driver, _ = set_driver(
            device_id=state.get("device_id"),
            app_package=PACKAGE_NAME, app_activity=ACTIVITY_NAME,
            connect_alt=False,
        )
        state.set("appium_driver", driver)
        logging.info("✅ [BTS] Appium reconnected")

    # Google Play purchase
    purchase_success, driver = handle_google_play_purchase(driver)
    state.set("appium_driver", driver)

    if not purchase_success:
        logging.warning("⚠️ [BTS] Google Play timed out — checking in-game success modal...")
        try:
            unity = reconnect_alttester(unity)
            state.set("unity_driver", unity)
            if wait_for_safe(unity, By.PATH, BTS_PURCHASE_SUCCESS, 15):
                logging.info("✅ [BTS] Purchase success modal found — purchase DID complete")
                purchase_success = True
        except Exception as fallback_err:
            logging.warning(f"⚠️ [BTS] Fallback modal check failed: {fallback_err}")

    if not purchase_success:
        raise Exception("❌ [BTS] Google Play purchase failed")

    logging.info("✅ [BTS] Google Play purchase completed")

    # Clean any extra Google Play popups still on screen
    gp_end = time.time() + 8
    while time.time() < gp_end:
        try:
            if driver.current_package == "com.android.vending":
                _, driver = close_extra_google_play_popups(driver, timeout=5)
            else:
                break
        except Exception:
            pass
        time.sleep(1)

    time.sleep(10)   # let the game screen return

    # Reconnect AltTester (game was pushed behind Google Play)
    unity = reconnect_alttester(unity)
    state.set("unity_driver", unity)
    logging.info("✅ [BTS] AltTester reconnected after purchase")

    # In-game purchase-success modal → OK
    if wait_for_safe(unity, By.PATH, BTS_PURCHASE_SUCCESS, 15):
        logging.info("✅ [BTS] Purchase success modal detected")
        ok = wait_for_safe(unity, By.PATH, BTS_PURCHASE_OK, 10)
        if ok:
            safe_tap(unity, ok)
            time.sleep(2)
            logging.info("✅ [BTS] Purchase success OK tapped")
    else:
        logging.warning("⚠️ [BTS] Purchase success modal not found — continuing")

    return unity, driver, True


# -----------------------------------------------------------------------
# REWARD SCREENS surfaced WHILE claiming tiers
# -----------------------------------------------------------------------
def _tap_screen_center(unity):
    """Raw ADB 'tap anywhere' — some lootbox reward screens don't register a
    tap on the CTA element and need a raw screen tap to dismiss (same trick the
    Shop lootbox uses)."""
    device_id = state.get("device_id")
    if not device_id:
        return
    try:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "input", "tap", "540", "1200"],
            check=False,
        )
    except Exception:
        pass


def _drain_lootboxes(unity, max_boxes=15):
    """Dismiss CONSECUTIVE Lootbox reward screens.

    A single claim can spawn several lootbox screens back-to-back, each with a
    transition animation between them — so after dismissing one we wait a few
    seconds for the NEXT to render before concluding they're done (a 1s look
    gives up too early and leaves the 2nd box open, which then blocks the later
    tiers).  Element tap first; a raw screen-tap is the fallback AND the way we
    confirm each box actually closed.  Returns the count dismissed."""
    dismissed = 0
    for _ in range(max_boxes):
        lb = wait_for_safe(unity, By.PATH, LOOTBOX_CLAIM, 4)   # patient: wait for the next box
        if not lb:
            break
        time.sleep(1.5)                     # let the reward animation settle
        try:
            safe_tap(unity, lb)
        except Exception:
            _tap_screen_center(unity)
        # Confirm THIS screen is gone before looking for the next; raw-tap retry.
        gone_end = time.time() + 8
        while time.time() < gone_end:
            if not wait_for_safe(unity, By.PATH, LOOTBOX_CLAIM, 1):
                break
            _tap_screen_center(unity)
            time.sleep(1)
        dismissed += 1
        logging.info(f"   📦 [BTS] Lootbox reward screen #{dismissed} dismissed")
        time.sleep(1)                       # transition before the next renders
    return dismissed


def _drain_bts_reward_screens(unity, rounds=10):
    """Dismiss reward screens that appear while claiming a tier:
       • Lootbox reward screen(s) → drain ALL consecutive ones (tap-to-continue)
       • Pawn cosmetic reward     → Equip (this is what equips the cosmetic)
       • Reward Summary modal      → tap CTA
    Loops until a full pass finds nothing.  Returns True if anything was
    dismissed."""
    acted = False
    for _ in range(rounds):
        did = False

        if wait_for_safe(unity, By.PATH, LOOTBOX_CLAIM, 1):
            if _drain_lootboxes(unity):
                did = acted = True

        if wait_for_safe(unity, By.PATH, PAWN_REWARDS_MODAL, 1):
            btn = (wait_for_safe(unity, By.PATH, PAWN_REWARDS_EQUIP, 2)
                   or wait_for_safe(unity, By.PATH, PAWN_REWARDS_CONTINUE, 2))
            if btn:
                safe_tap(unity, btn)
                logging.info("   🎭 [BTS] Pawn cosmetic reward → Equip tapped")
                time.sleep(2)   # ~2s equip animation
                did = acted = True

        rs = wait_for_safe(unity, By.PATH, REWARD_SUMMARY_CTA, 1)
        if rs:
            time.sleep(1)
            safe_tap(unity, rs)
            logging.info("   🎬 [BTS] Reward Summary dismissed")
            time.sleep(1)
            did = acted = True

        if not did:
            break
    return acted


# -----------------------------------------------------------------------
# TIER CLAIMING
#
# Claim button path (confirmed):
#   .../BumpToSpinTierScrollItem_{n}/<section>/SorryButtonType-Text/TouchArea
# where <section> is `freePass` (free reward) or `royalPass` (royal/paid).
#
# The slots all exist in the scroll content and AltTester taps them even when
# scrolled off-screen — exactly like the Shop packs — so we claim by slot path
# DIRECTLY, no scrolling.  The list auto-scrolls to the top (the HIGHEST tier),
# and is shown in DECREASING order, so slot N maps to game tier (count - N + 1)
# (slot 1 = top = highest claimable tier; tier 15 is auto-granted).
# -----------------------------------------------------------------------
CLAIM_SECTIONS = (("freePass", "free"), ("royalPass", "royal"), ("bonusPass", "royal"))


def _claim_tier_button(unity, slot_n, section):
    p = BTS_TIER_ITEM_TMPL.format(n=slot_n) + f"/{section}/SorryButtonType-Text/TouchArea"
    return _wait(unity, p, 0.15)


def _quick_dismiss(unity):
    """Fast, non-patient dismissal after claiming a tier that HAS reward values
    (so it can't be a lootbox): clears a Reward Summary / Pawn cosmetic that
    occasionally rides along, WITHOUT the slow patient lootbox wait."""
    for _ in range(2):
        did = False
        rs = wait_for_safe(unity, By.PATH, REWARD_SUMMARY_CTA, 0.4)
        if rs:
            safe_tap(unity, rs)
            time.sleep(0.8)
            did = True
        if wait_for_safe(unity, By.PATH, PAWN_REWARDS_MODAL, 0.4):
            btn = (wait_for_safe(unity, By.PATH, PAWN_REWARDS_EQUIP, 1)
                   or wait_for_safe(unity, By.PATH, PAWN_REWARDS_CONTINUE, 1))
            if btn:
                safe_tap(unity, btn)
                logging.info("   🎭 [BTS] Pawn cosmetic reward → Equip tapped")
                time.sleep(1.5)
                did = True
        if not did:
            break


def _claim_all_tiers(unity):
    """Claim the free + royal reward on every tier — by slot path, no scrolling.

    Lootbox rule (per feedback): a tier whose reward shows a numeric value can't
    be a lootbox, so we skip the slow lootbox wait for it; only a value-less
    tier can drop a lootbox reward screen, so we drain then.

    Returns (per_tier_rewards, {"free": n, "royal": n})."""
    logging.info("🎁 [BTS] Claiming all tier rewards")

    # Discover the claimable slots that exist (scales if tiers are added/removed)
    slots = [n for n in range(1, MAX_TIERS + 1)
             if _wait(unity, BTS_TIER_ITEM_TMPL.format(n=n), 0.15)]
    count = len(slots)
    logging.info(f"🎁 [BTS] {count} claimable tier slots detected: {slots}")

    per_tier = {}          # game_tier -> [(raw, val), ...]
    taps     = {"free": 0, "royal": 0}
    logged   = set()

    # A claim can settle/reveal another, so loop passes until one claims nothing.
    for _pass in range(1, 5):
        claimed = 0
        for n in slots:
            tp = BTS_TIER_ITEM_TMPL.format(n=n)
            game_tier = (count - n + 1) if count else n   # top slot = highest tier
            rewards = _rewards(unity, tp)
            if n not in logged:
                logged.add(n)
                per_tier[game_tier] = rewards
                logging.info(
                    f"   🏷️ [BTS] Tier {game_tier} rewards: "
                    + (", ".join(f"{r}={v}" for r, v in rewards) or "(lootbox / none)")
                )
            has_value = bool(rewards)
            for section, kind in CLAIM_SECTIONS:
                btn = _claim_tier_button(unity, n, section)
                if not btn:
                    continue
                try:
                    safe_tap(unity, btn)
                except Exception:
                    continue
                taps[kind] += 1
                claimed += 1
                logging.info(f"   ✅ [BTS] Tier {game_tier} {kind} claim tapped")
                time.sleep(1.2)                       # reward animation
                if has_value:
                    _quick_dismiss(unity)             # fast — can't be a lootbox
                else:
                    _drain_bts_reward_screens(unity)  # value-less → may be a lootbox
        if claimed == 0:
            break

    # One final thorough mop-up (a mixed tier could still leave a lootbox up)
    _drain_bts_reward_screens(unity)

    logging.info(
        f"🎁 [BTS] Claim taps → free:{taps['free']} royal:{taps['royal']} "
        f"across {count} tiers"
    )
    return per_tier, taps


# -----------------------------------------------------------------------
# DB STATE  (authoritative confirmation of claims + purchase)
# -----------------------------------------------------------------------
def _bts_db_state(player_id):
    doc = get_user_from_db(player_id) or {}
    bts = doc.get("bmpToSpn", {}) or {}

    def _tier_keys(m):
        return sorted(int(k) for k in (m or {}).keys() if str(k).isdigit())

    return {
        "ammo":          bts.get("ammo"),
        "pnts":          bts.get("pnts"),
        "royal_active":  bool(bts.get("isRylPsActv")),
        "free_claimed":  _tier_keys(bts.get("frePsClms")),
        "royal_claimed": _tier_keys(bts.get("rylPsClms")),
    }


# -----------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------
def _print_summary(per_tier, db_state, cosmetic_before, cosmetic_after,
                   wallet_before, wallet_after):
    logging.info("=" * 64)
    logging.info("🎡 BUMP TO SPIN — FINAL SUMMARY")

    # Per-tier reward values (as read off the track)
    for idx in sorted(per_tier):
        rewards = per_tier[idx]
        rw = ", ".join(f"{r}={v}" for r, v in rewards) or "—"
        logging.info(f"   Tier {idx:>2}: rewards [{rw}]")

    # Free / paid tiers claimed (from DB — authoritative)
    logging.info(
        f"   🎟️ Free tiers claimed : {len(db_state['free_claimed'])} "
        f"→ {db_state['free_claimed']}"
    )
    logging.info(
        f"   👑 Royal tiers claimed: {len(db_state['royal_claimed'])} "
        f"→ {db_state['royal_claimed']}"
    )
    logging.info(
        f"   👑 Royal Pass active  : {db_state['royal_active']} | "
        f"points: {db_state['pnts']} | ammo left: {db_state['ammo']}"
    )

    # Cosmetic
    logging.info(f"   🎭 Cosmetic: {cosmetic_before or '—'} → {cosmetic_after or '—'}")

    # Wallet delta (UI / Data / DB)
    def _delta(a, b):
        try:
            return (b or 0) - (a or 0)
        except Exception:
            return "N/A"

    wb_db, wa_db     = wallet_before.get("db", {}),   wallet_after.get("db", {})
    wb_data, wa_data = wallet_before.get("data", {}), wallet_after.get("data", {})
    logging.info(
        f"   💰 Gold  Δ → UI:{_delta(wallet_before['gold_ui'], wallet_after['gold_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('gold'), wa_data.get('gold'))!s:>8}"
        f"  DB:{_delta(wb_db.get('gold'), wa_db.get('gold'))!s:>8}"
    )
    logging.info(
        f"   💎 Gems  Δ → UI:{_delta(wallet_before['gems_ui'], wallet_after['gems_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('gems'), wa_data.get('gems'))!s:>8}"
        f"  DB:{_delta(wb_db.get('gems'), wa_db.get('gems'))!s:>8}"
    )
    logging.info(
        f"   🔨 Hmmr  Δ → UI:{_delta(wallet_before['hammer_ui'], wallet_after['hammer_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('pips'), wa_data.get('pips'))!s:>8}"
        f"  DB:{_delta(wb_db.get('pips'), wa_db.get('pips'))!s:>8}"
    )
    logging.info("=" * 64)


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_bump_to_spin(unity_driver, driver=None):
    start_time = time.time()
    steps = []
    royal_ignored = False

    def add_step(msg, status="INFO"):
        steps.append({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "status": status, "step": msg})
        logging.info(msg)

    try:
        add_step("🎡 ── test_14_bumptospin START ──", "PASS")

        # ── 1. Lobby + clear popups ──────────────────────────────────
        home = _wait(unity_driver, HOME_BUTTON, 5)
        if home:
            safe_tap(unity_driver, home)
            time.sleep(1.5)
        clear_all_popups(unity_driver)

        # ── 2. Profile → cosmetic (before) + player_id ───────────────
        # get_user_snapshot opens the profile, logs the equipped cosmetic,
        # closes it and captures player_id — exactly the "open profile, log
        # cosmetic, close, read wallet" step.
        get_user_snapshot(unity_driver)
        player_id = state.user_info.get("player_id")
        if not player_id:
            raise Exception("❌ [BTS] Player ID missing")
        cosmetic_before = state.user_info.get("equipped_pawn")
        add_step(f"✅ Player ID: {player_id}", "PASS")
        add_step(f"🎭 [BTS] Equipped cosmetic (before): {cosmetic_before or '—'}", "PASS")

        # ── 3. Wallet (before) ───────────────────────────────────────
        wallet_before = _log_wallet(unity_driver, "before BTS", player_id)

        # ── 4. Open BTS + FTUE free ammo + total ammo ────────────────
        if not _open_bts(unity_driver):
            raise Exception("❌ [BTS] Could not open Bump To Spin")
        total_ammo_before = _num(unity_driver, BTS_TOTAL_AMMO, 4)
        add_step(f"🔫 [BTS] Total ammo in hand: {total_ammo_before}", "PASS")
        event_tracker.record("Bump To Spin", "Open", "PASS",
                             f"ammo {total_ammo_before}")

        # ── 5. KILL → boost ammo → LAUNCH → reopen ───────────────────
        device_id = _kill_game(unity_driver)
        set_bump_to_spin_ammo(player_id, BTS_AMMO_TOPUP)
        add_step(f"🎡 [BTS] Boosted ammo while game killed → "
                 f"bmpToSpn.ammo = {BTS_AMMO_TOPUP}", "PASS")
        time.sleep(2)
        unity_driver = _launch_and_reconnect(device_id)

        time.sleep(3)
        for _ in range(3):
            if not clear_all_popups(unity_driver):
                break
            time.sleep(1)
        add_step("✅ [BTS] Lobby cleared after relaunch", "PASS")

        if not _open_bts(unity_driver):
            raise Exception("❌ [BTS] Could not reopen BTS after relaunch")
        # Popups / info screens can surface ON the BTS modal after the relaunch
        # (they block the spin button) — close them before spinning.
        _clear_bts_overlays(unity_driver)
        total_ammo_boosted = _num(unity_driver, BTS_TOTAL_AMMO, 4)
        add_step(f"🔫 [BTS] Total ammo after boost: {total_ammo_boosted}", "PASS")

        # ── 6. Multiplier x10 ────────────────────────────────────────
        _set_multiplier_max(unity_driver)

        # ── 7. Autospin until all tiers unlock ───────────────────────
        unlocked = _autospin_until_unlocked(unity_driver, player_id)
        add_step(
            "🎯 [BTS] All tiers unlocked" if unlocked
            else "⚠️ [BTS] Autospin ended (unlock unconfirmed) — continuing",
            "PASS" if unlocked else "INFO",
        )
        event_tracker.record("Bump To Spin", "Autospin", "PASS" if unlocked else "FAIL",
                             "all tiers unlocked" if unlocked else "unlock unconfirmed")

        # ── 8. Buy the Royal Pass ────────────────────────────────────
        # Disable the Royal Pass close in the popup handler so it isn't
        # auto-dismissed during the purchase / claim; re-enabled before the
        # BTS screen is closed (guaranteed in `finally`).
        popup_handler.ignore_popup(BTS_ROYAL_CLOSE)
        royal_ignored = True
        add_step("🛡️ [BTS] Royal Pass close disabled in popup handler", "INFO")

        unity_driver, driver, _bought = _buy_royal_pass(unity_driver, driver)
        add_step("✅ [BTS] Royal Pass purchased", "PASS")
        event_tracker.record("Bump To Spin", "Royal Pass Purchase", "PASS", "bought")

        # A pawn-equip / reward screen can pop straight after the purchase
        _drain_bts_reward_screens(unity_driver)

        # ── 9. Claim every tier ──────────────────────────────────────
        per_tier, taps = _claim_all_tiers(unity_driver)
        _drain_bts_reward_screens(unity_driver)   # final mop-up

        # ── 10. Confirm via DB (authoritative) ───────────────────────
        db_state = _bts_db_state(player_id)
        purchase_ok = db_state["royal_active"] and len(db_state["royal_claimed"]) > 0
        if purchase_ok:
            add_step(
                f"✅ [BTS] Royal Pass active; paid tiers claimed: "
                f"{db_state['royal_claimed']}", "PASS",
            )
        else:
            add_step(
                f"❌ [BTS] Royal/paid rewards not claimable — Royal Pass purchase "
                f"FAILED (isRylPsActv={db_state['royal_active']}, "
                f"rylPsClms={db_state['royal_claimed']})", "FAIL",
            )
        add_step(
            f"🎟️ [BTS] Free tiers claimed: {len(db_state['free_claimed'])} | "
            f"Royal tiers claimed: {len(db_state['royal_claimed'])} | "
            f"claim taps free/royal: {taps['free']}/{taps['royal']}", "PASS",
        )
        event_tracker.record(
            "Bump To Spin", "Claim Tiers",
            "PASS" if purchase_ok else "FAIL",
            f"free {len(db_state['free_claimed'])}, royal {len(db_state['royal_claimed'])}",
        )

        # ── 11. Re-enable Royal Pass close, then close BTS → lobby ────
        popup_handler.unignore_popup(BTS_ROYAL_CLOSE)
        royal_ignored = False
        add_step("✅ [BTS] Royal Pass close re-enabled in popup handler", "INFO")

        close = _wait(unity_driver, BTS_CLOSE, 8)
        if close:
            safe_tap(unity_driver, close)
            time.sleep(2)
        home = _wait(unity_driver, HOME_BUTTON, 5)
        if home:
            safe_tap(unity_driver, home)
            time.sleep(1.5)
        clear_all_popups(unity_driver)

        # ── 12. Confirm the cosmetic is now equipped ─────────────────
        cosmetic_after = _read_equipped_cosmetic(unity_driver)
        equipped_changed = bool(cosmetic_after and cosmetic_after != cosmetic_before)
        add_step(
            f"🎭 [BTS] Equipped cosmetic (after): {cosmetic_after or '—'} "
            f"({'changed ✓' if equipped_changed else 'unchanged'})",
            "PASS" if cosmetic_after else "INFO",
        )

        # ── 13. Wallet (after) + summary ─────────────────────────────
        wallet_after = _log_wallet(unity_driver, "after BTS", player_id)
        _print_summary(per_tier, db_state, cosmetic_before, cosmetic_after,
                       wallet_before, wallet_after)

        status = "PASS" if purchase_ok else "FAIL"
        add_step(
            "✅ Bump To Spin Test Completed" if status == "PASS"
            else "⚠️ Bump To Spin completed with issues (see above)",
            status,
        )
        return {
            "name": "Bump To Spin",
            "status": status,
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }

    except Exception as e:
        logging.exception("❌ Bump To Spin Test Failed")
        add_step(f"❌ Test failed: {str(e)}", "FAIL")
        return {
            "name": "Bump To Spin",
            "status": "FAIL",
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }

    finally:
        # Guarantee the Royal Pass close handler is re-enabled even on failure.
        if royal_ignored:
            try:
                popup_handler.unignore_popup(BTS_ROYAL_CLOSE)
            except Exception:
                pass
