"""
test_13_treasureisland.py
─────────────────────────
Treasure Island (Fortune Island) full-play test.

Flow
────
 1. Home + clear popups. Log lobby wallet (UI / Data / DB).
 2. Open Treasure Island; log the LEVEL PROGRESS.
      • Level 1  → FTUE not completed.
      • Level 2+ → FTUE already cleared.
 3. Run the happy-flow Treasure Island FTUE (imported) if FTUE isn't done.
 4. Close TI → boost event ammo in Mongo (frtnIslndDt.data.ammCnt = 900).
 5. RELAUNCH the game, reconnect AltTester, clear lobby popups, reopen TI.
 6. Confirm + log level progress (expected 2+). Then, per level:
      • Log total ammo, level rewards (gold/gem), kitty-bag contents.
      • Open chests until the Doubloon Key is found:
          - reward (gold/gem/ammo → kitty bag)  → log kitty bag
          - bomb  → revive (costs gems)          → track cost
          - doubloon key                          → next level
      • Track per level: chests opened, bombs, revive costs, which chest gave
        the doubloon, ammo used (= chests opened).
 7. Tap the Event Complete screen to claim.
 8. Close → lobby. Log wallet (after) + delta. Print full summary.

Notes
─────
• The happy-flow FTUE flow is imported (`_do_treasure_island`) and run first.
• There is a game RELAUNCH after the ammo boost — the reconnected unity_driver
  is returned so the runner keeps using the live one.
• Chest slots are random (up to 40 slots, chest variant 1/2/3 each). We can't
  predict counts, so we open whatever chests are available until the doubloon
  appears, with safety caps to avoid infinite loops.
"""

import re
import time
import logging
import subprocess

from alttester import By

from utils.state_manager import state
from utils.popup_handler import (
    wait_for_safe, safe_tap, clear_all_popups, close_info_screen,
)
from utils.helpers import (
    fast_text, safe_text, parse_amount, get_wallet_from_data, get_user_snapshot,
    get_rewards_from_data,
)
from utils.mongo_helper import get_user_wallet, set_treasure_island_ammo
from utils.driver_manager import connect_altunity
import utils.event_tracker as event_tracker
from config import ADB_PATH, PACKAGE_NAME, ACTIVITY_NAME, ALTTESTER_PORT, APP_NAME
from tests.test_02_happy_flow import _do_treasure_island
from utils.paths import (
    HOME_BUTTON, HOME_GOLD_TEXT, HOME_GEMS_TEXT,
    TI_ICON, TI_CLOSE, TI_MAIN_MODAL, TI_TOTAL_AMMO, TI_LEVEL_PROGRESS,
    TI_CHEST_SLOTS, TI_DOUBLOON_KEY,
    TI_LEVEL_REWARDS_CONTAINER, TI_KITTY_CONTAINER, TI_KITTY_TAP,
    TI_EVENT_COMPLETE_CONTAINER,
    TI_CHECKPOINT_FTUE, TI_BOMB_FTUE, TI_BOMB_MODAL,
    TI_REVIVE_COST, TI_REVIVE_BUTTON, TI_COMPLETE_SCREEN,
)

# -----------------------------------------------------------------------
# TUNABLES
# -----------------------------------------------------------------------
TI_AMMO_TOPUP        = 900   # frtnIslndDt.data.ammCnt set before relaunch
MAX_LEVELS           = 25    # safety cap on the level loop
MAX_CHESTS_PER_LEVEL = 60    # safety cap on chest opens per level
LEVEL_TRANSITION_SEC = 3     # transition after tapping the doubloon key


# -----------------------------------------------------------------------
# LOW-LEVEL HELPERS  (direct wait_for_object — safe inside TI modals)
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


def _read_level(unity):
    """Return (level_int, raw_text) from the TI header level panel."""
    raw = _text(unity, TI_LEVEL_PROGRESS, 3) or ""
    m = re.findall(r"\d+", raw)
    return (int(m[0]) if m else 0, raw.strip())


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
    logging. Index-independent (grabs all `amountText` value nodes rather than
    an exact `.../SpriteRewardItem_9/...` path). parse_amount handles plain
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
    """Reward (label, amount) pairs for a reward container currently showing.

    Prefers reading the game's reward components directly via
    get_rewards_from_data() — returns the reward TYPE name + raw amount, e.g.
    ("Gold", 1500) or ("FortuneIslandAmmo", 3) — scoped to `container_path`.
    Falls back to scanning the UI amountText under `container_path` when that
    returns nothing, so it can only improve the reads, never regress them."""
    try:
        data = get_rewards_from_data(unity, container=container_path)
    except Exception:
        data = []
    if data:
        return [(r["type"], r["amount"]) for r in data]
    return _scan_amounts(unity, container_path)


