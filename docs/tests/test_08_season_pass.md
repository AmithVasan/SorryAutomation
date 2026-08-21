# Season Pass

`tests/test_08_season_pass.py` · `test_season_pass(unity_driver, driver, run_type=None)` · types: `iap, regression, complete`

## Purpose
Runs an end-to-end Season Pass IAP regression: opens Season Pass, spends gems to unlock one extra tier, purchases the premium pass through a real Google Play transaction, claims the Tier 1 rewards, force-completes the pass via a direct MongoDB write, restarts the app, reopens Season Pass, claims every remaining tier/reward screen, and logs a DB-vs-Data wallet comparison before and after. It is the suite's real-money purchase regression test for the Season Pass feature.

## Preconditions
- Active `unity_driver` (AltTester) and `driver` (Appium) sessions; the test assumes it can already reach a screen showing the Season Pass icon — it never taps `HOME_BUTTON` before the first `open_season_pass()` call (tests/test_08_season_pass.py:1086).
- `state.get("device_id")` must be set — `restart_game()` raises `"❌ device_id missing in state"` otherwise (tests/test_08_season_pass.py:77-83).
- `state.user_info["player_id"]` should already be populated, or `get_user_snapshot(unity_driver)` (utils/helpers.py) must be able to populate it — the test raises `"❌ Player ID missing"` if both fail (tests/test_08_season_pass.py:1025-1047).
- `MONGO_URI` env var must be set — `get_user_wallet` / `unlock_season_pass` raise via `get_client()` otherwise (utils/mongo_helper.py:18-25).
- Requires a Google Play test account able to complete a real (sandbox) purchase — `handle_google_play_purchase` (utils/google_play_helper.py) drives the actual Play Store UI.

## Flow
1. Initialize the `steps` log list and `add_step("🚀 Starting Season Pass Test", "PASS")` (tests/test_08_season_pass.py:991-1015).
2. Resolve `player_id` from `state.user_info`; if missing, call `get_user_snapshot(unity_driver)` (utils/helpers.py) once and re-read it; raise `"❌ Player ID missing"` if still absent (tests/test_08_season_pass.py:1025-1047).
3. Capture the "BEFORE" wallet: `get_user_wallet(player_id)` from MongoDB (raises `"❌ Failed to fetch BEFORE wallet"` if empty) and `get_wallet_from_data(unity_driver)` from Unity's `UserManager`; both are logged, neither is asserted (tests/test_08_season_pass.py:1058-1080).
4. `open_season_pass()`: runs a popup-clearing loop (`handle_one_popup` only, up to 10 s / 2 consecutive clean passes), then waits up to 20 s for `SEASON_PASS_ICON` (raises `"❌ Season Pass icon not found"` if missing), taps it, sleeps 5 s (tests/test_08_season_pass.py:171-217, 1086).
5. `unlock_one_tier_with_gems()`: waits up to 15 s for `UNLOCK_ONE_TIER_BTN` (raise if missing), taps it, reads the gem price off `SEASON_PASS_GEM_PRICE`, waits up to 15 s for `UNLOCK_CONFIRM_BTN` (raise if missing) and taps it — spends in-game gems to unlock one extra tier (tests/test_08_season_pass.py:224-272, 1097-1099).
6. `purchase_season_pass(unity_driver, driver)` — the real-money IAP leg; returns a possibly-reconnected `(unity_driver, driver)` pair (tests/test_08_season_pass.py:279-579, 1110-1113):
   - Globally ignores the `SeasonPassPurchaseModal` close path via `popup_handler.ignore_popup` so the global auto popup-closer can't dismiss it mid-flow (279-306).
   - Taps `ACTIVATE_BTN_PATH` (20 s wait), then `BUY_BTN_PATH` (20 s wait), logging the price text first (312-361).
   - Taps Buy, sleeps 5 s, then checks the Appium session is alive (`driver.current_activity`) and reconnects via `set_driver` if it died (363-406).
   - Calls `handle_google_play_purchase(driver)` (utils/google_play_helper.py); on reported failure, reconnects AltTester and checks for `SEASON_PASS_PURCHASE_MODAL` as a fallback confirmation before giving up and raising `"❌ Google Play purchase failed"` (412-455).
   - Polls up to 8 s for lingering Google Play packages/popups and closes them via `close_extra_google_play_popups` (465-510).
   - Sleeps 10 s, reconnects AltTester, and if `SEASON_PASS_PURCHASE_MODAL` appears taps `SEASON_PASS_PURCHASE_OK` (516-564).
   - `finally`: re-enables the globally-ignored popup via `popup_handler.unignore_popup` regardless of outcome (571-579).
