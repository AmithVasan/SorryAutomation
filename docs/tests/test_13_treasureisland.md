# Treasure Island

`tests/test_13_treasureisland.py` · `test_treasure_island(unity_driver, driver=None)` · types: `complete`

## Purpose
Plays a full Treasure Island (internally "Fortune Island") event pass: runs the FTUE if needed, boosts event ammo in Mongo, then adaptively opens chests level-by-level until every level's Doubloon Key is found and the event-complete reward is claimed.

## Preconditions
- Account signed in and lobby reachable (test taps `HOME_BUTTON` and clears popups first).
- `state.user_info["player_id"]` must resolve (falls back to `get_user_snapshot`) — the test raises if no player ID is available (`tests/test_13_treasureisland.py:466-471`).
- `state.get("device_id")` must be set for the kill/relaunch ADB commands to run (a missing device ID only logs a warning, it does not abort the test).
- Treasure Island event must be live in-game so `TI_ICON` is present on the lobby.

## Flow
Mirrors the numbered flow in the module docstring (`tests/test_13_treasureisland.py:1-33`); line refs point to `test_treasure_island`:
1. **Home + clear popups** — wait for `HOME_BUTTON`, tap, `clear_all_popups` (`tests/test_13_treasureisland.py:459-463`).
2. **Player ID** — read `state.user_info["player_id"]`; if absent, call `get_user_snapshot(unity_driver)` and retry; raise on failure (`:466-472`).
3. **Wallet (before)** — `_log_wallet` logs UI/Data/DB gold+gems via `fast_text`, `get_wallet_from_data`, `get_user_wallet` (`:475`, helper at `:217-228`).
4. **Open TI + read level** — `_open_ti` taps `TI_ICON`, sleeps 4s, `clear_all_popups`, confirms `TI_MAIN_MODAL` or `TI_LEVEL_PROGRESS` (`:234-242`). `_read_level` parses the level number from `TI_LEVEL_PROGRESS` text (`:96-100`). Level < 2 ⇒ FTUE not done. Close TI (`_close_ti`, taps `TI_CLOSE`) and clear popups (`:478-488`).
5. **FTUE (conditional)** — if FTUE not done, call the imported `_do_treasure_island(unity_driver)` from `tests/test_02_happy_flow.py` (opens `HF_TI_ICON`, dismisses the info screen, handles the free-ammo modal, runs a 6-tap generic overlay-dismiss loop, then taps `HF_TI_CLOSE`); otherwise skip (`:491-496`).
6. **Kill → boost → relaunch** — `_kill_game` stops the AltTester driver and `adb shell am force-stop` the package, sleeps 3s (`:261-277`). `set_treasure_island_ammo(player_id, TI_AMMO_TOPUP=900)` writes the boost **while the game is dead** — the module warns that boosting a live game gets clobbered when the app syncs `ammCnt=0` back on shutdown (`:498-506`, rationale at `:252-260`). `_launch_and_reconnect` does `adb shell am start`, sleeps 10s, then `connect_altunity` and stores the new driver in `state` (`:280-294`, called at `:508`).
7. **Re-clear lobby** — `clear_all_popups` once, then up to 3 more passes while it keeps finding popups (`:511-518`).
8. **Reopen TI + confirm level** — `_open_ti` again; logs a warning (does not fail) if level is still < 2 (`:521-526`).
9. **Level loop** (up to `MAX_LEVELS=25`) — for each level, `_play_level`:
   - Dismisses `TI_CHECKPOINT_FTUE` if present (`:343-346`).
   - Reads level number/ammo, pulls `TI_LEVEL_REWARDS_CONTAINER` amounts, pulls the kitty bag via `_pull_kitty` (taps `TI_KITTY_TAP`, reads `TI_KITTY_CONTAINER` in the ~1-2s tooltip window, retries up to 3x) (`:348-365`).
   - Chest loop (`:367-398`, up to `MAX_CHESTS_PER_LEVEL=60`): stop early if `TI_COMPLETE_SCREEN` appears; `_find_chests` (`:182-211`) looks for `Chest_1/2/3` under `TI_CHEST_SLOTS` (falls back to probing slots 0-40 directly); taps the first chest found; `_handle_chest_outcome` (`:300-334`) resolves the result — dismisses `TI_BOMB_FTUE` if shown, then checks `TI_BOMB_MODAL` (reads `TI_REVIVE_COST`, taps `TI_REVIVE_BUTTON`, increments `bombs`), else checks `TI_DOUBLOON_KEY` (level complete), else treats it as a `"reward"` added to the kitty bag.
   - On `"doubloon"`: taps `TI_DOUBLOON_KEY`, sleeps `LEVEL_TRANSITION_SEC=3`, marks the level `completed` (`:390-398`).
   - Records per-level stats via `event_tracker.record("Treasure Island", ...)` (`:409-414`).
   - The outer loop stops if the complete screen appears or a level finishes without a doubloon (`:530-540`).