def _pull_rewards(unity, container_path, label):
    """Scan a persistent reward container and log its amounts."""
    out = _rewards(unity, container_path)
    if out:
        logging.info(f"   🎁 [TI] {label}: " + ", ".join(f"{r}={v}" for r, v in out))
    else:
        logging.info(f"   🎁 [TI] {label}: (none on screen)")
    return out


def _pull_kitty(unity, attempts=3):
    """Read kitty-bag rewards.

    The kitty rewards are only rendered inside a tooltip that appears when the
    bag is TAPPED and auto-hides after ~1-2s — a passive scan always sees it
    empty. So we tap the bag and read the tooltip immediately, retrying a few
    times (waiting for it to auto-hide between taps so the re-tap re-opens it
    rather than toggling it shut)."""
    for attempt in range(1, attempts + 1):
        tap = _wait(unity, TI_KITTY_TAP, 2)
        if tap:
            try:
                safe_tap(unity, tap)
            except Exception:
                pass
        out = _rewards(unity, TI_KITTY_CONTAINER)   # read within the tooltip window
        if out:
            logging.info("   🎒 [TI] Kitty bag: " + ", ".join(f"{r}={v}" for r, v in out))
            return out
        time.sleep(1.5)   # let the tooltip auto-hide before re-tapping
    logging.info("   🎒 [TI] Kitty bag: (empty — rewards granted at checkpoint)")
    return []


def _revive_cost(unity):
    """Extract the numeric gem cost from e.g. 'REVIVE FOR <sprite=6>0'."""
    raw = _text(unity, TI_REVIVE_COST, 3) or ""
    clean = re.sub(r"<[^>]*>", "", raw)        # drop the <sprite=…> tag
    nums = re.findall(r"\d+", clean)
    return int(nums[-1]) if nums else 0


# -----------------------------------------------------------------------
# CHEST DISCOVERY
# -----------------------------------------------------------------------
def _find_chests(unity):
    """Best-effort list of available chest objects.

    Primary: find_objects on a descendant wildcard for each chest variant.
    Fallback: probe slot indices directly (slower).
    """
    found = []
    for v in (1, 2, 3):
        try:
            objs = unity.find_objects(By.PATH, f"{TI_CHEST_SLOTS}//Chest_{v}")
            if objs:
                found.extend(objs)
        except Exception:
            pass
    if found:
        return found

    # Fallback — probe each slot for any of the 3 chest variants
    for slot in range(0, 41):
        for v in (1, 2, 3):
            try:
                o = unity.find_object(
                    By.PATH, f"{TI_CHEST_SLOTS}/{slot}/Chest{v}(Clone)/Chest_{v}"
                )
                if o:
                    found.append(o)
                    break   # one chest per slot
            except Exception:
                pass
    return found