7. `claim_tier1()`: taps `FREE_TIER1_PATH` if present (15 s wait), then `PAID_TIER1_PATH` if present (15 s wait); a paid-tier claim can surface `PAWN_REWARDS_MODAL`, handled by tapping `PAWN_REWARDS_CONTINUE` ("Later") or falling back to `PAWN_REWARDS_EQUIP`; finally spends up to 20 s draining any other popups via `handle_one_popup` (tests/test_08_season_pass.py:586-671, 1124).
8. `unlock_season_pass(player_id, 30000)` writes `seasonPass.points = 30000` directly to MongoDB, instantly maxing progression instead of grinding matches; sleeps 5 s (tests/test_08_season_pass.py:1135-1145; utils/mongo_helper.py:354-404).
9. `restart_game()`: force-stops and cold-launches the app via ADB (`subprocess` + `config.ADB_PATH`), using `state["device_id"]` (raises if unset); sleeps 10 s at the end (tests/test_08_season_pass.py:75-120, 1151).
10. Reconnects AltTester after the restart: stops the old `unity_driver` (best-effort), calls `connect_altunity(alt_port=13000, app_name="sorry")`, publishes it via `state.set`, sleeps 5 s (tests/test_08_season_pass.py:1168-1180).
11. Checks for and handles the Daily Login popup via `tests/handlers/daily_handler.py`'s `is_present`/`handle` (tests/test_08_season_pass.py:1189-1193).
12. Clears the lobby (`handle_one_popup`, falling back to `run_handlers`) for up to 20 s / 2 consecutive clean passes, then sleeps 2 s (tests/test_08_season_pass.py:1205-1221).
13. Reopens Season Pass via `open_season_pass()` again, sleeps 2 s for the auto-scroll animation, then re-clears any popup on top for up to 10 s (tests/test_08_season_pass.py:1227-1247).
14. `claim_all()`: waits up to 25 s for `CLAIM_ALL_PATH` (raise if missing), ignores `REWARD_SUMMARY_CTA`'s auto-close, taps Claim All, then runs a dynamic loop (priority order Reward Summary → Pawn Rewards → Lootbox-drain) until one full pass finds nothing left, bounded by a 60 s no-progress timeout and a 900 s absolute cap; always calls `_finalize_and_return_home()` afterward regardless of how the loop ended, and always re-enables `REWARD_SUMMARY_CTA` handling in a `finally` block (tests/test_08_season_pass.py:761-953, 1258).
    - `_finalize_and_return_home()`: a follow-up mop-up loop (240 s cap) that clears any leftover Reward Summary / Pawn Rewards / Lootbox screen, then taps `SEASON_PASS_CLOSE` and `HOME_BUTTON` once nothing remains; its `True`/`False` return is not checked by `claim_all` (tests/test_08_season_pass.py:677-754, 947).
