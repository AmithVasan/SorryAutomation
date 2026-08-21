# Gamemode — Classic

`tests/test_09_classicmode.py` · `test_gameplay(unity_driver, driver)` · types: `smoke, complete`

## Purpose
Plays one full Classic-mode match end to end: opens the bet screen, confirms/selects the Classic tab, adjusts the bet, starts matchmaking, exercises in-game emoji and text chat, draws and redraws a card, exercises the opponent-profile flow (add friend / block / confirm / unblock / close), quits via the burger menu, and logs a three-way (UI / Data / DB) wallet comparison before and after.

## Preconditions
- Active `unity_driver` (AltTester) session. `driver` (Appium) is accepted as a parameter but never referenced in the function body.
- Tolerant Home navigation: waits up to 5 s for `HOME_BUTTON` and taps it if present, but does not raise if it's missing — the test assumes it's already reasonably close to the lobby (tests/test_09_classicmode.py:138-141).
- `state.get("device_id")` should be set for the ADB-driven text-chat step (`_adb`), though `_adb` itself swallows failures silently (tests/test_09_classicmode.py:88-96).
- `state.user_info.get("player_id")` is optional — if absent, the DB wallet reads are simply skipped in favor of `{}` rather than raising (tests/test_09_classicmode.py:151, 432).
- Needs live matchmaking to actually find an opponent within the 60 s poll window for the rest of the match (chat, draw, opponent profile) to have anything to act on.