# -----------------------------------------------------------------------
# WALLET LOGGING (UI / Data / DB)
# -----------------------------------------------------------------------
def _log_wallet(unity, phase, player_id):
    gold_ui = parse_amount(fast_text(unity, HOME_GOLD_TEXT))
    gems_ui = parse_amount(fast_text(unity, HOME_GEMS_TEXT))
    data = get_wallet_from_data(unity)
    db = get_user_wallet(player_id) if player_id else {}

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 [TI] Wallet ({phase})")
    logging.info(f"   🟡 Gold → UI:{gold_ui:<10} Data:{str(data.get('gold')):<10} DB:{db.get('gold')}")
    logging.info(f"   💎 Gems → UI:{gems_ui:<10} Data:{str(data.get('gems')):<10} DB:{db.get('gems')}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return {"gold_ui": gold_ui, "gems_ui": gems_ui, "data": data, "db": db}


# -----------------------------------------------------------------------
# OPEN / CLOSE
# -----------------------------------------------------------------------
def _open_ti(unity):
    """Tap the lobby icon and confirm the TI main modal opened."""
    icon = wait_for_safe(unity, By.PATH, TI_ICON, 15)
    if not icon:
        return False
    safe_tap(unity, icon)
    time.sleep(4)               # opening animation + screen load
    clear_all_popups(unity)     # any lobby popup that rode in
    return _present(unity, TI_MAIN_MODAL, 8) or _present(unity, TI_LEVEL_PROGRESS, 5)


def _close_ti(unity):
    close = _wait(unity, TI_CLOSE, 8)
    if close:
        safe_tap(unity, close)
        time.sleep(2)


# -----------------------------------------------------------------------
# KILL → BOOST → LAUNCH
#
# The ammo boost MUST happen while the game is dead. If we boost while the
# game is still running, on force-stop the app syncs its in-memory event
# state (ammCnt=0) back to the server and clobbers the boost. So: force-stop
# first, THEN write the boost, THEN cold-launch — the game then loads the
# boosted value fresh.
# -----------------------------------------------------------------------
def _kill_game(unity_driver):
    """Close the AltTester driver and force-stop the game. Returns device_id."""
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
        logging.info("🛑 [TI] Game force-stopped")
        time.sleep(3)   # let the process fully die before we write the boost
    else:
        logging.warning("⚠️ [TI] device_id missing in state — cannot force-stop via ADB")
    return device_id


def _launch_and_reconnect(device_id):
    """Cold-launch the game and reconnect AltTester with the patient connector
    (a cold start needs time to re-register). Returns the NEW unity_driver."""
    if device_id:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "am", "start",
             "-n", f"{PACKAGE_NAME}/{ACTIVITY_NAME}"],
            check=False,
        )
    logging.info("🎮 [TI] Game launched — waiting for AltTester to register...")
    time.sleep(10)
    new_driver = connect_altunity(alt_port=ALTTESTER_PORT, app_name=APP_NAME)
    state.set("unity_driver", new_driver)
    logging.info("✅ [TI] AltTester reconnected after launch")
    return new_driver


# -----------------------------------------------------------------------
# CHEST OUTCOME
# -----------------------------------------------------------------------
def _handle_chest_outcome(unity, stats):
    """After a chest is tapped, resolve the outcome.

    Returns one of:
      • "doubloon" — level-complete key found (caller taps it → next level)
      • "bomb"     — bomb hit, revived (cost tracked)
      • "reward"   — gold/gem/ammo/nothing (added to kitty bag)
    """
    time.sleep(1.5)   # let the outcome animate in

    # First-time bomb tutorial overlay → tap to continue, bomb modal follows
    if _present(unity, TI_BOMB_FTUE, 1):
        logging.info("   💥 [TI] Bomb FTUE overlay — tapping to continue")
        close_info_screen(unity)
        time.sleep(1.5)

    # Bomb-hit modal → log revive cost, revive
    if _present(unity, TI_BOMB_MODAL, 1):
        cost = _revive_cost(unity)
        stats["bombs"] += 1
        stats["revive_costs"].append(cost)
        logging.info(f"   💣 [TI] BOMB hit! Revive cost: {cost} gems — reviving")
        btn = _wait(unity, TI_REVIVE_BUTTON, 5)
        if btn:
            safe_tap(unity, btn)
            time.sleep(2)
        else:
            logging.warning("   ⚠️ [TI] Revive button not found")
        return "bomb"

    # Doubloon key (level complete)
    if _present(unity, TI_DOUBLOON_KEY, 1):
        return "doubloon"

    return "reward"