15. Belt-and-braces close: if `SEASON_PASS_CLOSE` is still present (5 s wait) it's tapped again; otherwise logged as already closed (tests/test_08_season_pass.py:1266-1280).
16. Clears any home-screen popups for up to 60 s (`handle_one_popup` + `run_handlers`), then confirms `HOME_BUTTON` is visible (10 s wait) — logged either way, no raise if it isn't confirmed (tests/test_08_season_pass.py:1289-1330).
17. Captures the "AFTER" wallet the same way as step 3 (`get_user_wallet` — raises `"❌ Failed to fetch AFTER wallet"` if empty — and `get_wallet_from_data`) (tests/test_08_season_pass.py:1336-1347).
18. Computes and logs BEFORE→AFTER gold/gems deltas for both the DB and Data sources (`"N/A"` if a Data value is `None`); no assertion is made on any value (tests/test_08_season_pass.py:1353-1397).
19. `fresh_launch_and_clear(unity_driver)`: force-stops/cold-launches the app again (via `restart_game()`), reconnects AltTester, and clears the fresh lobby (25 s cap) so the next test starts clean (tests/test_08_season_pass.py:130-164, 1406).
20. Returns `{"name": "Season Pass", "status": "PASS", "duration": <seconds>, "steps": steps, "unity_driver": unity_driver}` (tests/test_08_season_pass.py:1412-1421).
21. Any exception raised anywhere in steps 2-19 is caught by the outer `try/except`, logged via `logging.exception`, appended as a `"FAIL"` step, and returned in the same dict shape with `"status": "FAIL"` (tests/test_08_season_pass.py:1423-1443).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Season Pass lobby icon | `SEASON_PASS_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/SeasonPassLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Season Pass modal close | `SEASON_PASS_CLOSE` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/closeGrp/closeCTA/touchArea` |
| Activate (premium) button | `ACTIVATE_BTN_PATH` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/seasonPassHeader/bonusPassHeader/banner/layout/seasonActivateBtn/activateCTA/TouchArea` |
| Buy button (purchase modal) | `BUY_BTN_PATH` | `/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/Layout/TopPivotContainer/rewardsSection/SorryButtonType-Currency/TouchArea` |
| Free Tier 1 claim | `FREE_TIER1_PATH` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/SeasonTierScollItem_1/freePass/FreeTierRewardItem/claimBtn/SorryButtonType-Text/TouchArea` |
| Paid Tier 1 claim | `PAID_TIER1_PATH` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/SeasonTierScollItem_1/bonusPass/BonusTierRewardItem/claimBtn/SorryButtonType-Text/TouchArea` |
| Claim All button | `CLAIM_ALL_PATH` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/bottomContainer/claimAllSlidingPopup/content/claimAllCTA/TouchArea` |
| Unlock-one-tier button | `UNLOCK_ONE_TIER_BTN` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/lockPivotScrollItem/unlockBtnTooltip/layout/unlockCTA/TouchArea` |
| Unlock confirm (gem spend) | `UNLOCK_CONFIRM_BTN` | `/Canvas/ModalLayer/SeasonPassTierUnlockModal(Clone)/rootMain/buyCTA/TouchArea` |
| Gem price on unlock confirm | `SEASON_PASS_GEM_PRICE` | `/Canvas/ModalLayer/SeasonPassTierUnlockModal(Clone)/rootMain/buyCTA/root/textContainer/priceText` |
| Purchase success OK button | `SEASON_PASS_PURCHASE_OK` | `/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/ButtonLayer/Okay Button/TouchArea` |
| Purchase success modal (root) | `SEASON_PASS_PURCHASE_MODAL` | `/Canvas/ModalLayer/PurchaseNotifModal(Clone)` |
| Home button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Pawn Rewards modal (root) | `PAWN_REWARDS_MODAL` | `/Canvas/ModalLayer/PawnRewardsModal(Clone)` |
| Pawn Rewards "Later" | `PAWN_REWARDS_CONTINUE` | `/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/continueButton/Later_Button/TouchArea` |
| Pawn Rewards "Equip" | `PAWN_REWARDS_EQUIP` | `/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/rewardsSection/rewardContainer/PawnRewardCard(Clone)/root/Equip Button/TouchArea` |
| Reward Summary CTA | `REWARD_SUMMARY_CTA` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea` |
| Lootbox tap-to-continue | `LOOTBOX_CLAIM` | `/Canvas/ModalLayer/LootboxRewardsModal(Clone)/rootMain/scaleAdjuster/root/TapToContinueButton/ctaButton` |
| Purchase modal close (inline literal, ignored globally) | `season_pass_popup` | `/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/closeCTA/touchArea` |
| Purchase price text (inline literal) | *(none — literal string)* | `/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/Layout/TopPivotContainer/rewardsSection/SorryButtonType-Currency/root/textContainer/priceText` |

