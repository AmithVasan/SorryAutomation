# City Build

`tests/test_11_city_build.py` · `test_city_build(unity_driver, driver)` · types: `smoke, complete`

## Purpose
Taps through every City Build card until the city finishes construction, collects the completion reward, and logs a full before/after comparison of Gold, Gems, and Hammer (the build currency) across UI, Unity in-memory data, and MongoDB, plus a per-card tap/hammer-spend summary.

## Preconditions
- The test navigates Home itself (`HOME_BUTTON`, tolerant if not found) and clears popups before reading the wallet, so it does not strictly require already being on Home (tests/test_11_city_build.py:210-216).
- `state.user_info["player_id"]` should be populated for the DB wallet reads (`get_user_wallet`); if absent, `db_b`/`db_a` are just `{}` (tests/test_11_city_build.py:205, 226, 416).
- A city build must be in progress with at least one `buildCard_Revamped(Clone)` card under the build tray, and the City Build lobby icon (`CB_ICON`) must be visible from Home.

## Flow
1. Log start banner; read `player_id = state.user_info.get("player_id")` (tests/test_11_city_build.py:203-205).
2. Navigate Home: `_wait(unity_driver, HOME_BUTTON, 5)`; if found, tap + sleep 1 s. Then `clear_all_popups(unity_driver)` (tests/test_11_city_build.py:210-216).
3. Wallet BEFORE: `gold_ui_b`/`gems_ui_b`/`hammer_ui_b` via `fast_text` + `parse_amount` on `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`/`HOME_HAMMER_TEXT`; `data_b = get_wallet_from_data(unity_driver)`; `db_b = get_user_wallet(player_id)` (or `{}` if no `player_id`). Logged via `_log_snapshot("BEFORE", ...)` (tests/test_11_city_build.py:221-227).
4. Tap City Build icon: `wait_for_safe(unity_driver, By.PATH, CB_ICON, 10)`; raises `"❌ City Build icon not found"` if missing; tap + sleep 2 s (tests/test_11_city_build.py:232-237).
5. Dismiss Build FTUE info screen if shown: `_wait(unity_driver, CB_INFO_SCREEN, 4)`; if present, tap + log + sleep 1 s (tests/test_11_city_build.py:242-246).
6. Clear popups carried onto the build screen: sleep 1 s (lets a carried-over popup animate in, e.g. a Piggy Bank sale that the step-1 clear on Home couldn't have seen) then `clear_all_popups(unity_driver)` (tests/test_11_city_build.py:248-256).
7. Log initial Build Progress (`fast_text(CB_PROGRESS_BAR)` or `"N/A"`) and `event_tracker.record("City Build", "Build Started", "PASS", ...)` (tests/test_11_city_build.py:259-264).
8. Card loop — `for idx in range(MAX_CARDS=5)` (tests/test_11_city_build.py:269-343):
   - a. If `_card_active(idx)` isn't found (3 s wait), log how many cards the city actually has and `break` the outer loop (tests/test_11_city_build.py:276-279).
   - b. Log the card's hammer cost via `_card_hammer(idx)` → `fast_text` + `parse_amount` (default `0`) (tests/test_11_city_build.py:285-287).
   - c. Snapshot `hammer_before_card` from `HOME_HAMMER_TEXT` (tests/test_11_city_build.py:290).
   - d. Inner tap loop, up to `MAX_TAPS_PER_CARD=50` iterations (tests/test_11_city_build.py:295-340): re-finds `_card_active(idx)` each pass (Unity may refresh the object); if present, reads hammer pre/post around a `.tap()` + 2 s build-animation sleep and logs the per-tap delta; if the card object is temporarily gone (mid-animation), just sleeps 2 s instead. After each tap attempt it checks `CB_REWARD_SCREEN` (1 s) — if present, sets `reward_found=True` and breaks the inner loop (city finished mid-card); otherwise checks `_card_tick(idx)` (1 s) — if present, the card is done: increments `cards_completed`, computes `hammers_spent_card = abs(delta(hammer_before_card, hammer_after_card))`, appends `(card_num, cost_per_tap, tap_count, hammers_spent_card)` to `card_summaries`, logs progress + `event_tracker.record(..., f"Card {idx+1}", "PASS", ...)`, and breaks the inner loop.
   - e. If a card's inner loop exhausts all 50 taps without the tick or reward screen appearing, the loop simply ends and the outer loop moves to the next card index — no failure, no summary entry for that card.
   - f. If `reward_found` was set inside the inner loop, the outer card loop also breaks immediately (tests/test_11_city_build.py:342-343).
9. If the reward screen wasn't already seen, wait up to 10 s more for `CB_REWARD_SCREEN`; if still absent, raise `"❌ City Build Reward screen never appeared"` (tests/test_11_city_build.py:348-354).
10. Poll for the Collect Reward button with a 2-minute safety ceiling (`while time.time() < deadline`, checking `CB_COLLECT` every 2 s, sleeping 1 s between misses); raise `"❌ Collect Reward button never appeared within 2 minutes"` if the ceiling is hit; otherwise tap it and `event_tracker.record("City Build", "Reward Collected", "PASS")` (tests/test_11_city_build.py:356-377).
11. Poll the same way (2-minute ceiling) for the Build Close button (`CB_CLOSE`); if found, tap + sleep 1 s; if the ceiling is hit, only **log a warning and continue** — this does not raise (tests/test_11_city_build.py:379-401).
12. `clear_all_popups(unity_driver, timeout=10)` (tests/test_11_city_build.py:406).
13. Wallet AFTER: same reads as step 3, into `gold_ui_a`/`gems_ui_a`/`hammer_ui_a`/`data_a`/`db_a`, logged via `_log_snapshot("AFTER", ...)` (tests/test_11_city_build.py:411-417).
14. `_log_comparison(...)`: logs a boxed Before/After/Delta table for Gold/Gems/Hammer across UI/Data/DB, plus a per-card table (cost/tap, taps, hammers spent) with totals (tests/test_11_city_build.py:419-429, table builder at 140-192).
15. `event_tracker.record("City Build", "City Complete", "PASS", f"{cards_completed} cards | Gold Δ ... | Hammer Δ ...")`, then a final completion log line. The function has no explicit `return` statement (tests/test_11_city_build.py:431-441).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Home nav icon | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Home gold counter (UI) | `HOME_GOLD_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text` |
| Home gems counter (UI) | `HOME_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text` |
| Home hammer counter (UI) | `HOME_HAMMER_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/hammerBar/text` |
| City Build lobby icon | `CB_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/buildCTA/buttonCTA` |
| Build tray progress text | `CB_PROGRESS_BAR` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/progessBar/TextStyle_bodyText_02_extraSmall/text` |
| Build tray close | `CB_CLOSE` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/closeCTA/touchArea` |
| Build FTUE info screen | `CB_INFO_SCREEN` | `/Canvas/ModalLayer/BuildFtueInfoModal(Clone)/bg` |
| City completion / reward screen | `CB_REWARD_SCREEN` | `/Canvas/midUiLayer/cityCompletionScreen/darkBG` |
| Collect reward CTA | `CB_COLLECT` | `/Canvas/midUiLayer/cityCompletionScreen/rootMain/collectCTA/TouchArea` |
| Build cards container (base) | `_CB_CARDS_BASE` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/buildingCards/` |
| Per-card active node | `_card_active(idx)` | `_CB_CARDS_BASE + "buildCard_Revamped(Clone)" [+ "[idx]" if idx>0] + "/buildCardParent/card/activeCard"` |
| Per-card tick (complete) icon | `_card_tick(idx)` | same base + `".../buildCardParent/card/bottomContainer/tickIcon"` |
| Per-card hammer cost text | `_card_hammer(idx)` | same base + `".../buildCardParent/card/bottomContainer/valueTextBlue"` |

## Data & DB interactions
- **MongoDB (read-only)**: `get_user_wallet(player_id)` (utils/mongo_helper.py:116-135) finds the user by `{"info.gameCode": player_id}` and returns its `wallet` sub-document, or `{}` if `player_id` is falsy, no user matches, or an exception occurs. Called once before (`db_b`) and once after (`db_a`) the build; no writes.
- **Unity in-memory**: `get_wallet_from_data(unity_driver)` (`utils/helpers.py`) returns `{"gold", "gems", "pips"}` via AltTester calls into `UserManager` (`pips` = hammer currency).
- All three sources (UI / Data / DB) are captured before and after and diffed in `_log_snapshot`/`_log_comparison`, but purely for logging — no assertion is made on any Gold/Gems/Hammer value.

## Pass / fail criteria
- `test_city_build` has **no top-level try/except and returns no dict** — on success it simply falls off the end of the function (`None` return, tests/test_11_city_build.py:198-441). This differs from Lucky Cards' self-caught `{"status": ...}` pattern.
- The generic harness (`tests/test_registry.py` entry loaded by `run_this.py`, called as `test_func(unity_driver, driver)`) treats any non-dict, non-`Exception` return as **PASS**, and itself builds `{"name": display_name, "status": "PASS", "steps": collector.steps or ["Test executed successfully"]}` (run_this.py:969-1006).
- **FAIL** happens only if an exception propagates out of the test — City Build icon not found, City Build Reward screen never appearing (after both the per-card check and the final 10 s wait), or the Collect Reward button not appearing within its 2-minute ceiling. The harness's own `except Exception` catches this and records `{"name": display_name, "status": "FAIL", "steps": collector.steps + [f"Error: {e}"]}` (run_this.py:1008-1021).
- Asymmetry: the **Collect Reward** timeout raises (hard FAIL); the **Build Close** timeout does not — it only logs a warning and the test continues (tests/test_11_city_build.py:396-401).
- A card that never shows its tick within `MAX_TAPS_PER_CARD` (50) taps is silently skipped (no entry in `card_summaries`, `cards_completed` not incremented) without failing the test.

## Notes & known flakiness
- `driver` is accepted in the signature but never referenced in the function body.
- `MAX_CARDS = 5` is only a loop ceiling — the loop breaks as soon as `_card_active(idx)` isn't found, so 3- or 4-card cities behave the same as 5-card ones.
- `hammers_spent_card` is `abs(delta(hammer_before_card, hammer_after_card))`; `_delta_int` returns `None` (not `0`) if either read failed, and `abs(None or 0)` collapses that to `0`, which could mask a real read failure as "0 hammers spent" in the per-card table.
- The Collect Reward and Build Close waits are open-ended polling loops bounded only by a coarse 2-minute safety ceiling each, so a slow reward transition can add several minutes to the test before either failing (Collect) or just warning (Close).
- Step 6's popup clear specifically exists to catch a sale popup (e.g. Piggy Bank) that surfaces only after entering the build screen, which the Home-screen clear in step 2 cannot see.
