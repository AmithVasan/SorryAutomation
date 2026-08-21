"""
test_15_puzzletheatre.py
────────────────────────
Puzzle Theatre (PT) full-play test.

Flow
────
 1. Lobby + clear popups.  get_user_snapshot → player_id.  Log wallet (UI / Data / DB).
 2. Open PT from the lobby icon.  Handle the Free-Ammo popup: log the free ammo,
    claim it.
 3. FTUE: reveal the FTUE piece, then open All Puzzles.  Fetch the Grand Reward
    panel values.  Log the total ammo in hand.
 4. Close PT → lobby → boost ammo in Mongo (puzzleEventData.ammoBalance) → reopen
    PT → confirm the total ammo reflects the boost (UI vs DB).
 5. Solve every puzzle board (count is adaptive — 6 today, may change):
      • enter the board (PuzzleFrame),
      • reveal every piece (count varies 4/6/8… per board — adaptive), logging the
        ammo DELTA per piece = that piece's ammo cost,
      • on board-complete, fetch + collect the reward screen,
      • move to the next board.
 6. After the last board → Event-Complete reward screen (fetch + collect) →
    Grand Reward screen (collect = event complete) → close → lobby.
 7. Summary: before/after wallet (UI / Data / DB), per-board reward + ammo cost,
    total reward, and grand reward.

Design notes
────────────
• Board count and pieces-per-board are discovered at runtime (find_objects +
  existence checks), so the test keeps working if boards/pieces are added.
• Per-piece cost is the drop in the PT total-ammo counter across a reveal.
• The boost follows the requested flow (close → boost DB → reopen, no relaunch);
  the total ammo is verified against the DB after reopen so it's obvious whether
  the boost was picked up.
"""

import time
import logging
import subprocess

from alttester import By

from utils.state_manager import state
from utils.popup_handler import (
    wait_for_safe, safe_tap, clear_all_popups, handle_one_popup, close_info_screen,
)
from utils.helpers import (
    fast_text, safe_text, parse_amount, get_wallet_from_data, get_user_snapshot,
    get_rewards_from_data,
)
from utils.mongo_helper import (
    get_user_wallet, get_user_from_db, set_puzzle_theatre_ammo, get_puzzle_theatre_ammo,
)
import utils.event_tracker as event_tracker
from config import ADB_PATH
from utils.paths import (
    HOME_BUTTON, HOME_GOLD_TEXT, HOME_GEMS_TEXT, HOME_HAMMER_TEXT,
    PT_ICON, PT_FREE_AMMO_MODAL, PT_FREE_AMMO_CONTAINER, PT_FREE_AMMO_COUNT,
    PT_AMMO_CLAIM, PT_FTUE_PIECE, PT_ALL_PUZZLES_ICON, PT_GRAND_REWARD_PANEL,
    PT_TOTAL_AMMO, PT_EVENT_CLOSE, PT_MODAL, PT_PUZZLE_FRAME, PT_ALL_PUZZLE_LAYOUT,
    PT_BOARD_TMPL, PT_PIECE_BTNS, PT_REWARD_SCREEN, PT_REWARD_ROOT, PT_REWARD_COLLECT,
    PT_GRAND_REWARD_SCREEN, PT_GRAND_REWARD_COLLECT,
)

# -----------------------------------------------------------------------
# TUNABLES
# -----------------------------------------------------------------------
PT_AMMO_TOPUP        = 5000   # puzzleEventData.ammoBalance set before reopen
MAX_BOARDS           = 30     # safety cap on the board loop (6 today; headroom)
MAX_PIECES_PER_BOARD = 30     # safety cap on the piece loop (8 today; headroom)
REVEAL_SETTLE        = 1.5    # secs to let a piece reveal + ammo counter update


# -----------------------------------------------------------------------
# LOW-LEVEL HELPERS  (direct wait_for_object — safe inside the PT modal)
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
    try:
        t = obj.get_text()
        if t is not None and str(t).strip() not in ("", "N/A"):
            return str(t).strip()
    except Exception:
        pass
    return safe_text(obj)