## Data & DB interactions
- `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`) — reads the `wallet` subdocument from `sorry_users.users` matched on `info.gameCode`; called BEFORE (tests/test_08_season_pass.py:1058) and AFTER (:1336) the claim-all flow. Raises the test if either call returns an empty dict.
- `unlock_season_pass(player_id, 30000)` (`utils/mongo_helper.py:354-404`) — `update_one({"info.gameCode": player_id}, {"$set": {"seasonPass.points": 30000}})`; this is the mechanism that force-completes the pass instead of grinding matches (tests/test_08_season_pass.py:1135-1138). Confirmed: it writes `seasonPass.points`, matching the memory note.
- `get_wallet_from_data(unity_driver)` (utils/helpers.py) — Unity in-memory `UserManager` gold/gems/pips read via AltTester, taken at the same BEFORE/AFTER points as the DB read (tests/test_08_season_pass.py:1069, 1347).
- No UI wallet text (`HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`) is read anywhere in this test — the BEFORE/AFTER comparison here is DB vs. Data only (two-way), unlike test_09's three-way UI/Data/DB comparison.
- All deltas are logged only (tests/test_08_season_pass.py:1353-1397); no assertion is made on gold/gems values.

## Pass / fail criteria
- **PASS**: no exception propagates through the whole flow (open → unlock tier → purchase → claim tier 1 → Mongo unlock → restart → reopen → claim all → wallet read). Returns `{"name": "Season Pass", "status": "PASS", "duration": <seconds>, "steps": steps, "unity_driver": unity_driver}` (tests/test_08_season_pass.py:1412-1421).
- **FAIL**: any exception — Season Pass icon/close not found, unlock/confirm buttons not found, Google Play purchase failing with no fallback success modal, Claim All button not found, or an empty before/after wallet fetch — is caught by the outer `try/except`, logged via `logging.exception`, appended as a `"FAIL"` step, and returned in the same dict shape with `"status": "FAIL"` (tests/test_08_season_pass.py:1423-1443).
- Both branches share the shape `{"name", "status", "duration", "steps", "unity_driver"}`.
- Failures inside `claim_all`'s reward loop or `_finalize_and_return_home` do not necessarily raise — `_finalize_and_return_home`'s `True`/`False` return is discarded by its caller (tests/test_08_season_pass.py:947), so a mop-up that times out or gives up after 4 idle passes does not by itself fail the test; the test only fails later if a subsequent required element (e.g., the final wallet fetch) genuinely can't be found.

## Notes & known flakiness
- `return_to_home(unity_driver)` (tests/test_08_season_pass.py:960-979) is defined but never called anywhere in this file — appears to be dead code.
- `run_type` (from the `test_season_pass(unity_driver, driver, run_type=None)` signature) is never referenced in the function body.
- The app is cold-restarted via ADB twice in a single run: once mid-test to reload after the Mongo season-pass unlock (tests/test_08_season_pass.py:1151), and again at the end via `fresh_launch_and_clear()` (:1406) to hand a clean lobby to the next test — each restart carries its own ~10-25 s of sleeps/reconnect budget.
- `claim_all`'s dynamic reward loop has a 60 s "no progress" timeout and a 900 s (15 min) absolute cap; an in-code comment describes the lootbox-draining behavior as an "EXPERIMENT" to cut clear time by scanning less often (tests/test_08_season_pass.py:890-898). A pass with many stacked lootboxes/pawn rewards can make this one of the slowest tests in the suite.
- Two separate `popup_handler.ignore_popup`/`unignore_popup` pairs are used (around the purchase modal, and around `REWARD_SUMMARY_CTA` during claim-all) specifically so the global auto-popup-closer can't eat a screen before the test's own explicit tap fires — both are wrapped in `try/finally` so they're re-enabled even on failure.
- If an exception occurs before `unity_driver` is reassigned inside `purchase_season_pass`/the restart-reconnect steps, the `"unity_driver"` key in the returned FAIL dict is just the original parameter value, which may already be a dead session — callers shouldn't assume it's alive.
- `purchase_season_pass`'s Appium-recovery check (`driver.current_activity`) and its Google-Play-timeout fallback (checking for `SEASON_PASS_PURCHASE_MODAL` before declaring failure) both exist because UiAutomator2 / the Play Store UI are noted in-code as flaky mid-purchase (tests/test_08_season_pass.py:371-388, 418-449).