# -----------------------------------------------------------------------
# PLAY ONE LEVEL
# -----------------------------------------------------------------------
def _play_level(unity, level_index):
    """Open chests until the doubloon key appears. Returns a stats dict."""
    # Dismiss checkpoint FTUE (appears entering a new level, e.g. 2→3)
    if _present(unity, TI_CHECKPOINT_FTUE, 1):
        logging.info("   🚩 [TI] Checkpoint FTUE — tapping to close")
        close_info_screen(unity)
        time.sleep(1.5)

    level_num, level_raw = _read_level(unity)
    ammo = _num(unity, TI_TOTAL_AMMO, 3)

    logging.info("─" * 55)
    logging.info(f"🏝️ [TI] LEVEL {level_raw or level_num} — start")
    logging.info(f"   🔫 Total ammo available : {ammo}")
    # Reward amounts via subtree scan (index-independent, handles 1.3k / 2.05M)
    level_reward = _pull_rewards(unity, TI_LEVEL_REWARDS_CONTAINER, "Level reward")
    _pull_kitty(unity)   # tap-to-reveal tooltip (auto-hides), so tap + quick read

    stats = {
        "level": level_num, "level_raw": level_raw,
        "ammo_start": ammo,
        "chests": 0, "bombs": 0, "revive_costs": [],
        "doubloon_chest": None, "rewards": [],
        "level_reward": level_reward,
        "completed": False,
    }

    for _ in range(MAX_CHESTS_PER_LEVEL):
        # Event may finish exactly on a doubloon-less state
        if _present(unity, TI_COMPLETE_SCREEN, 0.5):
            logging.info("   🏁 [TI] Event complete screen detected mid-level")
            break

        chests = _find_chests(unity)
        if not chests:
            logging.warning("   ⚠️ [TI] No openable chests found — stopping this level")
            break

        chest = chests[0]
        name = getattr(chest, "name", "?")
        try:
            chest.tap()
        except Exception:
            safe_tap(unity, chest)
        stats["chests"] += 1
        logging.info(f"   📦 [TI] Opened chest #{stats['chests']} ({name})")

        outcome = _handle_chest_outcome(unity, stats)
        stats["rewards"].append({"chest": stats["chests"], "outcome": outcome})

        if outcome == "doubloon":
            stats["doubloon_chest"] = stats["chests"]
            logging.info(f"   🔑 [TI] Doubloon Key found on chest #{stats['chests']} → next level")
            dk = _wait(unity, TI_DOUBLOON_KEY, 5)
            if dk:
                safe_tap(unity, dk)
                time.sleep(LEVEL_TRANSITION_SEC)   # transition to next level
            stats["completed"] = True
            break

    stats["ammo_used"] = stats["chests"]   # 1 chest open == 1 ammo

    logging.info(
        f"   📊 [TI] Level {stats['level_raw'] or stats['level']} summary → "
        f"chests:{stats['chests']} bombs:{stats['bombs']} "
        f"revives:{stats['revive_costs']} doubloon@chest:{stats['doubloon_chest']} "
        f"ammo used:{stats['ammo_used']}"
    )
    logging.info("─" * 55)
    event_tracker.record(
        "Treasure Island", f"Level {stats['level_raw'] or level_index}",
        "PASS" if stats["completed"] else "FAIL",
        f"chests {stats['chests']}, bombs {stats['bombs']}, "
        f"doubloon@{stats['doubloon_chest']}, ammo {stats['ammo_used']}",
    )
    return stats


