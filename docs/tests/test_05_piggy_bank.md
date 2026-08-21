# Piggy Bank

`tests/test_05_piggy_bank.py` · `test_piggy_bank(unity_driver, driver=None)` · types: `iap, regression, complete`

## Purpose
Drives the Piggy Bank IAP end to end: opens the widget from Home, buys it through the real Google Play purchase sheet, reconnects AltTester afterward, and taps through the claim screen.

## Preconditions
- A live Appium `driver`. If the caller passes `None`, the function pulls one from `state.get("appium_driver")`; if that is also unavailable it raises `RuntimeError("❌ [PiggyBank] No Appium driver available")` immediately (tests/test_05_piggy_bank.py:74-78).
- A device/emulator with a working Google Play test-purchase account — the purchase step drives the real Google Play UI via Appium/UiAutomator2 (`utils/google_play_helper.py`), nothing is mocked.
- No hard precondition on purchase state: if the Piggy Bank icon or its Buy button is missing (e.g. already purchased), the test SKIPs gracefully rather than failing.

## Flow
1. Refresh `driver` from `state` if `None`; raise `RuntimeError` if still unavailable (tests/test_05_piggy_bank.py:74-78).
2. `popup_handler.ignore_popup(PIGGY_BANK_CLOSE)` — suppresses the global `POPUP_PRIORITY` auto-close for the Piggy Bank close button (it's registered there under HIGH priority) for the entire test, so nothing auto-dismisses the modal mid-flow. Guaranteed to be reversed in the `finally` block on every exit path (tests/test_05_piggy_bank.py:88, 222-229).
3. Navigate Home: waits up to 5 s for `HOME_BUTTON` and taps it if found, then `clear_all_popups()` (tests/test_05_piggy_bank.py:94-101).
4. Taps the Piggy Bank icon: waits up to 10 s for `PIGGY_BANK_ICON`; if not found, falls back to `unity_driver.find_object(By.NAME, "PiggyBankWidget")`. If still not found, logs a warning, records `event_tracker.record("IAP", "Piggy Bank", "SKIP")`, and returns `unity_driver` right away — the `finally` block still runs (tests/test_05_piggy_bank.py:110-126). Otherwise taps it and sleeps 2 s (tests/test_05_piggy_bank.py:128-130).
5. Waits up to 10 s for `PIGGY_BANK_MODAL`; raises `"Piggy Bank modal did not open"` if it never appears (tests/test_05_piggy_bank.py:135-139).
6. Waits up to 5 s for `PIGGY_BANK_BUY`. If absent (bank presumed already purchased/unavailable), taps `PIGGY_BANK_CLOSE` if present, records `event_tracker.record("IAP", "Piggy Bank", "SKIP")`, and returns `unity_driver` (tests/test_05_piggy_bank.py:144-156).
7. Taps the Buy button and sleeps 3 s while the Google Play sheet opens (tests/test_05_piggy_bank.py:161-163).
8. `handle_google_play_purchase(driver)` drives the Google Play UI (via Appium/UiAutomator2 — an OS-level `uiautomator dump` returns nothing on this sheet) to locate and tap Buy, then dismiss safe post-purchase confirmation popups; returns `(gp_success, driver)`, where `driver` may be a fresh Appium session if UiAutomator2 crashed mid-purchase (tests/test_05_piggy_bank.py:168; `utils/google_play_helper.py:529-700`).
9. Maps `gp_success` to `"PASS"`/`"FAIL"`, records `event_tracker.record("IAP", "Piggy Bank", status)`, and updates `state.set("appium_driver", driver)` (tests/test_05_piggy_bank.py:170-181).
10. `reconnect_alttester(unity_driver)`: stops the old AltDriver, force-foregrounds the game (restarting the app if a simple foreground doesn't bring the AltTester client back), and reconnects to AltTester Desktop; the refreshed driver is stored via `state.set("unity_driver", unity_driver)` (tests/test_05_piggy_bank.py:183-189; `utils/google_play_helper.py:793-868`).
11. Waits up to 15 s for `PIGGY_BANK_CLAIM_SCREEN`; taps it and sleeps 2 s for the claim animation. Logs a warning but continues if it never appears (tests/test_05_piggy_bank.py:194-203).
12. If `PIGGY_BANK_MODAL` reappears (checked with a 5 s wait), taps `PIGGY_BANK_CLOSE` (5 s wait) and sleeps 1 s; otherwise logs that nothing needed closing (tests/test_05_piggy_bank.py:208-218).
13. `finally`: `popup_handler.unignore_popup(PIGGY_BANK_CLOSE)` re-enables the global auto-close — runs on normal completion, an early SKIP `return`, or any exception (tests/test_05_piggy_bank.py:222-229).
14. Returns `unity_driver` (possibly the refreshed one from step 10) (tests/test_05_piggy_bank.py:231).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Home nav button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Piggy Bank lobby icon | `PIGGY_BANK_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/PiggyBankWidget` |
| Piggy Bank icon (By.NAME fallback) | *(inline literal, not in `paths.py`)* | `By.NAME, "PiggyBankWidget"` |
| Piggy Bank modal root | `PIGGY_BANK_MODAL` | `/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain` |
| Buy / claim CTA | `PIGGY_BANK_BUY` | `/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/content/ClaimButton/TouchArea` |
| Modal close button | `PIGGY_BANK_CLOSE` | `/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/header/Close Button/touchArea` |
| Post-purchase claim screen | `PIGGY_BANK_CLAIM_SCREEN` | `/Canvas/ModalLayer/PiggyClaimModal(Clone)/darkBG` |

## Data & DB interactions
No MongoDB access (no `mongo_helper` import). Uses `event_tracker.record("IAP", "Piggy Bank", "PASS"|"FAIL"|"SKIP")` to log the purchase outcome into the in-memory, thread-local event tracker that feeds the run report's "IAP" section — this is a reporting side-channel, not persisted storage, and it is separate from the value the harness uses for top-level pass/fail (see below). Also uses `state.set("appium_driver", ...)` / `state.set("unity_driver", ...)` to persist refreshed driver handles in the thread-local `StateManager` for later tests in the same run.

## Pass / fail criteria
This test does **not** return a status dict — it returns the (possibly refreshed) `unity_driver` object directly. Per the harness's dispatch loop in `run_this.py`:
- If `test_piggy_bank` returns without raising, `reported_status` defaults to `"PASS"` (a non-dict return only triggers a `unity_driver` refresh — `run_this.py:978, 990-993`) — this includes the two internal SKIP paths (icon missing, Buy button missing), which are only visible via the separate `event_tracker` "IAP" section, not the top-level result.
- If an exception propagates — the only explicit one in this file is `"Piggy Bank modal did not open"` (step 5), plus the `RuntimeError` if no Appium driver is available — the harness's outer `try/except` (`run_this.py:1008-1021`) catches it and marks the test **FAIL**, appending the error text to that run's steps.
- In short: an actual Google Play purchase failure (`gp_success is False`) by itself does **not** fail the top-level test result; it only shows up as `"FAIL"` in the IAP event-tracker section.

## Notes & known flakiness
- Actual source signature is `test_piggy_bank(unity_driver, driver)` — `driver` has no default in code; the function tolerates a `None` argument by pulling it from `state` (see Preconditions). The header above follows this doc set's display convention.
- Google Play timing: `handle_google_play_purchase` waits up to 90 s total and, per an in-code comment, deliberately waits a flat 15 s before its first UI query — querying the sheet while it's still opening can wedge UiAutomator2 for the whole timeout (`utils/google_play_helper.py:616-630`). After Buy is tapped, `_wait_purchase_complete` requires an 8 s minimum settle plus an 8 s clear-screen grace window, capped at 35 s.
- `reconnect_alttester` can force-restart the whole game (`am force-stop` + relaunch) if simply foregrounding it doesn't restore the AltTester connection — a visible app restart, not just a background reconnect.
- This is a real Google Play purchase flow; it can only be meaningfully validated on an actual device/emulator with a functioning test-purchase account.
- The "Buy button absent ⇒ already purchased" branch is an assumption baked into the log message — the code does not independently verify ownership, it only infers it from the CTA's absence.
- The module's own docstring header (tests/test_05_piggy_bank.py:1-2) reads `test_06_piggy_bank.py`, but the actual filename is `test_05_piggy_bank.py` — stale comment from prior renumbering, not a functional issue.