## Flow
1. Log start; read `device_id` and `player_id` from `state` (tests/test_09_classicmode.py:129-132).
2. Navigate Home: wait up to 5 s for `HOME_BUTTON`, tap if found, sleep 1 s, then `clear_all_popups(unity_driver)` — the only popup-clearing call in the entire test (tests/test_09_classicmode.py:137-143).
3. Wallet BEFORE: `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT` via `fast_text` + `parse_amount` (UI), `get_wallet_from_data(unity_driver)` (Data), `get_user_wallet(player_id)` if `player_id` else `{}` (DB); logged via `_log_wallet_comparison("BEFORE", ...)` (tests/test_09_classicmode.py:148-152).
4. Tap `GAME_PLAY_BUTTON` — the only wait in this test that uses the popup-aware `wait_for_safe` rather than the local `_wait`; 10 s wait, raises `"❌ [Gameplay] Play button not found"` if missing; sleep 2 s (tests/test_09_classicmode.py:157-162).
5. Select the Classic tab: 5 s wait for `GAME_BET_CLASSIC_TAB` (`inactiveTab`, only present when Classic isn't already selected); tap if present, otherwise log that it's already active (tests/test_09_classicmode.py:169-176).
6. Log `GAME_BET_MODE` and `GAME_BET_AMOUNT` text (tests/test_09_classicmode.py:181-183).
7. Navigate bet: tap `GAME_BET_PREV` twice (0.5 s pause each, warns per-tap if missing), then `GAME_BET_NEXT` once (tests/test_09_classicmode.py:188-203).
8. Log `GAME_BET_PLAY_TEXT` — despite the in-code comment ("same path as Next"), this constant is actually byte-identical to `GAME_BET_AMOUNT`, not `GAME_BET_NEXT` (tests/test_09_classicmode.py:206-209; utils/paths.py:658,661).
9. Tap `GAME_BET_PLAY_BTN` (8 s wait, raises `"❌ [Gameplay] Bet screen Play button not found"` if missing); logs "Game starting"; sleep 2 s (tests/test_09_classicmode.py:213-219).
10. Poll every 2 s up to 60 s for `MATCHMAKING_SCREEN` to disappear; only warns (doesn't raise) if it's still visible after the full window (tests/test_09_classicmode.py:224-232).
11. Sleep 2 s for FTUE/transition animations (tests/test_09_classicmode.py:237).
12. Log `GAME_INGAME_GEM` text (tests/test_09_classicmode.py:242-243).
13. Emoji chat: tap `GAME_EMOJI_BTN` → `GAME_QUICK_CHAT` → re-tap `GAME_EMOJI_BTN` → `GAME_EMOJI_SEND`; the whole block is skipped (warn only) if the first `GAME_EMOJI_BTN` wait fails, and each subsequent sub-step warns independently if missing (tests/test_09_classicmode.py:248-278).
14. Text chat: tap `GAME_CHAT_MSG_BTN` → `GAME_CHAT_INPUT` → ADB `input text "Sorry!%sAutomation%sClassic%sMode"` → ADB `input keyevent 66` (Enter; chat auto-closes on send) (tests/test_09_classicmode.py:283-309).
15. Draw card: 15 s wait for `GAME_CARD_DRAW`, tap if found, else warn (tests/test_09_classicmode.py:314-321).
16. Redraw window: log `GAME_REDRAW_GEM` cost text, then a 4 s wait for `GAME_REDRAW_BTN` — tap if it appears in time, else warn "window may have passed" (tests/test_09_classicmode.py:326-336).
17. `event_tracker.record("Gameplay", "Classic Match", "PASS")` — recorded unconditionally at this point regardless of any warnings logged so far (tests/test_09_classicmode.py:338).
18. Opponent profile flow: tap `GAME_OPP_PROFILE_BTN` (8 s wait; whole block skipped with a warning if missing) → Add Friend → Block → Block Confirm → Unblock → Close, each sub-step independently guarded and warning-only if its element isn't found (tests/test_09_classicmode.py:344-398).
19. Quit: tap `GAME_BURGER_MENU` (10 s wait, raises if missing) → `GAME_QUIT_ICON` (5 s wait, raises if missing) → `GAME_QUIT_CONFIRM` (5 s wait, raises if missing); sleep 3 s after confirming (tests/test_09_classicmode.py:403-424).
20. Wallet AFTER: same three-way read as step 3, logged via `_log_wallet_comparison("AFTER", ...)` (tests/test_09_classicmode.py:429-433).
21. Log the UI/Data/DB gold and gems deltas via `_safe_delta` (`"N/A"` if either side is `None`); no assertion is made (tests/test_09_classicmode.py:435-445).
22. Log "DONE" and `return unity_driver` (tests/test_09_classicmode.py:447-448).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Home button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Home gold counter (UI) | `HOME_GOLD_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text` |
| Home gems counter (UI) | `HOME_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text` |
| Matchmaking overlay | `MATCHMAKING_SCREEN` | `/TransitionCanvas/matchmakingScreen_new(Clone)/root/bgGrp/bg` |
| Lobby Play button | `GAME_PLAY_BUTTON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/playCTA/rootMain/playCTA/TouchArea` |
| Classic mode tab (inactive) | `GAME_BET_CLASSIC_TAB` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/NormalBetscreenModesTab/inactiveTab` |
| Active mode label text | `GAME_BET_MODE` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/NormalBetscreenModesTab/activeTab/gridLayout/text/TextStyle_Amount_T1_large/text` |
| Bet amount text | `GAME_BET_AMOUNT` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/play_button/root/currencyText/text01` |
| Bet Prev button | `GAME_BET_PREV` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/prev_button/touchArea` |
| Bet Next button | `GAME_BET_NEXT` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/next_button/touchArea` |
| Play-bet text (= `GAME_BET_AMOUNT`) | `GAME_BET_PLAY_TEXT` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/play_button/root/currencyText/text01` |
| Play button (bet screen) | `GAME_BET_PLAY_BTN` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/play_button/TouchArea` |
| In-game gem count | `GAME_INGAME_GEM` | `/Canvas/hudLayer/commonHUD/root/Container/gemBar/text` |
| Emoji chat open | `GAME_EMOJI_BTN` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc/touchArea` |
| Quick chat button | `GAME_QUICK_CHAT` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/chatMsgs/container_top/msgButton/bg` |
| Emoji send button | `GAME_EMOJI_SEND` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/emojiContainer/emojiButton_5/emoji` |
| Text chat open | `GAME_CHAT_MSG_BTN` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc_1/touchArea` |
| Chat text input field | `GAME_CHAT_INPUT` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/TextBar/textArea/textViewport/PlaceHolderText` |
| Card draw button | `GAME_CARD_DRAW` | `/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02` |
| Redraw button | `GAME_REDRAW_BTN` | `/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/iconContent/root/arrowParent/arrow` |
| Redraw gem-cost text | `GAME_REDRAW_GEM` | `/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/redraw /text` |
| Burger menu | `GAME_BURGER_MENU` | `/Canvas/hudLayer/settings/grp/leftGrp/burgerMenu/touchArea` |
| Quit icon (in burger menu) | `GAME_QUIT_ICON` | `/Canvas/hudLayer/settings/grp/leftGrp/menuOptions/quit/touchArea` |
| Quit confirm | `GAME_QUIT_CONFIRM` | `/Canvas/ModalLayer/QuitGamePopup(Clone)/rootMain/CTA_Red/TouchArea` |
| Opponent profile button | `GAME_OPP_PROFILE_BTN` | `/Canvas/GameplayLayer/2pGameplayLayer/PlayerContainer/opponentProfileHolder /root/ProfileButton` |
| Add friend (opponent profile) | `GAME_OPP_ADD_FRIEND` | `/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/contentMask/Content/topSection/section-Name/addFriendCTA/touchArea` |
| Block button | `GAME_OPP_BLOCK_BTN` | `/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/BlockBtn/TouchArea` |
| Block confirm | `GAME_OPP_BLOCK_CONFIRM` | `/Canvas/ModalLayer/SorryCommonModal(Clone)/rootMain/layout/CTA_Red/TouchArea` |
| Unblock button | `GAME_OPP_UNBLOCK_BTN` | `/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/UnBlockBtn/TouchArea` |
| Close opponent profile | `GAME_OPP_PROFILE_CLOSE` | `/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/closeCTA/touchArea` |

## Data & DB interactions
- `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`) — reads the `wallet` subdocument from `sorry_users.users` matched on `info.gameCode`; called BEFORE (tests/test_09_classicmode.py:151) and AFTER (:432), but only `if player_id` — otherwise the DB side is silently skipped (`{}`) rather than raised.
- No Mongo writes occur in this test.
- `get_wallet_from_data(unity_driver)` (utils/helpers.py) — Unity in-memory `UserManager` gold/gems read, the same helper used by the other wallet-comparison tests in this suite.
- `fast_text` + `parse_amount` — UI wallet text (`HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`) parsed to numbers.
- All three sources are logged for comparison only (`_log_wallet_comparison`, `_safe_delta`, tests/test_09_classicmode.py:99-118) — no assertion is made on any wallet value.
- `event_tracker.record("Gameplay", "Classic Match", "PASS")` (utils/event_tracker.py) is the only non-Mongo persisted signal in this test; its internals weren't inspected here.

## Pass / fail criteria
- The function returns only `unity_driver` on success — **not** a `{"status": ...}` dict like `test_lucky_cards`/`test_season_pass`. There is no top-level `try/except` and no `steps` list.
- **PASS** (informal): the function runs to completion and returns `unity_driver`.
- **FAIL** (informal): an uncaught exception propagates from one of exactly five hard checks — `GAME_PLAY_BUTTON` not found (:160), `GAME_BET_PLAY_BTN` not found (:216), `GAME_BURGER_MENU` not found (:406), `GAME_QUIT_ICON` not found (:413), or `GAME_QUIT_CONFIRM` not found (:420). Any caller/harness must catch these itself to record a FAIL — nothing in this file builds that record.
- Every other missing element (Classic tab, chat buttons, draw/redraw, opponent profile, matchmaking timeout) only logs a warning and lets the test continue.

## Notes & known flakiness
- The file's own module docstring header reads `test_09_gameplay.py` (and the in-body log markers say `"── test_09_gameplay START/DONE ──"`), but the actual file is `tests/test_09_classicmode.py` — a naming drift between the docstring/logs and the real filename (tests/test_09_classicmode.py:1-4, 129, 447).
- `driver` (the Appium session) is accepted as a parameter but is never used anywhere in the function body.
- Only the very first wait (`GAME_PLAY_BUTTON`, via `wait_for_safe`) is popup-aware; every other wait in the test uses the local `_wait()` helper (a plain `wait_for_object` in a try/except, tests/test_09_classicmode.py:81-85), so an unexpected popup appearing later in the match is not auto-dismissed by this test the way test_08/test_04 do throughout.
- `GAME_BET_AMOUNT` and `GAME_BET_PLAY_TEXT` (utils/paths.py:658, 661) are the exact same AltTester path — logging both (bet screen text in step 6, "play-bet text" in step 8) reads the same node twice.
- No top-level `try/except`: an exception anywhere from matchmaking onward could leave the app mid-match (e.g., burger menu found but quit-confirm missing) with no cleanup attempted by this function.
- The Prev×2/Next×1 bet navigation doesn't verify the resulting bet value against an expectation — it only logs whatever `GAME_BET_PLAY_TEXT` shows afterward, so a bet screen that started at its minimum (where Prev is a no-op) would silently produce a different effective bet than one that started elsewhere.
- The 60 s matchmaking wait does not fail the test on timeout — it just proceeds, so a stuck matchmaker manifests as a later, less obvious failure (e.g., draw button not found) rather than a clear "matchmaking timed out" error.