10. **Event Complete** — if `TI_COMPLETE_SCREEN` is present, pulls `TI_EVENT_COMPLETE_CONTAINER` rewards, taps the complete-screen node itself to claim, records the event (`:543-554`).
11. **Close → lobby → wallet (after)** — `_close_ti`, tap `HOME_BUTTON`, `clear_all_popups`, `_log_wallet` "after", then `_print_summary` logs per-level chests/bombs/revives/doubloon-chest/ammo and the DB gold/gem delta (`:558-567`, summary at `:421-440`).

## Key element paths
| Purpose | Constant | Path |
|---|---|---|
| Lobby home button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Home gold / gems text | `HOME_GOLD_TEXT` / `HOME_GEMS_TEXT` | `.../HomeScreen/topSections/commonHUD/root/Container/coinBar\|gemBar/text` |
| TI lobby icon | `TI_ICON` (= `HF_TI_ICON`) | `.../HomeScreen/topSections/lobbyWidgetSection/.../FortuneIslandLobbyWidget/.../mainIcon` |
| TI close button | `TI_CLOSE` (= `HF_TI_CLOSE`) | `/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/closeButton/closeButton/touchArea` |
| TI main modal / level header | `TI_MAIN_MODAL` / `TI_LEVEL_PROGRESS` | `.../FortuneIslandMainModal(Clone)/Container` / `.../LevelPanel/TextStyle_Amount_T1_medium/text` |
| Total ammo counter | `TI_TOTAL_AMMO` (= `HF_TI_TOTAL_AMMO`) | `.../FIMainScreenAmmoUI/root/container/bg/textLabel/.../text` |
| Chest slots container | `TI_CHEST_SLOTS` | `.../Container/Anchored/ScalableLayout/ChestLayout/ChestSlots` |
| Doubloon key (level complete tap) | `TI_DOUBLOON_KEY` | `.../FortuneIslandLevelCompleteRewardsModal/ClickArea` |
| Bomb modal / revive cost / revive button | `TI_BOMB_MODAL` / `TI_REVIVE_COST` / `TI_REVIVE_BUTTON` | `/Canvas/ModalLayer/FortuneIslandBombHitModal(Clone)` (+ `GreenCTA ` — note real trailing space in the node name) |
| Level reward / kitty bag containers | `TI_LEVEL_REWARDS_CONTAINER` / `TI_KITTY_CONTAINER` | `.../FIMainScreenLevelRewardsUi/bgImage/Rewards` / `.../FIMainScreenKittyBagUI/root/RewardInfoTooltip/content/rewardsContainer` |
| Kitty bag tap target | `TI_KITTY_TAP` | `.../FIMainScreenKittyBagUI/root` |
| Event-complete container / tap-to-claim | `TI_EVENT_COMPLETE_CONTAINER` / `TI_COMPLETE_SCREEN` | `.../FortuneIslandEventCompleteRewardsModal/container` (+ `/bottomContent/tapToClaimtext`) |
| Checkpoint / bomb FTUE overlays | `TI_CHECKPOINT_FTUE` / `TI_BOMB_FTUE` | `.../Container/CheckpointFtueHandler/overlay` / `.../BombFtueHandler/overlay` |