def _scan_amounts(unity, container_path):
    """Every reward AMOUNT under a container as (raw_text, number).  Index-free —
    grabs all `amountText` value nodes rather than an exact SpriteRewardItem_N
    path — so it works regardless of which items a screen shows."""
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
    """Reward (label, amount) pairs for the reward screen currently showing.

    Prefers reading the game's reward components directly via
    get_rewards_from_data() — accurate + formatting-independent, returns the
    reward TYPE name + raw amount, e.g. ("PuzzleEventAmmo", 10). Falls back to
    scanning the UI amountText under `container_path` when that returns nothing
    (e.g. a build without the GetRewardAmount/GetRewardTypeId getters), so this
    can only improve the reads, never regress them."""
    try:
        data = get_rewards_from_data(unity, container=container_path)
    except Exception:
        data = []
    if data:
        return [(r["type"], r["amount"]) for r in data]
    return _scan_amounts(unity, container_path)


def _tap_screen_center(unity=None):
    """Raw ADB 'tap anywhere' — some reward screens don't register a tap on the
    CTA element and need a raw screen tap to dismiss."""
    device_id = state.get("device_id")
    if not device_id:
        return
    try:
        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", "540", "1200"],
                       check=False)
    except Exception:
        pass


# -----------------------------------------------------------------------
# WALLET LOGGING (UI / Data / DB)
# -----------------------------------------------------------------------
def _log_wallet(unity, phase, player_id):
    gold_ui   = parse_amount(fast_text(unity, HOME_GOLD_TEXT))
    gems_ui   = parse_amount(fast_text(unity, HOME_GEMS_TEXT))
    hammer_ui = parse_amount(fast_text(unity, HOME_HAMMER_TEXT))
    data = get_wallet_from_data(unity)
    db   = get_user_wallet(player_id) if player_id else {}

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"💰 [PT] Wallet ({phase})")
    logging.info(f"   🟡 Gold   → UI:{gold_ui:<10} Data:{str(data.get('gold')):<10} DB:{db.get('gold')}")
    logging.info(f"   💎 Gems   → UI:{gems_ui:<10} Data:{str(data.get('gems')):<10} DB:{db.get('gems')}")
    logging.info(f"   🔨 Hammer → UI:{hammer_ui:<10} Data:{str(data.get('pips')):<10} DB:{db.get('pips')}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return {"gold_ui": gold_ui, "gems_ui": gems_ui, "hammer_ui": hammer_ui,
            "data": data, "db": db}


# -----------------------------------------------------------------------
# OPEN PT + FREE-AMMO CLAIM
# -----------------------------------------------------------------------
def _handle_free_ammo(unity):
    """Free-ammo popup on open — log the amount, claim it."""
    if _present(unity, PT_FREE_AMMO_MODAL, 5):
        amounts = _rewards(unity, PT_FREE_AMMO_CONTAINER)
        raw = (", ".join(f"{r}={v}" for r, v in amounts)
               or (fast_text(unity, PT_FREE_AMMO_COUNT) or "—"))
        logging.info(f"🎁 [PT] Free ammo: {raw}")
        claim = wait_for_safe(unity, By.PATH, PT_AMMO_CLAIM, 8)
        if claim:
            safe_tap(unity, claim)
            time.sleep(1.5)
            logging.info("✅ [PT] Free ammo claimed")
        return True
    logging.info("ℹ️ [PT] No free-ammo popup (already claimed)")
    return False


def _open_pt(unity):
    """Tap the lobby icon, handle the free-ammo popup, confirm the event opened."""
    icon = wait_for_safe(unity, By.PATH, PT_ICON, 15)
    if not icon:
        return False
    safe_tap(unity, icon)
    time.sleep(4)
    _handle_free_ammo(unity)
    clear_all_popups(unity)
    return (_present(unity, PT_MODAL, 8)
            or _present(unity, PT_TOTAL_AMMO, 4)
            or _present(unity, PT_ALL_PUZZLE_LAYOUT, 4))


def _handle_ftue(unity):
    """First open only: reveal the FTUE piece, then open All Puzzles.  Best-effort
    (these don't appear after the event has been opened once)."""
    piece = wait_for_safe(unity, By.PATH, PT_FTUE_PIECE, 4)
    if piece:
        safe_tap(unity, piece)
        logging.info("🧩 [PT] FTUE piece revealed")
        time.sleep(2)
    allp = wait_for_safe(unity, By.PATH, PT_ALL_PUZZLES_ICON, 4)
    if allp:
        safe_tap(unity, allp)
        logging.info("🗂️ [PT] Opened All Puzzles")
        time.sleep(2)


# -----------------------------------------------------------------------
# NAVIGATION
# -----------------------------------------------------------------------
def _to_lobby(unity):
    home = _wait(unity, HOME_BUTTON, 5)
    if home:
        safe_tap(unity, home)
        time.sleep(1.5)
    clear_all_popups(unity)


def _close_event(unity):
    close = _wait(unity, PT_EVENT_CLOSE, 6)
    if close:
        safe_tap(unity, close)
        time.sleep(2)
    _to_lobby(unity)


def _board_indices(unity):
    """Discover which PuzzleNumber_N boards exist (adaptive).  Stops after two
    consecutive gaps so a non-contiguous layout still terminates."""
    found, misses = [], 0
    for n in range(1, MAX_BOARDS + 1):
        if _wait(unity, PT_BOARD_TMPL.format(n=n), 0.4):
            found.append(n)
            misses = 0
        else:
            misses += 1
            if found and misses >= 2:
                break
    return found


# -----------------------------------------------------------------------
# REWARD SCREEN (board-complete AND event-complete share RewardSummaryModal)
# -----------------------------------------------------------------------
def _collect_reward_screen(unity, label, timeout=12):
    """Wait for the RewardSummaryModal, fetch its reward values, tap Collect.
    Returns the list of (raw, value) rewards (empty if the screen never showed)."""
    if not _present(unity, PT_REWARD_SCREEN, timeout):
        logging.info(f"ℹ️ [PT] No reward screen for {label}")
        return []
    time.sleep(2)   # ~2s reward animation
    rewards = _rewards(unity, PT_REWARD_ROOT)
    logging.info(f"🏆 [PT] {label} rewards: "
                 + (", ".join(f"{r}={v}" for r, v in rewards) or "(none read)"))
    cta = wait_for_safe(unity, By.PATH, PT_REWARD_COLLECT, 8)
    if cta:
        safe_tap(unity, cta)
        time.sleep(1.5)
    else:
        _tap_screen_center(unity)
        time.sleep(1.5)
    # a reward screen can chain into another (rare) — clear a lingering one
    if _present(unity, PT_REWARD_SCREEN, 1):
        cta2 = wait_for_safe(unity, By.PATH, PT_REWARD_COLLECT, 4)
        if cta2:
            safe_tap(unity, cta2)
            time.sleep(1.2)
    logging.info(f"✅ [PT] {label} reward collected")
    return rewards