# -----------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------
def _print_summary(levels, wallet_before, wallet_after):
    logging.info("=" * 62)
    logging.info("🏝️ TREASURE ISLAND — FINAL SUMMARY")
    total_chests = sum(l["chests"] for l in levels)
    total_bombs = sum(l["bombs"] for l in levels)
    for l in levels:
        rw = ", ".join(f"{r}={v}" for r, v in l.get("level_reward", [])) or "—"
        logging.info(
            f"   Level {l['level_raw'] or l['level']}: reward [{rw}] | "
            f"chests {l['chests']} | bombs {l['bombs']} | revive costs {l['revive_costs']} | "
            f"doubloon on chest #{l['doubloon_chest']} | ammo used {l['ammo_used']}"
        )
    logging.info(f"   TOTAL → levels:{len(levels)} chests:{total_chests} bombs:{total_bombs}")

    gb, ga = wallet_before.get("db", {}), wallet_after.get("db", {})
    if gb and ga:
        dg = (ga.get("gold", 0) or 0) - (gb.get("gold", 0) or 0)
        dm = (ga.get("gems", 0) or 0) - (gb.get("gems", 0) or 0)
        logging.info(f"   💰 Wallet delta (DB) → gold: {dg:+}  gems: {dm:+}")
    logging.info("=" * 62)


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_treasure_island(unity_driver, driver=None):
    start_time = time.time()
    steps = []

    def add_step(msg, status="INFO"):
        steps.append({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "status": status, "step": msg})
        logging.info(msg)

    try:
        add_step("🏝️ ── test_13_treasureisland START ──", "PASS")

        # ── 1. Home + clear popups ───────────────────────────────────
        home = _wait(unity_driver, HOME_BUTTON, 5)
        if home:
            safe_tap(unity_driver, home)
            time.sleep(1.5)
        clear_all_popups(unity_driver)

        # ── Player id ────────────────────────────────────────────────
        player_id = state.user_info.get("player_id")
        if not player_id:
            get_user_snapshot(unity_driver)
            player_id = state.user_info.get("player_id")
        if not player_id:
            raise Exception("❌ [TI] Player ID missing")
        add_step(f"✅ Player ID: {player_id}", "PASS")

        # ── 2. Wallet (before) ───────────────────────────────────────
        wallet_before = _log_wallet(unity_driver, "before Treasure Island", player_id)

        # ── 3. Open TI + level progress ──────────────────────────────
        if not _open_ti(unity_driver):
            raise Exception("❌ [TI] Could not open Treasure Island")
        level_num, level_raw = _read_level(unity_driver)
        ftue_done = level_num >= 2
        add_step(
            f"📖 [TI] Level progress: {level_raw or level_num} → "
            f"FTUE {'already cleared' if ftue_done else 'NOT completed'}",
            "PASS",
        )
        _close_ti(unity_driver)
        clear_all_popups(unity_driver)

        # ── 3b. FTUE flow (imported from happy flow) ─────────────────
        if not ftue_done:
            add_step("🎬 [TI] Running happy-flow Treasure Island FTUE...", "PASS")
            _do_treasure_island(unity_driver)   # opens, runs FTUE, closes
            clear_all_popups(unity_driver)
        else:
            add_step("⏭️ [TI] FTUE already done — skipping FTUE flow", "PASS")

        # ── 4. KILL game → boost ammo → LAUNCH game ──────────────────
        # Order matters: the game must be dead when we write the boost, else
        # it syncs its in-memory ammCnt=0 back over it on shutdown.
        device_id = _kill_game(unity_driver)
        set_treasure_island_ammo(player_id, TI_AMMO_TOPUP)
        add_step(
            f"🏝️ [TI] Boosted ammo while game killed → "
            f"frtnIslndDt.data.ammCnt = {TI_AMMO_TOPUP}", "PASS",
        )
        time.sleep(2)
        unity_driver = _launch_and_reconnect(device_id)

        # ── 5. Clear lobby ───────────────────────────────────────────
        time.sleep(3)
        clear_all_popups(unity_driver)
        # Two clean passes so the lobby is truly clear before reopening TI
        for _ in range(3):
            if not clear_all_popups(unity_driver):
                break
            time.sleep(1)
        add_step("✅ [TI] Lobby cleared after relaunch", "PASS")

        # ── 6. Reopen TI + confirm level ─────────────────────────────
        if not _open_ti(unity_driver):
            raise Exception("❌ [TI] Could not reopen Treasure Island after relaunch")
        level_num, level_raw = _read_level(unity_driver)
        add_step(f"📖 [TI] Level after relaunch: {level_raw or level_num}", "PASS")
        if level_num < 2:
            logging.warning("⚠️ [TI] Level still 1 after FTUE+relaunch — proceeding anyway")

        # ── 7. Play levels until the event completes ─────────────────
        levels = []
        for lvl in range(1, MAX_LEVELS + 1):
            if _present(unity_driver, TI_COMPLETE_SCREEN, 1):
                break
            stats = _play_level(unity_driver, lvl)
            levels.append(stats)
            time.sleep(LEVEL_TRANSITION_SEC)
            if _present(unity_driver, TI_COMPLETE_SCREEN, 2):
                break
            if not stats["completed"]:
                logging.warning("⚠️ [TI] Level not completed (no doubloon) — stopping loop")
                break

        # ── 8. Event complete → claim ────────────────────────────────
        if _present(unity_driver, TI_COMPLETE_SCREEN, 5):
            ec_rewards = _pull_rewards(
                unity_driver, TI_EVENT_COMPLETE_CONTAINER, "Event Complete rewards"
            )
            tap = _wait(unity_driver, TI_COMPLETE_SCREEN, 5)
            if tap:
                safe_tap(unity_driver, tap)
                time.sleep(2)
            rw = ", ".join(f"{r}={v}" for r, v in ec_rewards) or "—"
            add_step(f"🎉 [TI] Event Complete — rewards [{rw}] claimed", "PASS")
            event_tracker.record("Treasure Island", "Event Complete", "PASS",
                                 f"{len(levels)} levels, rewards [{rw}]")
        else:
            add_step("⚠️ [TI] Event complete screen not reached", "INFO")

        # ── 9. Close → lobby → wallet after ──────────────────────────
        _close_ti(unity_driver)
        home = _wait(unity_driver, HOME_BUTTON, 5)
        if home:
            safe_tap(unity_driver, home)
            time.sleep(1.5)
        clear_all_popups(unity_driver)

        wallet_after = _log_wallet(unity_driver, "after Treasure Island", player_id)
        _print_summary(levels, wallet_before, wallet_after)

        add_step("✅ Treasure Island Test Completed", "PASS")
        return {
            "name": "Treasure Island",
            "status": "PASS",
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }

    except Exception as e:
        logging.exception("❌ Treasure Island Test Failed")
        add_step(f"❌ Test failed: {str(e)}", "FAIL")
        return {
            "name": "Treasure Island",
            "status": "FAIL",
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }
