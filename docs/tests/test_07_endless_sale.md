# Endless Sale

`tests/test_07_endless_sale.py` · `test_endless_sale(unity_driver, driver)` · types: `smoke, iap, regression, complete`

## Purpose
Runs the Endless Sale lobby offer end-to-end: opens the popup and works through its reward-tile track, claiming free tiles and purchasing paid tiles via Google Play, while logging a 3-way (UI/Data/DB) wallet comparison before and after. A `smoke` run stops after exactly one paid purchase; other run types continue until the sale's own complete screen appears or no further tile is found.

## Preconditions
- `unity_driver` connected to AltTester (app `sorry`). If the caller passes `driver=None`, the function falls back to `state.get("appium_driver")` and raises `RuntimeError("No Appium driver available")` if that is also unset (`tests/test_07_endless_sale.py:131-134`).
- `state.get("run_type")` should already be set by the suite runner (defaults to `"complete"` if absent) — this is what selects smoke vs. complete tile-loop behavior, not a function argument (`:124-126`).
- `state.user_info["player_id"]` should already be populated (e.g. by Guest Login) so the DB wallet lookup has a key; if it's missing, the DB read is simply skipped in favor of `{}` (`:157, 161`).
- The Endless Sale offer must be live in-game — the lobby icon (`ES_ICON`) has to render within 15s or the test SKIPs instead of proceeding (`:168-176`).

## Flow
1. **Suppress auto-close** — `popup_handler.ignore_popup(ES_CLOSE)` for the whole test, since `ES_CLOSE` sits in `POPUP_PRIORITY`'s HIGH tier and would otherwise get auto-dismissed mid-test (`:140`).
2. **Home + clear popups** — wait for `HOME_BUTTON` (5s), tap if found, then `clear_all_popups(unity_driver)` (`:146-152`).
3. **Wallet BEFORE** — UI via `fast_text`+`parse_amount` on `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`, Data via `get_wallet_from_data(unity_driver)`, DB via `get_user_wallet(player_id)`; all three logged together by `_log_wallet_comparison("BEFORE", ...)` (`:156-162`, helper at `:96-109`).
4. **Open Endless Sale** — wait up to 15s for `ES_ICON`; if absent, warn, `event_tracker.record("IAP", "Endless Sale", "SKIP")`, and return `unity_driver` immediately (`:167-176`). Otherwise tap it, sleep 2s, then wait up to 10s for `ES_POPUP` (raises `Exception` if it never opens) (`:178-184`).
5. **Ammo Progress BEFORE** — `_read_ammo_progress` reads `ES_AMMO_PROGRESS` text, defaulting to `"N/A"` (`:189-190`, helper `:69-71`).
6. **Tile loop** (`while True`, `:201-262`), once per tile:
   - Stop if `ES_COMPLETE_SCREEN` appears (2s check) → `complete = True`, break (`:205-208`).
   - Wait up to 8s for `ES_TILE_PRICE`; if not found, warn and break (no more tiles) (`:211-214`).
   - `_log_tile` reads price (`ES_TILE_PRICE`), both reward amounts (`ES_TILE_REWARD_1`/`ES_TILE_REWARD_2`), and ammo (`ES_TILE_AMMO`); `is_free` is `price.strip().lower() == "free"` (`:74-93`, called `:216`).
   - Wait up to 5s for `ES_TILE_BUY_BTN`; if not found, warn and break (`:218-221`).
   - **Free tile** → tap, sleep 3s for the claim animation, loop again (`:223-227`).
   - **Paid tile** → tap, sleep 3s, then `handle_google_play_purchase(driver)`; record `event_tracker.record("IAP", f"Endless Sale tile {tile_num}", "PASS"/"FAIL")`; sync `state.set("appium_driver", driver)`; `reconnect_alttester(unity_driver)` and sync `state.set("unity_driver", ...)`; sleep 3s more for the claim animation; increment `paid_bought` (`:229-246`). After the *first* paid purchase only, log ammo progress again (`:249-251`). If `is_smoke`, stop the whole loop right here (`:253-255`); otherwise re-check `ES_COMPLETE_SCREEN` (3s) and stop if it now appears (`:257-261`).
7. **Ammo Progress AFTER** — re-read `ES_AMMO_PROGRESS` and log the before→after strings (no numeric diff) (`:266-268`).
8. **Complete screen dismiss** — if `complete` was set, wait up to 5s for `ES_COMPLETE_SCREEN` and tap it, sleep 2s (`:273-278`).
9. **Close popup** — wait up to 5s for `ES_CLOSE`, tap if found (warn if not) (`:283-289`).
10. **Wallet AFTER + delta** — same 3 sources re-read; UI delta is a plain subtraction, Data/DB deltas go through `_safe_delta` (returns `"N/A"` if either side is `None`) (`:294-307`, helper `:317-321`).
11. **Finally** — `popup_handler.unignore_popup(ES_CLOSE)` always runs, even on exception (`:311-312`).
12. Returns `unity_driver` (possibly the AltTester-reconnected instance from step 6) (`:314`).