# -----------------------------------------------------------------------
# BOARD SOLVING — reveal every piece, log per-piece ammo cost
# -----------------------------------------------------------------------
def _reveal_board_pieces(unity, board_n):
    """Reveal all pieces in the current board; return [ammo_cost_per_piece].

    Pieces + their reveal cost vary per board, so we re-query the un-revealed
    piece buttons each iteration and stop when none remain or the board-complete
    reward screen appears.  A stall guard (ammo not dropping AND button count not
    shrinking) prevents an infinite loop."""
    costs = []
    ammo_prev = _num(unity, PT_TOTAL_AMMO, 3)
    prev_btn_count = None
    stalls = 0

    for _ in range(MAX_PIECES_PER_BOARD):
        if _present(unity, PT_REWARD_SCREEN, 0.4):
            break   # board complete
        try:
            btns = unity.find_objects(By.PATH, PT_PIECE_BTNS)
        except Exception:
            btns = []
        if not btns:
            break

        # Stall detection: same #buttons AND ammo unchanged for 2 rounds → bail.
        if prev_btn_count is not None and len(btns) >= prev_btn_count and stalls >= 2:
            logging.warning(f"⚠️ [PT] Board {board_n}: piece reveal stalled "
                            f"({len(btns)} left) — stopping")
            break
        prev_btn_count = len(btns)

        try:
            safe_tap(unity, btns[0])
        except Exception:
            _tap_screen_center(unity)
        time.sleep(REVEAL_SETTLE)

        ammo_now = _num(unity, PT_TOTAL_AMMO, 2)
        if ammo_prev is not None and ammo_now is not None and ammo_now < ammo_prev:
            cost = ammo_prev - ammo_now
            costs.append(cost)
            logging.info(f"   🧩 [PT] Board {board_n} piece {len(costs)} revealed → "
                         f"ammo {ammo_prev}→{ammo_now} (cost {cost})")
            ammo_prev = ammo_now
            stalls = 0
        else:
            stalls += 1
            logging.info(f"   🧩 [PT] Board {board_n} tap (no ammo change; "
                         f"ammo {ammo_now}) — stall {stalls}")

    logging.info(f"🧩 [PT] Board {board_n}: {len(costs)} pieces revealed, "
                 f"total ammo cost {sum(costs) if costs else 0}")
    return costs


def _enter_board(unity, board_n):
    """Open puzzle board `board_n` from the All-Puzzles grid.

    The event reuses ONE PuzzleFrame for every board, and its piece buttons stay
    in the hierarchy after a board completes — so a *present* PuzzleFrame is NOT
    proof the right board is open.  (Trusting it caused boards after #1 to be
    skipped: the lingering board-1 frame satisfied the check, board 2 was never
    tapped, and the reveal loop then re-scanned board 1's already-revealed
    pieces.)  So we ALWAYS wait for this board's own PuzzleNumber_{n} tile on the
    grid and tap it, then confirm the frame (re)opened."""
    tile = None
    end = time.time() + 15   # allow the grid to reappear after the prev reward
    while time.time() < end:
        tile = _wait(unity, PT_BOARD_TMPL.format(n=board_n), 1)
        if tile:
            break
        time.sleep(1)
    if not tile:
        logging.warning(f"⚠️ [PT] Board {board_n} tile not found on the All-Puzzles grid")
        return False
    safe_tap(unity, tile)
    time.sleep(2.5)   # board open animation
    return _present(unity, PT_PUZZLE_FRAME, 8)


# -----------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------
def _print_summary(wallet_before, wallet_after, board_rewards, board_costs,
                   event_reward, grand_reward, total_ammo_before, total_ammo_boosted):
    logging.info("=" * 64)
    logging.info("🎭 PUZZLE THEATRE — FINAL SUMMARY")
    logging.info(f"   🔫 Total ammo: before {total_ammo_before} → after boost {total_ammo_boosted}")

    for n in sorted(board_rewards):
        rw = ", ".join(f"{r}={v}" for r, v in board_rewards[n]) or "—"
        costs = board_costs.get(n, [])
        logging.info(f"   Board {n:>2}: reward [{rw}] | piece costs {costs} "
                     f"(Σ {sum(costs) if costs else 0})")

    logging.info("   🏁 Event-complete reward: "
                 + (", ".join(f"{r}={v}" for r, v in event_reward) or "—"))
    logging.info("   👑 Grand reward: "
                 + (", ".join(f"{r}={v}" for r, v in grand_reward) or "—"))

    def _delta(a, b):
        try:
            return (b or 0) - (a or 0)
        except Exception:
            return "N/A"

    wb_db, wa_db     = wallet_before.get("db", {}),   wallet_after.get("db", {})
    wb_data, wa_data = wallet_before.get("data", {}), wallet_after.get("data", {})
    logging.info(
        f"   💰 Gold Δ → UI:{_delta(wallet_before['gold_ui'], wallet_after['gold_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('gold'), wa_data.get('gold'))!s:>8}"
        f"  DB:{_delta(wb_db.get('gold'), wa_db.get('gold'))!s:>8}")
    logging.info(
        f"   💎 Gems Δ → UI:{_delta(wallet_before['gems_ui'], wallet_after['gems_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('gems'), wa_data.get('gems'))!s:>8}"
        f"  DB:{_delta(wb_db.get('gems'), wa_db.get('gems'))!s:>8}")
    logging.info(
        f"   🔨 Hmmr Δ → UI:{_delta(wallet_before['hammer_ui'], wallet_after['hammer_ui'])!s:>8}"
        f"  Data:{_delta(wb_data.get('pips'), wa_data.get('pips'))!s:>8}"
        f"  DB:{_delta(wb_db.get('pips'), wa_db.get('pips'))!s:>8}")
    logging.info("=" * 64)


