# Guest Login

`tests/test_01_guest_login.py` · `test_guest_login(unity_driver, driver)` · types: `smoke, regression, bat, complete`

## Purpose
Signs a fresh account in as a guest, walks the entire new-user FTUE (onboarding) sequence to reach a stable lobby, then — if the account is below level 50 — boosts it in MongoDB and restarts the game so subsequent tests run against a levelled-up profile. This is the entry test that leaves the app at Home for the rest of the suite.

## Preconditions
- An `unity_driver` (AltTester) session already connected, and a live Appium `driver` (this test uses both). AltTester traffic reaches the licensed Desktop via `adb reverse tcp:13000` (see `restart_and_reconnect`, tests/test_01_guest_login.py:88-121).
- The app is either at the guest login screen **or** already logged in — the test handles both (tests/test_01_guest_login.py:387-436).
- MongoDB reachable via `MONGO_URI` (used only when a level boost is needed).

## Flow
1. Look for the login screen: `wait_for_safe(LOGIN_SCREEN, 5)`. If absent, log "Already logged in" and skip straight to Reach Home (tests/test_01_guest_login.py:388-436, else-branch at 489).
2. If present, tap Guest: `wait_for_safe(GUEST_BUTTON, 5)` → `guest.tap()` (raises `"Guest button not found"` if missing) (tests/test_01_guest_login.py:397-409).
3. Android permissions: call `permissions_handler.handle(...)` in a loop up to 5×, 2 s apart, until it reports nothing handled (tests/test_01_guest_login.py:411-430).
4. **Loading gate → intro skip** (tests/test_01_guest_login.py:432-448):
   - `wait_for_login_loading_complete(unity_driver)` — polls `LOGIN_SCREEN` (which hosts the loading bar) until it disappears, up to 90 s, before any FTUE search. This decouples slow load time from the skip-button search timeout (tests/test_01_guest_login.py:65-86).
   - `wait_for_safe(FTUE_INTRO_SKIP, 15)` → `safe_tap` + `event_tracker.record("FTUE","New User FTUE","PASS")`; if not found, log a warning and continue.
5. `handle_new_ftue_flow(unity_driver, driver)` — the guided walkthrough (tests/test_01_guest_login.py:188-378):
   - Defensive `wait_for_login_loading_complete` again before the transition/skip search (tests/test_01_guest_login.py:194).
   - **STEP 1** — settle 3 s, then `wait_for_safe(FTUE_SKIP_BUTTON, 10)` → `safe_tap`; records `"Ingame FTUE"` PASS/FAIL (tests/test_01_guest_login.py:197-213).
   - **STEP 2** — wait for `MATCHMAKING_SCREEN` to appear (≤15 s) then disappear (≤30 s) (tests/test_01_guest_login.py:215-236).
   - **STEP 3** — `CARD_DRAW_BUTTON` (≤10 s) → `safe_tap` (tests/test_01_guest_login.py:238-248).
   - **STEP 4** — `INGAME_BURGER_MENU` → `INGAME_HUD_QUIT` → `QUIT_CONFIRM` (tests/test_01_guest_login.py:250-278).
   - **STEP 5** — `BUILD_ACTIVE_CARD` → dismiss `BUILD_INFO_SCREEN` via `_tap_screen_center()` (raw adb tap, looped until gone ≤8 s) → `NEXT_BUILD_CARD` → `BUILD_CLOSE` (tests/test_01_guest_login.py:280-324).
   - **STEP 6** — `BET_PLAY_BUTTON` → dismiss FTUE overlay via `_tap_screen_center()` → `BET_CLOSE` (tests/test_01_guest_login.py:326-350).
   - **STEP 7** — if `daily_login_present`, run `daily_login_handle` (tests/test_01_guest_login.py:352-362).
   - **STEP 8** — if `PIGGY_BANK_INFO` present, dismiss via `_tap_screen_center()` (tests/test_01_guest_login.py:364-374).