## Data & DB interactions
- **Boost field**: `frtnIslndDt.ammCnt` (a sibling of `frtnIslndDt.data`, not nested inside it) via `set_treasure_island_ammo(player_id, ammo=900)` (`utils/mongo_helper.py:186-227`). `TI_AMMO_TOPUP = 900` (`tests/test_13_treasureisland.py:68`). Must be written while the game is force-stopped, per the helper's own docstring.
- **3-way wallet check** (`_log_wallet`, `tests/test_13_treasureisland.py:217-228`):
  - UI → `fast_text(unity, HOME_GOLD_TEXT)` / `HOME_GEMS_TEXT`, parsed with `parse_amount`.
  - Data → `get_wallet_from_data(unity)` (`utils/helpers.py:50-88`), which calls `UserManager.GetGold`/`GetGems`/`GetPips` in-memory via AltTester (`call_static_method`, falling back to `call_component_method` on a found `UserManager` component).
  - DB → `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`), reads the `wallet` sub-document (`gold`/`gems`/`pips`) from Mongo by `info.gameCode`.
- **Player snapshot**: `get_user_snapshot(unity_driver)` (`utils/helpers.py:91-145`) opens the profile modal, reads name/country/ID/level/xp/equipped pawn plus HUD gold/gems/hammer, and stores them into `state.user_info`; only invoked here as a player-ID fallback.
- Level-by-level outcomes and the Event Complete result are pushed to `event_tracker.record("Treasure Island", ...)` for the run report (`utils/event_tracker.py:124-162`).

## Pass / fail criteria
- The function always returns `{"name": "Treasure Island", "status", "duration", "steps", "unity_driver"}`.
- `status = "PASS"` if the whole flow runs to completion without an unhandled exception — including the branch where the event-complete screen is never reached (that branch only adds an `"INFO"` step, it does not fail the test) (`tests/test_13_treasureisland.py:555-556, 569-576`).
- `status = "FAIL"` only on an unhandled exception (missing player ID, TI failing to open/reopen) — caught in the outer `try/except`, logged, and returned with the steps captured so far (`:578-587`).
- Per-level and Event-Complete outcomes are separately recorded via `event_tracker.record` with their own PASS/FAIL (e.g. a level without a doubloon records "FAIL" for that level, `:409-414`), but this does not by itself flip the top-level test `status`.
- `unity_driver` in the returned dict is the **reconnected** driver from the post-boost relaunch, so the caller keeps using the live session.

## Notes & known flakiness
- Chest layout is random (up to 40 slots, 3 chest variants) — chest discovery, bomb/reward/doubloon outcomes, and per-level chest/bomb counts are inherently non-deterministic; safety caps (`MAX_LEVELS=25`, `MAX_CHESTS_PER_LEVEL=60`) exist purely to bound runaway loops, not to assert a specific count.
- The kitty bag is only readable in the ~1-2s window after tapping it (tooltip auto-hides); `_pull_kitty` retries up to 3 times with sleeps to catch it.
- The kill→boost→relaunch step is the same pattern used in Bump To Spin and (with a close-instead-of-kill variant) Puzzle Theatre; boosting while the game is alive is documented as unsafe here because shutdown re-syncs the in-memory `ammCnt=0`.
- `_do_treasure_island` (imported from `test_02_happy_flow.py`) dismisses several FTUE overlays with a fixed 6-iteration generic tap loop rather than per-element waits — the file's own comment block describes more granular sub-steps than the code currently implements (see that module for the discrepancy).
- Full correctness (doubloon discovery, reward math, event-complete reward) can only be validated on-device against a live, currently-running Treasure Island event; these are not exercised by any assertion beyond "did the loop terminate / did the screen appear."
