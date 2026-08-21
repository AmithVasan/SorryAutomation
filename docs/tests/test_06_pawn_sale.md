# Legendary Pawn Sale

`tests/test_06_pawn_sale.py` · `test_pawn_sale(unity_driver, driver=None)` · types: `iap, regression, complete`

## Purpose
Drives the Legendary Pawn Sale IAP end to end: opens the lobby widget, buys the offer through the real Google Play purchase sheet, reconnects AltTester afterward, equips the pawn from the success modal, and logs the resulting profile snapshot.

## Preconditions
- A live Appium `driver`. If the caller passes `None`, the function pulls one from `state.get("appium_driver")`; if that is also unavailable it raises `RuntimeError("❌ [PawnSale] No Appium driver available")` immediately (tests/test_06_pawn_sale.py:74-78).
- A device/emulator with a working Google Play test-purchase account — the purchase step drives the real Google Play UI via Appium/UiAutomator2 (`utils/google_play_helper.py`), nothing is mocked.
- No hard precondition on offer availability: if the lobby widget or its Buy button is missing (sale inactive / pawn already owned), the test SKIPs gracefully rather than failing.

## Flow
1. Refresh `driver` from `state` if `None`; raise `RuntimeError` if still unavailable (tests/test_06_pawn_sale.py:74-78).
2. Navigate Home: waits up to 5 s for `HOME_BUTTON` and taps it if found, then `clear_all_popups()` (tests/test_06_pawn_sale.py:83-90).
3. Looks for the lobby widget: waits up to 10 s for `HF_PAWN_ICON`; if not found, falls back to `unity_driver.find_object(By.NAME, "LegendaryPawnLobbyWidget")`. If still not found, logs a warning, records `event_tracker.record("IAP", "Pawn Sale", "SKIP")`, and returns `unity_driver` (tests/test_06_pawn_sale.py:99-115).
4. Taps the icon and sleeps 2 s (tests/test_06_pawn_sale.py:117-119).
5. Waits up to 10 s for `PAWN_SALE_MODAL`; raises `"Pawn Sale modal did not open"` if it never appears (tests/test_06_pawn_sale.py:124-128).
6. Reads the pawn's display name via `fast_text(unity_driver, PAWN_SALE_NAME)` (defaults to `"Unknown"`), used only for logging and for the `event_tracker` name (tests/test_06_pawn_sale.py:133-134; `utils/helpers.py:28-33`).
7. Waits up to 5 s for `PAWN_SALE_BUY`. If absent (pawn presumed already owned / sale unavailable), taps `PAWN_SALE_CLOSE` if present, records `event_tracker.record("IAP", f"Pawn Sale ({pawn_name})", "SKIP")`, and returns `unity_driver` (tests/test_06_pawn_sale.py:139-150).
8. Taps the Buy button and sleeps 3 s while the Google Play sheet opens (tests/test_06_pawn_sale.py:155-157).
9. `handle_google_play_purchase(driver)` drives the Google Play UI (via Appium/UiAutomator2) to locate and tap Buy, then dismiss safe post-purchase confirmation popups; returns `(gp_success, driver)`, where `driver` may be a fresh Appium session if UiAutomator2 crashed mid-purchase (tests/test_06_pawn_sale.py:162; `utils/google_play_helper.py:529-700`).
10. Maps `gp_success` to `"PASS"`/`"FAIL"`, records `event_tracker.record("IAP", f"Pawn Sale ({pawn_name})", status)`, and updates `state.set("appium_driver", driver)` (tests/test_06_pawn_sale.py:164-175).
11. `reconnect_alttester(unity_driver)`: stops the old AltDriver, force-foregrounds the game (restarting the app if a simple foreground doesn't bring the AltTester client back), and reconnects to AltTester Desktop; the refreshed driver is stored via `state.set("unity_driver", unity_driver)` (tests/test_06_pawn_sale.py:181-183; `utils/google_play_helper.py:793-868`).
12. Waits up to 12 s for `PAWN_SALE_SUCCESS_MODAL`. If found, waits up to 5 s for `PAWN_SALE_EQUIP_BTN` and taps it (sleeps 2 s), logging a warning if the Equip button itself is missing. If the success modal never appears at all, logs a warning and continues without equipping (tests/test_06_pawn_sale.py:188-204).
13. Captures a post-purchase profile snapshot via `get_user_snapshot(unity_driver)` — wrapped in its own `try/except` that only logs a warning on failure. This taps `PROFILE_BUTTON`, reads name/country/ID/level/xp/`PROFILE_PAWN` (equipped pawn), closes the profile modal, then re-reads `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`/`HOME_HAMMER_TEXT`, and writes all of it into `state.user_info` (`utils/helpers.py:91-145`). The function then reads back `state.user_info.get("equipped_pawn")` and logs it as "Now equipped" (tests/test_06_pawn_sale.py:209-214).
14. Returns `unity_driver` (tests/test_06_pawn_sale.py:218).

Unlike Piggy Bank, this function has no top-level `try/except`/`finally` around the main flow — steps 2 through 13 run unguarded (the only local `try/except` blocks are the `_wait` helper and the `get_user_snapshot` call in step 13).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Home nav button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Pawn Sale lobby widget | `HF_PAWN_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/LegendaryPawnLobbyWidget/scaleAdjuster/root/Overlay Parent/bg` |
| Lobby widget (By.NAME fallback) | *(inline literal, not in `paths.py`)* | `By.NAME, "LegendaryPawnLobbyWidget"` |
| Sale modal root | `PAWN_SALE_MODAL` | `/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/darkbg` |
| Sale modal close | `PAWN_SALE_CLOSE` | `/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/CrossButton/touchArea` |
| Buy CTA | `PAWN_SALE_BUY` | `/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/CTA/TouchArea` |
| Pawn name label | `PAWN_SALE_NAME` | `/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/nameText/text` |
| Purchase-success modal | `PAWN_SALE_SUCCESS_MODAL` | `/Canvas/ModalLayer/PawnCosmeticSalePurchaseSuccessModal(Clone)/root/PawnRewardCard` |
| Equip button (success modal) | `PAWN_SALE_EQUIP_BTN` | `/Canvas/ModalLayer/PawnCosmeticSalePurchaseSuccessModal(Clone)/root/PawnRewardCard/root/Equip Button/TouchArea` |
| Equipped-pawn label (profile modal, via `get_user_snapshot`) | `PROFILE_PAWN` | `/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/bottomSection/midSection/cohort_parent/Cosmetics-Button/container/InfoSection/CosmeticNameText/text` |

## Data & DB interactions
No MongoDB access (no `mongo_helper` import). Uses `event_tracker.record("IAP", f"Pawn Sale ({pawn_name})", "PASS"|"FAIL"|"SKIP")` to log the purchase outcome into the in-memory, thread-local event tracker that feeds the run report's "IAP" section — separate from the top-level pass/fail (see below). `get_user_snapshot()` writes a single post-purchase snapshot (name, country, ID, level, xp, gold, gems, hammer, equipped pawn) into the thread-local `state.user_info` dict — this is in-memory only, not persisted, and there is **no pre-purchase snapshot taken for comparison**; only the after-purchase equipped-pawn value is logged.

## Pass / fail criteria
This test does **not** return a status dict — it returns the (possibly refreshed) `unity_driver` object directly, and (unlike Piggy Bank) has no top-level exception handling of its own. Per the harness's dispatch loop in `run_this.py`:
- If `test_pawn_sale` returns without raising, `reported_status` defaults to `"PASS"` (a non-dict return only triggers a `unity_driver` refresh — `run_this.py:978, 990-993`) — this includes both internal SKIP paths (widget missing, Buy button missing) and the case where the success modal / Equip button never appeared. All of those are only visible via the separate `event_tracker` "IAP" section, not the top-level result.
- If an exception propagates — the only explicit ones in this file are `"Pawn Sale modal did not open"` (step 5) and the `RuntimeError` when no Appium driver is available (step 1) — the harness's outer `try/except` (`run_this.py:1008-1021`) catches it and marks the test **FAIL**, appending the error text to that run's steps.
- In short: an actual Google Play purchase failure (`gp_success is False`), a missing success modal, or a missing Equip button do **not** by themselves fail the top-level test result; they only surface as `"FAIL"`/a logged warning in the IAP event-tracker section or logs.

## Notes & known flakiness
- Actual source signature is `test_pawn_sale(unity_driver, driver)` — `driver` has no default in code; the function tolerates a `None` argument by pulling it from `state` (see Preconditions). The header above follows this doc set's display convention.
- No `ignore_popup`/`unignore_popup` calls in this file. `PawnCosmeticSaleMainModal` paths do not appear anywhere in `popup_handler.POPUP_PRIORITY`, so — unlike Piggy Bank, which must suppress `PIGGY_BANK_CLOSE` — there is no competing auto-close to guard against here.
- Same Google Play timing caveats as the Piggy Bank test: `handle_google_play_purchase` waits a flat 15 s before its first UI query (to avoid wedging UiAutomator2 on a half-open sheet) and up to 90 s total; `_wait_purchase_complete` requires an 8 s minimum settle plus an 8 s clear-screen grace window, capped at 35 s (`utils/google_play_helper.py:616-630`).
- `reconnect_alttester` can force-restart the whole game (`am force-stop` + relaunch) if simply foregrounding it doesn't restore the AltTester connection.
- `get_user_snapshot` failures are swallowed (logged as a warning only), so the "Now equipped" log line can silently stay stale or fall back to `"Unknown"` if that call fails.
- This is a real Google Play purchase flow; it can only be meaningfully validated on an actual device/emulator with a functioning test-purchase account.
- The module's own docstring header (tests/test_06_pawn_sale.py:1-2) reads `test_07_pawn_sale.py`, but the actual filename is `test_06_pawn_sale.py` — stale comment from prior renumbering, not a functional issue.