6. `reach_home(unity_driver, driver)` — a ≤120 s loop that runs the daily-login / album-FTUE / beach-buddies handlers (high priority), then a generic `handle_one_popup`, then taps `HOME_BUTTON`; returns the (possibly updated) drivers. Raises `"Failed to reach home"` on timeout (tests/test_01_guest_login.py:125-179, 492).
7. `get_user_snapshot(unity_driver)` populates `state.user_info`; read `player_id` and `level` (raises `"Player ID missing"` if absent) (tests/test_01_guest_login.py:498-509).
8. **Conditional boost + restart** (tests/test_01_guest_login.py:512-523): if `level >= 50`, skip. Otherwise `boost_player_level(player_id)` (MongoDB) then `restart_and_reconnect(driver, unity_driver)` — force-stop, relaunch, and reconnect a fresh `AltDriver` (up to 10 attempts; raises `"AltTester reconnect failed"` if all fail).
9. After restart, re-check daily login (`sleep 5` → `daily_login_present` → handle), then `reach_home` again (tests/test_01_guest_login.py:527-536).
10. If a boost happened, take a final `get_user_snapshot` for validation, then `return unity_driver` (tests/test_01_guest_login.py:539-546).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Guest login screen (holds loading bar) | `LOGIN_SCREEN` | `/Canvas/midUiLayer/loginScreen` |
| Guest sign-in button | `GUEST_BUTTON` | `/Canvas/midUiLayer/loginScreen/buttonsParent/guestCTA/TouchArea` |
| FTUE intro cinematic skip | `FTUE_INTRO_SKIP` | `/Canvas/ModalLayer/FTUEIntroCinematic/root/skipButton/TouchArea` |
| In-game FTUE skip | `FTUE_SKIP_BUTTON` | `/Canvas/FTUE-InGame/container/scaleAdjuster/skipButton/TouchArea` |
| Matchmaking screen | `MATCHMAKING_SCREEN` | `/TransitionCanvas/matchmakingScreen_new(Clone)/root/bgGrp/bg` |
| Card draw (withdraw) | `CARD_DRAW_BUTTON` | `/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02` |
| In-game burger menu | `INGAME_BURGER_MENU` | `/Canvas/hudLayer/settings/grp/leftGrp/burgerMenu/touchArea` |
| Quit option | `INGAME_HUD_QUIT` | `/Canvas/hudLayer/settings/grp/leftGrp/menuOptions/quit/touchArea` |
| Quit confirm | `QUIT_CONFIRM` | `/Canvas/ModalLayer/QuitGamePopup(Clone)/rootMain/CTA_Red/TouchArea` |
| Build active card | `BUILD_ACTIVE_CARD` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/.../buildCardParent/card/activeCard` |
| Build info ("tap anywhere") | `BUILD_INFO_SCREEN` | `/Canvas/ModalLayer/BuildFtueInfoModal(Clone)/bg` |
| Bet play button | `BET_PLAY_BUTTON` | `/Canvas/uiLayer/TableManager/.../HomeScreen/buttonsGrp/root/Buttons/playCTA/rootMain/playCTA/TouchArea` |
| Bet screen close | `BET_CLOSE` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/header/cross_button/touchArea` |
| Piggy Bank info ("tap anywhere") | `PIGGY_BANK_INFO` | `/Canvas/ModalLayer/PiggyBankInfoModal(Clone)/bg` |
| Home button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |

## Data & DB interactions
- **MongoDB write (conditional):** `boost_player_level(player_id)` (`utils/mongo_helper.py`) sets `pipPrgrsn.lvl = 50`, `info.name = "NOOB"`, and `wallet.gold/gems/pips = 5000/1050/3000` — only when the snapshot level is `< 50` (tests/test_01_guest_login.py:517-521).
- **Snapshots:** `get_user_snapshot(unity_driver)` reads the player profile (player_id, level) into `state.user_info` before the boost decision and again after restart when a boost occurred.

## Pass / fail criteria
- **PASS:** the function returns normally, yielding `unity_driver` (the possibly-reconnected AltTester driver). Unlike the feature tests, this test does **not** return a `{status: ...}` dict — the harness treats a clean return as PASS.
- **FAIL:** any raised exception — `"Guest button not found"`, `"Failed to reach home"`, `"Player ID missing"`, or `"AltTester reconnect failed"`.
- Returning `unity_driver` matters: after `restart_and_reconnect` the old driver is dead, so the caller must adopt the new one this test hands back.

## Notes & known flakiness
- **Loading gate (recent):** `wait_for_login_loading_complete` was added so a slow load no longer races the FTUE skip search — it waits for `LOGIN_SCREEN`/loading bar to clear (≤90 s) before searching, at both the intro-skip site and the top of `handle_new_ftue_flow`. It is fail-safe: on timeout it logs a warning and proceeds, so it can only help a slow load, never hard-fail.
- **Best-effort FTUE:** most FTUE steps only warn-and-continue if an element is missing (the walkthrough is intentionally resilient); the hard requirements are the guest button, reaching home, a player id, and (when boosting) the reconnect.
- **"Tap anywhere" screens** (`BUILD_INFO_SCREEN`, the bet FTUE overlay, `PIGGY_BANK_INFO`) are dismissed with a raw adb tap at (540, 1200) via `_tap_screen_center()`, because tapping the specific element path does not register on those screens.
- The **old (non-FTUE) login flow is disabled** — a commented block at the end of the file; "new FTUE flow always active."
- The restart path only runs for sub-level-50 accounts; a returning/boosted account short-circuits it, so a full FTUE walkthrough is only exercised on a genuinely new guest account.