## Key element paths
| Purpose | Constant | Path |
|---|---|---|
| Lobby home button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Home gold / gems text | `HOME_GOLD_TEXT` / `HOME_GEMS_TEXT` | `.../HomeScreen/topSections/commonHUD/root/Container/coinBar\|gemBar/text` |
| Endless Sale lobby icon | `ES_ICON` (= `HF_ENDLESS_SALE_ICON`) | `.../HomeScreen/topSections/lobbyWidgetSection/.../IconsRHS/mineRunWidget/scaleAdjuster/root/buttonArea` |
| Sale popup root | `ES_POPUP` | `/Canvas/ModalLayer/EndlessSalePopup(Clone)` |
| Sale close button | `ES_CLOSE` | `/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea` |
| Ammo progress counter | `ES_AMMO_PROGRESS` | `.../EndlessSalePopup(Clone)/container/header/progressBarMain/count/text` |
| Complete screen | `ES_COMPLETE_SCREEN` | `.../EndlessSalePopup(Clone)/container/congratulationsContainer/darkBG` |
| Current tile price | `ES_TILE_PRICE` | `.../slot1/EndlessSaleRewardPanel/buyCTA/root/textContainer/priceText` |
| Current tile reward 1 / 2 | `ES_TILE_REWARD_1` / `ES_TILE_REWARD_2` | `.../rewardContainer/layout/BaseRewardInstantiator/root/SpriteRewardItem_10/visualParent/rewardMain/textMain/amountText/text` (reward 2: `BaseRewardInstantiator_1/.../SpriteRewardItem_19/...`) |
| Current tile ammo banner | `ES_TILE_AMMO` | `.../slot1/EndlessSaleRewardPanel/rewardContainer/showelContainer/banner/textShadow/text` |
| Current tile buy/claim button | `ES_TILE_BUY_BTN` | `.../slot1/EndlessSaleRewardPanel/buyCTA/TouchArea` |

## Data & DB interactions
- **3-way wallet check** BEFORE/AFTER (`_log_wallet_comparison`, `tests/test_07_endless_sale.py:96-109`): UI → `fast_text`+`parse_amount` on `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`; Data → `get_wallet_from_data(unity_driver)` (`utils/helpers.py:50-88`), calling Unity `UserManager.GetGold/GetGems/GetPips` through AltTester; DB → `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`), reading the `wallet` sub-document from the `sorry_users.users` collection keyed by `info.gameCode`.
- Read-only DB access — no Mongo writes or boosts in this test.
- Per-tile purchase outcomes go to `event_tracker.record("IAP", ...)` for the run report only, not to the database.
- No `get_user_snapshot` call — `player_id` is read from existing `state.user_info` and never (re)fetched here.

## Pass / fail criteria
- Returns the (possibly AltTester-reconnected) `unity_driver` — no result dict. The suite runner (`run_this.py`) treats a plain object return as an implicit PASS; a FAIL is recorded only if an exception propagates out of the function.
- Raises (→ FAIL): no Appium driver available at all (`:134`); Endless Sale popup not opening after the icon tap (`:183`).
- Icon not found within 15s is an explicit **SKIP**, not a failure: warns, records `event_tracker.record("IAP", "Endless Sale", "SKIP")`, and returns normally (`:170-176`) — the runner still sees a plain return, so this counts as PASS at the suite level even though the report's IAP section shows SKIP.
- All other missing elements mid-loop (tile price/buy button, close button) only log warnings and break the loop — they never raise.
- Each paid-tile purchase is recorded individually via `event_tracker.record` PASS/FAIL, but a failed purchase does not stop the loop or fail the test by itself.

## Notes & known flakiness
- Smoke vs. complete behavior is read from shared `state.get("run_type")`, not from a parameter — the function signature is just `(unity_driver, driver)`.
- The complete-run tile loop has no iteration cap beyond "no tile found" / "complete screen appears" — its length is entirely dictated by the live sale's configured tile count.
- `ES_AMMO_PROGRESS` is logged as a raw string (e.g. `"3/10"`) before/after with no numeric parsing or diffing, unlike gold/gems.
- `is_free` is a plain string compare (`price.strip().lower() == "free"`) — depends on the sale always labeling free tiles exactly `"Free"`.
- Every paid tile drives a real Google Play purchase (`handle_google_play_purchase`) followed by an AltTester reconnect — meaningful end-to-end verification needs an on-device Google Play (sandbox/test) purchasing setup, not just AltTester.
