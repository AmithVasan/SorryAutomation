# Puzzle Theatre

`tests/test_15_puzzletheatre.py` · `test_puzzle_theatre(unity_driver, driver=None)` · types: `complete`

## Purpose
Plays a full Puzzle Theatre (PT) event pass: claims FTUE free ammo, boosts event ammo in Mongo, then adaptively solves every discovered puzzle board (revealing every piece, logging its ammo cost) before collecting the event-complete and grand rewards.

## Preconditions
- Account signed in, lobby reachable; PT event live so `PT_ICON` (= `HF_PUZZLE_ICON`) is present.
- `state.user_info["player_id"]` must resolve via `get_user_snapshot`; the test raises if it doesn't (`tests/test_15_puzzletheatre.py:401-404`).
- `state.get("device_id")` should be set — used only for the raw ADB "tap screen center" fallback (`_tap_screen_center`, `:125-135`), not for any kill/relaunch here.
- Unlike Treasure Island / Bump To Spin, this test does **not** force-stop or relaunch the game — the boost is applied via close-event→write-DB→reopen-event while the game keeps running, per the module docstring (`:26-33`). Note the discrepancy with the "kill→boost→relaunch" pattern used by the other two event tests.

## Flow
Mirrors the module docstring flow (`tests/test_15_puzzletheatre.py:1-34`); line refs point to `test_puzzle_theatre`:
1. **Lobby + player ID + wallet (before)** — `_to_lobby` (tap `HOME_BUTTON`, `clear_all_popups`), `get_user_snapshot` for `player_id`, then `_log_wallet` "before PT" (UI/Data/DB gold, gems, hammer) (`:399-405`).
2. **Open PT + free ammo + FTUE + grand-reward preview + ammo** — `_open_pt` taps `PT_ICON`, sleeps 4s, calls `_handle_free_ammo` (checks `PT_FREE_AMMO_MODAL`, scans `PT_FREE_AMMO_CONTAINER`, taps `PT_AMMO_CLAIM`), `clear_all_popups`, confirms `PT_MODAL`/`PT_TOTAL_AMMO`/`PT_ALL_PUZZLE_LAYOUT` (`:161-190`, called at `:408`). `_handle_ftue` best-effort taps `PT_FTUE_PIECE` then `PT_ALL_PUZZLES_ICON` (`:192-204`, called at `:410`). Reads `PT_GRAND_REWARD_PANEL` amounts as a preview and logs total ammo (`:412-418`).
3. **Close → boost ammo (Mongo) → reopen → verify** — `_close_event` taps `PT_EVENT_CLOSE` then `_to_lobby` (`:218-223`, called at `:421`). `set_puzzle_theatre_ammo(player_id, PT_AMMO_TOPUP=5000)` writes the boost; `get_puzzle_theatre_ammo(player_id)` immediately reads it back from the DB as `db_ammo` (`:422-424`). Reopens with `_open_pt` + `_handle_ftue` (no-op if FTUE already done) (`:427-429`). Reads `total_ammo_boosted` and computes `boost_ok = total_ammo_boosted is not None and total_ammo_boosted >= (total_ammo_before or 0) and total_ammo_boosted >= int((db_ammo or 0) * 0.5)` — i.e. the UI ammo must be at least half the DB value written, a tolerance rather than an exact-match check (`:430-441`).
4. **Solve every board (adaptive)** — ensures the All-Puzzles screen is showing (backs out of a board frame via `PT_ALL_PUZZLES_ICON` if needed) (`:444-450`). `_board_indices` probes `PT_BOARD_TMPL.format(n=n)` for `n` in `1..MAX_BOARDS(30)`, stopping after two consecutive misses (adaptive; falls back to `[1]` if none found) (`:226-238`, called at `:451-453`). For each board `n`:
   - `_enter_board`: if already inside `PT_PUZZLE_FRAME`, no-op; else tap the `PT_BOARD_TMPL` node, sleep 2.5s, confirm `PT_PUZZLE_FRAME` within 6s — on failure, logs a `"FAIL"` step and skips the board (`:327-337`, `:459-461`).
   - `_reveal_board_pieces`: up to `MAX_PIECES_PER_BOARD(30)` iterations — stop if `PT_REWARD_SCREEN` appears (board complete); re-query `PT_PIECE_BTNS` (find_objects under `PT_PIECE_GROUP`) each round; tap the first button; sleep `REVEAL_SETTLE=1.5`; the ammo drop across the tap (`PT_TOTAL_AMMO` before/after) is recorded as that piece's cost; a stall guard bails after 2 rounds of unchanged button-count + no ammo drop (`:274-324`, called at `:462`).
   - `_collect_reward_screen(..., f"Board {n}")`: waits for `PT_REWARD_SCREEN` (default 12s timeout), scans `PT_REWARD_ROOT` amounts, taps `PT_REWARD_COLLECT` (falls back to a raw ADB screen-center tap if the CTA isn't found), and re-taps once more if the screen chains into a second one (`:244-268`, called at `:463`).
   - Records the board via `event_tracker.record("Puzzle Theatre", f"Board {n}", ...)`, sleeps 1.5s, and checks `PT_ALL_PUZZLE_LAYOUT` is back (routine — the return value isn't branched on) (`:464-468`).
5. **Event-complete → grand reward** — `_collect_reward_screen(..., "Event complete", timeout=15)` (`:471`). If `PT_GRAND_REWARD_SCREEN` appears within 10s, scans it for amounts (falling back to the earlier `grand_preview` if the scan is empty), taps `PT_GRAND_REWARD_COLLECT` (or a raw tap-center fallback), and records the Grand Reward event; otherwise logs an `"INFO"` step that the grand-reward screen wasn't shown (`:473-485`).
6. **Close → lobby → wallet (after) + summary** — `_close_event`, `_log_wallet` "after PT", `_print_summary` (per-board reward + piece costs, event/grand reward, UI/Data/DB wallet deltas) (`:488-491`, summary at `:343-380`).

## Key element paths
| Purpose | Constant | Path |
|---|---|---|
| PT lobby icon | `PT_ICON` (=`HF_PUZZLE_ICON`) | `.../HomeScreen/topSections/lobbyWidgetSection/.../PuzzleEventWidget/.../mainIcon` |
| Free-ammo modal / claim | `PT_FREE_AMMO_MODAL` / `PT_AMMO_CLAIM` | `GenericCommonModal(Clone)/rootMain/layout/baseBg` / `.../buttonsGroup/SorryButtonType-Text/TouchArea` |
| PT modal / event close | `PT_MODAL` / `PT_EVENT_CLOSE` | `/Canvas/ModalLayer/PuzzleEventModal(Clone)` / `.../closeButton/closeGrpAnimate/.../touchArea` |
| Total ammo counter | `PT_TOTAL_AMMO` | `PuzzleEventModal(Clone)/Container/footer/PuzzleHUD/.../text` |
| FTUE piece / All Puzzles icon | `PT_FTUE_PIECE` / `PT_ALL_PUZZLES_ICON` | `CommonNudgeModal(Clone)/Btn(Clone)` / `CommonNudgeModal(Clone)/buttonCTA(Clone)` |
| Grand reward preview panel | `PT_GRAND_REWARD_PANEL` | `PuzzleEventModal(Clone)/Container/RewardPanel` |
| All-puzzles layout / board template | `PT_ALL_PUZZLE_LAYOUT` / `PT_BOARD_TMPL` | `.../AllPuzzle/PuzzlesLayout` / `.../PuzzlesLayout/PuzzleNumber_{n}` |
| Puzzle frame (inside a board) | `PT_PUZZLE_FRAME` | `PuzzleEventModal(Clone)/Container/PuzzleBoard/PuzzleFrame` |
| Piece reveal buttons | `PT_PIECE_BTNS` | `.../PuzzlePieces/puzzlePieceGrp//Btn` (find_objects, all descendants) |
| Reward screen / root / collect | `PT_REWARD_SCREEN` / `PT_REWARD_ROOT` / `PT_REWARD_COLLECT` | `RewardSummaryModal(Clone)/darkBG` / `.../rootMain` / = `REWARD_SUMMARY_CTA` |
| Grand reward screen / collect | `PT_GRAND_REWARD_SCREEN` / `PT_GRAND_REWARD_COLLECT` | `PuzzleEventModal(Clone)/Blocker` / `GrandEventStartPopup(Clone)/.../footer/CTA/TouchArea` |

## Data & DB interactions
- **Boost field**: `puzzleEventData.ammoBalance` via `set_puzzle_theatre_ammo(player_id, ammo=5000)` (`utils/mongo_helper.py:282-322`); read back with `get_puzzle_theatre_ammo(player_id)` which returns `puzzleEventData.ammoBalance` from `get_user_from_db` (`utils/mongo_helper.py:325-328`). `PT_AMMO_TOPUP = 5000` (`tests/test_15_puzzletheatre.py:66`). Unlike TI/BTS, the helper's docstring says to call it "after closing the event to the lobby, then re-open" — no game kill required.
- **3-way wallet check** (`_log_wallet`, `:141-155`): UI via `fast_text` on `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`/`HOME_HAMMER_TEXT`; Data via `get_wallet_from_data(unity)` (`UserManager.GetGold`/`GetGems`/`GetPips`, `utils/helpers.py:50-88`); DB via `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`, returns the `wallet` sub-document).
- `get_user_snapshot(unity_driver)` (`utils/helpers.py:91-145`) is the source of `player_id` and populates `state.user_info`.
- `event_tracker.record(...)` is called for Open, Ammo Boost, each Board, and Grand Reward (`:418, 439-441, 464-465, 483`).

## Pass / fail criteria
- Always returns `{"name": "Puzzle Theatre", "status", "duration", "steps", "unity_driver"}`.
- `boards_done` = count of boards in `boards` whose `board_costs[n]` is truthy (at least one piece revealed). `status = "PASS"` if `boost_ok` **and** `boards_done > 0`, else `"FAIL"` (`tests/test_15_puzzletheatre.py:493-500`) — this is a DB/behavior-verified pass condition, not just "no exception," similar to Bump To Spin.
- `status = "FAIL"` also on any unhandled exception (missing `player_id`, PT failing to open/reopen after boost) — caught in the outer `try/except` (`:509-518`).
- A board that fails to open (`_enter_board` returns `False`) is skipped with a `"FAIL"` step but does not raise — it only affects `boards_done` and thus the final status if no board succeeds.

## Notes & known flakiness
- Board count (6 today per the docstring) and pieces-per-board (4/6/8…) are discovered at runtime, not hard-coded — `_board_indices` and the per-board piece loop both re-query the UI adaptively so the test keeps working if content changes.
- Per-piece ammo cost is inferred purely from the drop in the `PT_TOTAL_AMMO` counter across a single reveal tap; if the counter doesn't visibly change (lag, or the tap missed), that piece's cost is silently not recorded rather than defaulted to zero.
- The `boost_ok` check uses a ≥50%-of-DB-value tolerance rather than an exact match against `db_ammo`, so a partially-stale UI read can still pass.
- Reward screens for board-complete and event-complete share the same `RewardSummaryModal` path family; a screen can rarely chain into a second one, which `_collect_reward_screen` handles with one extra collect attempt only.
- Several reward/collect taps fall back to a raw ADB "tap screen center" (`_tap_screen_center`) when the CTA element isn't tappable — this assumes a specific screen resolution/coordinate (540, 1200) and is a best-effort fallback, not guaranteed to hit the right control on all devices.
- Full correctness (adaptive board/piece discovery matching the live event's actual content, grand-reward payout) can only be validated on-device against a currently-running Puzzle Theatre event.
