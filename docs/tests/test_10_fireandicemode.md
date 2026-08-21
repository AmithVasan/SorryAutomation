# Gamemode — Fire & Ice

`tests/test_10_fire&icemode.py` · `test_fire_and_ice(unity_driver, driver)` · types: `smoke, complete`

## Purpose
Plays one full Fire & Ice match end-to-end — selecting the mode on the bet screen, starting the match, exercising card draw/redraw and in-game chat (emoji + ADB-typed text), then quitting via the burger menu. Logs the Gold/Gems wallet from UI, Data, and DB sources both before and after the match.

## Preconditions
- A resolvable `state.user_info["player_id"]` is needed for the DB wallet reads; if absent, `get_user_wallet` is simply skipped (returns `{}}`), not a hard failure (`tests/test_10_fire&icemode.py:149`).
- `state.get("device_id")` should be set for the ADB text-chat step; if unset it falls back to the literal string `"Unknown"` (`tests/test_10_fire&icemode.py:129`), which would make `adb -s Unknown shell ...` fail — silently, since `_adb()` swallows all exceptions.
- No Mongo boost/ammo top-up is performed by this test — it plays with whatever Gold/Gems the account already has.

## Flow
1. Navigate to Home (tap `HOME_BUTTON` if found) and clear any open popups via `clear_all_popups` — `tests/test_10_fire&icemode.py:135-141`.
2. Log wallet BEFORE: Gold/Gems from UI (`HOME_GOLD_TEXT`/`HOME_GEMS_TEXT` via `fast_text` + `parse_amount`), Data (`get_wallet_from_data`), DB (`get_user_wallet`) — `tests/test_10_fire&icemode.py:146-150`.
3. Tap `GAME_PLAY_BUTTON` via `wait_for_safe` (10 s) to open the bet screen; raises `Exception` if not found — `tests/test_10_fire&icemode.py:155-160`.
4. Tap the Fire & Ice tab (`GAME_BET_FIREICE_TAB`, 8 s wait); raises if not found — `tests/test_10_fire&icemode.py:165-171`.
5. Log the currently-selected bet amount (`GAME_BET_AMOUNT`) — `tests/test_10_fire&icemode.py:176-177`.
6. Step the bet selector: tap `GAME_BET_PREV` twice, then `GAME_BET_NEXT` once — each is non-fatal (logs a warning) if not found — `tests/test_10_fire&icemode.py:182-197`.
7. Log the resulting play-bet text (`GAME_BET_PLAY_TEXT`) — `tests/test_10_fire&icemode.py:202-203`.
8. Tap `GAME_BET_PLAY_BTN` to start the match; raises if not found — `tests/test_10_fire&icemode.py:208-213`.
9. Wait (8 s) for a rules screen (`GAME_FIREICE_RULES_SCREEN`) and dismiss it via its CTA (`GAME_FIREICE_RULES_CTA`) — logged as "Fire Rules" — `tests/test_10_fire&icemode.py:218-229`.
10. Wait (8 s) on the **same** screen/CTA constants a second time and dismiss again — logged as "Ice Rules". The code cannot actually distinguish the two screens; it assumes Fire appears first and Ice second — `tests/test_10_fire&icemode.py:234-245`.
11. Poll up to 8× (2 s object-wait + 2 s sleep per iteration, ~16 s worst case) for `MATCHMAKING_SCREEN` to disappear; logs a warning and proceeds anyway if it never clears — `tests/test_10_fire&icemode.py:250-258`.
12. Sleep 2 s for FTUE/transition animations, then log the in-game gem count (`GAME_INGAME_GEM`) — `tests/test_10_fire&icemode.py:263-269`.
13. Tap `GAME_FIREICE_CARD_DRAW` (15 s wait) to draw a card — warns but does not raise if missing — `tests/test_10_fire&icemode.py:274-281`.
14. Log the redraw gem cost (`GAME_FIREICE_REDRAW_GEM`), then wait 4 s for `GAME_FIREICE_REDRAW_BTN` and tap it if present (docstring calls this a "3-second window", the code's actual wait timeout is 4 s) — `tests/test_10_fire&icemode.py:286-296`.
15. Chat flow:
    - **Emoji**: tap `GAME_EMOJI_BTN` → tap `GAME_QUICK_CHAT` → re-tap `GAME_EMOJI_BTN` → tap `GAME_EMOJI_SEND` — `tests/test_10_fire&icemode.py:301-331`.
    - **Text**: tap `GAME_CHAT_MSG_BTN` → tap `GAME_CHAT_INPUT` → send the literal ADB text `Sorry!%sAutomation%sFire%s\&%sIce%sMode` (`%s` → space, `\&` → shell-escaped `&`) via `adb shell input text`, then `adb shell input keyevent 66` (Enter); the chat panel is expected to auto-close on send — `tests/test_10_fire&icemode.py:336-362`.
16. Record `event_tracker.record("Gameplay", "Fire & Ice Match", "PASS")` unconditionally at this point, regardless of whether the preceding draw/redraw/chat steps actually succeeded — `tests/test_10_fire&icemode.py:364`.
17. Quit: tap `GAME_BURGER_MENU` → tap `GAME_QUIT_ICON` → tap `GAME_QUIT_CONFIRM`; each step raises `Exception` if its element is not found — `tests/test_10_fire&icemode.py:369-390`.
18. Log wallet AFTER (same 3 sources) and log the UI/Data/DB delta for Gold and Gems, then return `unity_driver` — `tests/test_10_fire&icemode.py:395-414`.

## Key element paths
| Purpose | Constant | Path |
|---|---|---|
| Home nav button | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Wallet HUD (Gold / Gems) | `HOME_GOLD_TEXT`<br>`HOME_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text`<br>`/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text` |
| Lobby Play button | `GAME_PLAY_BUTTON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/playCTA/rootMain/playCTA/TouchArea` |
| Fire & Ice mode tab | `GAME_BET_FIREICE_TAB` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/Fire&IceBetscreenModesTab_2/inactiveTab` |
| Bet Prev / Next | `GAME_BET_PREV`<br>`GAME_BET_NEXT` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/prev_button/touchArea`<br>`/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/next_button/touchArea` |
| Bet screen Play | `GAME_BET_PLAY_BTN` | `/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/play_button/TouchArea` |
| Fire/Ice rules screen + CTA | `GAME_FIREICE_RULES_SCREEN`<br>`GAME_FIREICE_RULES_CTA` | `/Canvas/ModalLayer/FireAndIceInfoModal(Clone)/darkbg`<br>`/Canvas/ModalLayer/FireAndIceInfoModal(Clone)/rootMain/CTA/TouchArea` |
| Matchmaking overlay | `MATCHMAKING_SCREEN` | `/TransitionCanvas/matchmakingScreen_new(Clone)/root/bgGrp/bg` |
| In-game gem HUD | `GAME_INGAME_GEM` | `/Canvas/hudLayer/commonHUD/root/Container/gemBar/text` |
| Draw card (Fire & Ice board) | `GAME_FIREICE_CARD_DRAW` | `/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02` |
| Redraw button / gem cost | `GAME_FIREICE_REDRAW_BTN`<br>`GAME_FIREICE_REDRAW_GEM` | `/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/iconContent/root/arrowParent/arrow`<br>`/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/redraw /text` |
| Emoji chat open / quick-chat / send | `GAME_EMOJI_BTN`<br>`GAME_QUICK_CHAT`<br>`GAME_EMOJI_SEND` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc/touchArea`<br>`/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/chatMsgs/container_top/msgButton/bg`<br>`/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/emojiContainer/emojiButton_5/emoji` |
| Text chat button / input | `GAME_CHAT_MSG_BTN`<br>`GAME_CHAT_INPUT` | `/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc_1/touchArea`<br>`/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/TextBar/textArea/textViewport/PlaceHolderText` |
| Burger menu → Quit → Confirm | `GAME_BURGER_MENU`<br>`GAME_QUIT_ICON`<br>`GAME_QUIT_CONFIRM` | `/Canvas/hudLayer/settings/grp/leftGrp/burgerMenu/touchArea`<br>`/Canvas/hudLayer/settings/grp/leftGrp/menuOptions/quit/touchArea`<br>`/Canvas/ModalLayer/QuitGamePopup(Clone)/rootMain/CTA_Red/TouchArea` |

## Data & DB interactions
- `get_user_wallet(player_id)` (`utils/mongo_helper.py`) reads Mongo `wallet.{gold,gems}` for the DB column of the before/after comparison; returns `{}` if `player_id` is falsy.
- `get_wallet_from_data(unity_driver)` (`utils/helpers.py`) reads Gold/Gems (and Pips, unused by this test) live from the Unity `UserManager` class via AltTester `call_static_method` / `call_component_method`.
- No ammo/currency boost is written to Mongo by this test (contrast with Beach Buddies' `set_beach_buddies_ammo`).
- `event_tracker.record("Gameplay", "Fire & Ice Match", "PASS")` is the only event recorded — always `PASS`, independent of whether chat/draw/redraw steps actually succeeded.

## Pass / fail criteria
- **FAIL** (raises `Exception`) if any of: `GAME_PLAY_BUTTON`, `GAME_BET_FIREICE_TAB`, `GAME_BET_PLAY_BTN`, `GAME_BURGER_MENU`, `GAME_QUIT_ICON`, or `GAME_QUIT_CONFIRM` is not found.
- All other missing elements (bet Prev/Next, rules screens, draw/redraw buttons, chat buttons/input) only log a warning and let the test continue.
- **PASS**: the function returns `unity_driver` after the quit-confirm tap and final wallet logging (`tests/test_10_fire&icemode.py:414`). There is no boolean/dict result — success is "reached the end without an unhandled exception."

## Notes & known flakiness
- `GAME_BET_MODE` is imported (`tests/test_10_fire&icemode.py:50`) but never referenced anywhere in the function body — appears to be a dead import.
- The Fire Rules and Ice Rules screens are dismissed using the identical path constants called twice in a row; there is no structural check that the second screen is actually "Ice" and not a repeat of "Fire".
- The ADB-typed chat message escapes `&` as `\&` and spaces as `%s` for the Android shell; this step only does anything useful on a real device/emulator with `adb` reachable via `config.ADB_PATH`.
- All ADB calls (`_adb()`) swallow exceptions and only log a warning, so a broken device/adb setup will not fail the test — the text-chat step can silently no-op.
- The matchmaking-wait and redraw-window timings in the docstring ("up to 15 s", "3-second window") are approximate; actual code uses an 8×(2 s+2 s) loop and a 4 s wait respectively.