# -----------------------------------------------------------------------
# MAIN TEST
# -----------------------------------------------------------------------
def test_puzzle_theatre(unity_driver, driver=None):
    start_time = time.time()
    steps = []

    def add_step(msg, status="INFO"):
        steps.append({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "status": status, "step": msg})
        logging.info(msg)

    try:
        add_step("🎭 ── test_15_puzzletheatre START ──", "PASS")

        # ── 1. Lobby + player_id + wallet (before) ───────────────────
        _to_lobby(unity_driver)
        get_user_snapshot(unity_driver)
        player_id = state.user_info.get("player_id")
        if not player_id:
            raise Exception("❌ [PT] Player ID missing")
        add_step(f"✅ Player ID: {player_id}", "PASS")
        wallet_before = _log_wallet(unity_driver, "before PT", player_id)

        # ── 2. Open PT + free ammo + FTUE + grand-reward preview + ammo ─
        if not _open_pt(unity_driver):
            raise Exception("❌ [PT] Could not open Puzzle Theatre")
        _handle_ftue(unity_driver)

        grand_preview = _rewards(unity_driver, PT_GRAND_REWARD_PANEL)
        add_step("👑 [PT] Grand reward (preview): "
                 + (", ".join(f"{r}={v}" for r, v in grand_preview) or "—"), "PASS")

        total_ammo_before = _num(unity_driver, PT_TOTAL_AMMO, 4)
        add_step(f"🔫 [PT] Total ammo in hand: {total_ammo_before}", "PASS")
        event_tracker.record("Puzzle Theatre", "Open", "PASS", f"ammo {total_ammo_before}")

        # ── 3. Close → boost ammo (Mongo) → reopen → verify ──────────
        _close_event(unity_driver)
        set_puzzle_theatre_ammo(player_id, PT_AMMO_TOPUP)
        db_ammo = get_puzzle_theatre_ammo(player_id)
        add_step(f"🎭 [PT] Boosted ammo → puzzleEventData.ammoBalance = {db_ammo}", "PASS")
        time.sleep(1)

        if not _open_pt(unity_driver):
            raise Exception("❌ [PT] Could not reopen Puzzle Theatre after boost")
        _handle_ftue(unity_driver)   # no-op if FTUE already done
        total_ammo_boosted = _num(unity_driver, PT_TOTAL_AMMO, 5)
        boost_ok = (total_ammo_boosted is not None
                    and total_ammo_boosted >= (total_ammo_before or 0)
                    and total_ammo_boosted >= int((db_ammo or 0) * 0.5))
        add_step(
            f"🔫 [PT] Total ammo after boost: {total_ammo_boosted} "
            f"(DB ammoBalance {db_ammo}) — {'boosted ✓' if boost_ok else 'NOT reflected ✗'}",
            "PASS" if boost_ok else "FAIL",
        )
        event_tracker.record("Puzzle Theatre", "Ammo Boost",
                             "PASS" if boost_ok else "FAIL",
                             f"ammo {total_ammo_boosted} / db {db_ammo}")

        # ── 4. Solve every puzzle board (adaptive) ───────────────────
        # Make sure we're on the All-Puzzles screen so the boards are enumerable.
        if not _present(unity_driver, PT_ALL_PUZZLE_LAYOUT, 2) and _present(unity_driver, PT_PUZZLE_FRAME, 1):
            # already dropped into a board's frame → back out via the event close-less path
            allp = _wait(unity_driver, PT_ALL_PUZZLES_ICON, 2)
            if allp:
                safe_tap(unity_driver, allp)
                time.sleep(1.5)
        boards = _board_indices(unity_driver)
        if not boards:
            boards = [1]   # at minimum, solve board 1 (adaptive discovery failed)
        add_step(f"🧩 [PT] Puzzle boards detected: {boards}", "PASS")

        board_rewards, board_costs = {}, {}
        empty_streak = 0
        for n in boards:
            add_step(f"🧩 [PT] ── Board {n} ──", "INFO")
            if not _enter_board(unity_driver, n):
                add_step(f"⚠️ [PT] Could not enter board {n} — skipping", "FAIL")
                empty_streak += 1
                if empty_streak >= 2:
                    add_step("⚠️ [PT] Two boards failed to open — stopping board loop", "FAIL")
                    break
                continue

            costs = _reveal_board_pieces(unity_driver, n)
            if not costs:
                # No piece cost registered → the board likely didn't actually
                # (re)open (stale reused frame). Re-enter once and retry.
                logging.info(f"↻ [PT] Board {n} produced no reveals — re-entering once")
                if _enter_board(unity_driver, n):
                    costs = _reveal_board_pieces(unity_driver, n)
            board_costs[n] = costs

            if not costs:
                add_step(f"⚠️ [PT] Board {n}: no pieces revealed (board did not open)", "FAIL")
                empty_streak += 1
                if empty_streak >= 2:
                    add_step("⚠️ [PT] Boards not opening — stopping board loop", "FAIL")
                    break
                continue
            empty_streak = 0

            board_rewards[n] = _collect_reward_screen(unity_driver, f"Board {n}")
            event_tracker.record("Puzzle Theatre", f"Board {n}", "PASS",
                                 f"pieces {len(costs)}, cost {sum(costs)}")
            # Collecting the reward returns the game to the All-Puzzles grid;
            # give it a moment before the next board's tile is tapped.
            time.sleep(1.5)
            _present(unity_driver, PT_ALL_PUZZLE_LAYOUT, 4)

        # ── 5. Event-complete reward → grand reward → done ───────────
        event_reward = _collect_reward_screen(unity_driver, "Event complete", timeout=15)

        grand_reward = []
        if _present(unity_driver, PT_GRAND_REWARD_SCREEN, 10):
            grand_reward = _rewards(unity_driver, PT_GRAND_REWARD_SCREEN) or grand_preview
            gcta = wait_for_safe(unity_driver, By.PATH, PT_GRAND_REWARD_COLLECT, 8)
            if gcta:
                safe_tap(unity_driver, gcta)
                time.sleep(2)
                add_step("👑 [PT] Grand reward collected — event complete", "PASS")
            else:
                _tap_screen_center(unity_driver)
            event_tracker.record("Puzzle Theatre", "Grand Reward", "PASS", "collected")
        else:
            add_step("ℹ️ [PT] Grand reward screen not shown", "INFO")

        # ── 6. Close → lobby → wallet (after) + summary ──────────────
        _close_event(unity_driver)
        wallet_after = _log_wallet(unity_driver, "after PT", player_id)
        _print_summary(wallet_before, wallet_after, board_rewards, board_costs,
                       event_reward, grand_reward, total_ammo_before, total_ammo_boosted)

        boards_done = len([n for n in boards if board_costs.get(n)])
        status = "PASS" if (boost_ok and boards_done > 0) else "FAIL"
        add_step(
            f"✅ Puzzle Theatre completed — {boards_done}/{len(boards)} boards solved"
            if status == "PASS" else
            f"⚠️ Puzzle Theatre completed with issues — {boards_done}/{len(boards)} boards",
            status,
        )
        return {
            "name": "Puzzle Theatre",
            "status": status,
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }

    except Exception as e:
        logging.exception("❌ Puzzle Theatre Test Failed")
        add_step(f"❌ Test failed: {str(e)}", "FAIL")
        return {
            "name": "Puzzle Theatre",
            "status": "FAIL",
            "duration": round(time.time() - start_time, 2),
            "steps": steps,
            "unity_driver": unity_driver,
        }
