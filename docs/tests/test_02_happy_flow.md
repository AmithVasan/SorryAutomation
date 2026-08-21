# Happy Flow

`tests/test_02_happy_flow.py` · `test_happy_flow(unity_driver, driver)` · types: `smoke`

## Purpose
Smoke-checks that every lobby widget/feature opens and closes cleanly, one after another, tolerating any that are absent (SKIP) or that error (FAIL) without stopping the rest of the run. Per the module docstring, it runs before `test_03_shop` and only on the "smoke" checklist (tests/test_02_happy_flow.py:1-8).

## Preconditions
- An active `unity_driver` session, presumably already logged in via `test_01` and positioned in (or reachable from) the lobby.
- Pre-flight best-effort taps `HOME_BUTTON` (5 s wait) to reach the lobby, but does not fail if it's missing (tests/test_02_happy_flow.py:804-808).
- Pre-flight also spends up to 30 s clearing lobby popups via `handle_one_popup()` until two consecutive clean passes are seen (tests/test_02_happy_flow.py:810-822) — every feature function assumes a popup-free lobby afterward.
- BumpToSpin (#14 in the list) is gated behind `HF_BTS_ICON` being non-blank in `utils/paths.py`; it is currently blank, so that feature always returns SKIP without attempting a wait (tests/test_02_happy_flow.py:673-678).

## Flow

**Pre-flight** (`test_happy_flow`, tests/test_02_happy_flow.py:792-824):
1. Log start (tests/test_02_happy_flow.py:798).
2. Best-effort tap `HOME_BUTTON` (5 s wait) and sleep 1.5 s if found (tests/test_02_happy_flow.py:804-808).
3. Clear all lobby popups: loop calling `handle_one_popup()` (0.3 s between calls) until 2 consecutive calls report nothing to close, capped at 30 s total (tests/test_02_happy_flow.py:810-822).

**Main loop** (tests/test_02_happy_flow.py:826-846): iterates the 15 `("Friendly Name", _do_<name>)` tuples in `FEATURES` (tests/test_02_happy_flow.py:773-789) in order, each call wrapped in its own `try/except`:
4. `result = fn(unity_driver)` — `True` → `event_tracker.record("Happy Flow", name, "PASS")` and append to `passed`; `False` → record `"SKIP"` and append to `skipped`; exception → log a warning, record `"FAIL"`, append to `failed`, then recover via `_go_home(unity_driver)` + `clear_all_popups(unity_driver)` before continuing to the next feature (tests/test_02_happy_flow.py:830-846). One feature's failure never aborts the run.
5. After all 15, logs the Passed/Skipped/Failed counts and names (tests/test_02_happy_flow.py:848-853).
6. Returns `unity_driver` unchanged — no status dict (tests/test_02_happy_flow.py:854).

**Shared per-feature shape.** Every `_do_*` helper below follows the same base pattern: `wait_for_safe(..., 10)` for the lobby icon (return `False`/SKIP if absent, using `By.PATH` via `utils.popup_handler.wait_for_safe`, which *does* run popup recovery) → `icon.tap()` → `time.sleep(...)` → optional info-screen/FTUE handling via the in-modal-safe `_wait()` helper (direct `wait_for_object`, no popup recovery, tests/test_02_happy_flow.py:94-99) and/or `close_info_screen()` → `_wait()` for the close button and tap it if found (warn-only, still returns `True`, if not). Deviations per feature:

7. **Season Pass** (`_do_season_pass`, :127-144) — icon → 1.5 s → close via `SEASON_PASS_CLOSE`. No info screen or FTUE handling.
8. **Treasure Island** (`_do_treasure_island`, :164-220, FTUE-aware) — icon → 4 s (opening animation + info-screen load) → up to 3 retry attempts dismissing `HF_TI_INFO_SCREEN` via `close_info_screen()` → optional `HF_TI_FREE_AMMO_MODAL` (logs `HF_TI_FREE_AMMO_COUNT`, taps `HF_TI_AWESOME_BTN`) → a generic 6× `close_info_screen()` tap loop (2 s gaps) intended to dismiss the chest/kitty-bag/2nd-chest/level-complete/final-transition FTUE overlays → close via `HF_TI_CLOSE`.
9. **SkyRush / SoapBox** (`_do_skyrush`, :227-274) — icon → optional info screen (`HF_SKYRUSH_INFO`) → `popup_handler.ignore_popup(HF_SKYRUSH_CLOSE)` while it waits for `HF_SKYRUSH_MODAL` and taps `HF_SKYRUSH_START`, handles a possible post-start info screen, then confirms via `HF_SKYRUSH_LEADERBOARD` (10 s wait, warns if absent) before tapping `HF_SKYRUSH_CLOSE`; `unignore_popup` runs in a `finally` (:270-271).
10. **Leagues** (`_do_leagues`, :281-321) — `HF_LEAGUE_ICON` specifically targets the Bronze-tier badge, "skips if player is in another tier" per in-code comment (:282) → optional info screen before *and* after reading `HF_LEAGUE_RANK` text → close, wrapped in `ignore_popup`/`unignore_popup` for `HF_LEAGUE_CLOSE`.
11. **Pie Duel** (`_do_pie_duel`, :328-369) — icon → optional info screen → waits for `HF_PIEDUEL_MODAL` (returns `True` early with a warning if it never opens, :347-349) → optional 2nd info screen → close; `ignore_popup`/`unignore_popup` wrapped around `HF_PIEDUEL_CLOSE`.
12. **Beach Buddies** (`_do_beach_buddies`, :376-414) — icon → optional info screen → optional `BB_LETS_GO` start-popup tap (no dedicated close for that popup) → optional 2nd info screen → close via `BB_CLOSE`.
13. **Ad Rewards** (`_do_ad_rewards`, :421-438) — icon → 1.5 s → close via `HF_AD_CLOSE`. No info/FTUE handling.
14. **Welcome Pack ↔ EDLP** (`_do_welcome_pack_or_edlp`, :450-499) — mutually exclusive slot: tries `HF_WELCOME_PACK_ICON` first (5 s); if present, handles it (icon → close, `ignore_popup`/`unignore_popup` wrapped) and returns, **skipping EDLP entirely**. Only if absent does it fall back to `HF_EDLP_ICON` (10 s wait) and repeat the same open/close pattern for EDLP.
15. **Daily Tasks** (`_do_daily_tasks`, :506-523) — icon → 1.5 s → close via `HF_DAILY_TASKS_CLOSE`. No info/FTUE handling.
16. **Endless Sale** (`_do_endless_sale`, :530-552) — icon → close via `HF_ENDLESS_SALE_CLOSE`, wrapped in `ignore_popup`/`unignore_popup`.
17. **Puzzle Event** (`_do_puzzle_event`, :559-606, FTUE-aware) — icon → optional `HF_PUZZLE_FTUE_MODAL` (logs `HF_PUZZLE_AMMO_COUNT`, taps `HF_PUZZLE_COLLECT`) → optional `HF_PUZZLE_PIECE_FTUE` tap, which if present also taps `HF_PUZZLE_ALL_ICON` to open the full Puzzle screen → logs `HF_PUZZLE_TOTAL_AMMO` → close via `HF_PUZZLE_CLOSE`.
18. **Piggy Bank** (`_do_piggy_bank`, :613-642) — the only feature that locally imports its path constants (`PIGGY_BANK_ICON`, `PIGGY_BANK_MODAL` from `utils.paths`, :614) instead of at module load. Icon → waits for `PIGGY_BANK_MODAL` (returns `True` early with a warning if it never opens, :627-629) → close via `PIGGY_BANK_CLOSE`; `ignore_popup`/`unignore_popup` wrapped.
19. **Legendary Pawn** (`_do_legendary_pawn`, :649-666) — icon (`HF_PAWN_ICON`) → 1.5 s → close via `PAWN_SALE_CLOSE`. No info/FTUE handling.
20. **BumpToSpin** (`_do_bts`, :673-722, FTUE-aware) — short-circuits to `False`/SKIP immediately if `HF_BTS_ICON` is falsy (:674-678, currently always true) → otherwise icon → optional info screen → optional `HF_BTS_FTUE_MODAL` (logs `HF_BTS_FREE_AMMO_COUNT`, taps `HF_BTS_CLAIM`) → optional 2nd info screen → close via `HF_BTS_CLOSE`.
21. **Social Lobby** (`_do_social`, :729-764) — icon → taps 4 tabs in sequence (Recent/Chat/Invites/Friends, 1 s apart, warns per-tab if one is missing but continues) → navigates back via `HOME_BUTTON` rather than a modal close button.

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Bottom-nav Home icon | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Season Pass — icon | `SEASON_PASS_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/SeasonPassLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Season Pass — close | `SEASON_PASS_CLOSE` | `/Canvas/ModalLayer/SeasonPassModal(Clone)/root/closeGrp/closeCTA/touchArea` |
| Treasure Island — icon | `HF_TI_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/FortuneIslandLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Treasure Island — info screen | `HF_TI_INFO_SCREEN` | `/Canvas/ModalLayer/fortuneislandinfoModal(Clone)/root/container/PlayerGrp/bottomSection` |
| Treasure Island — free-ammo FTUE modal | `HF_TI_FREE_AMMO_MODAL` | `/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain` |
| Treasure Island — free-ammo count text | `HF_TI_FREE_AMMO_COUNT` | `/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain/InnerPanel/Bg/SpriteRewardItem/visualParent/rewardMain/textMain/amountText/textt` |
| Treasure Island — "Awesome" claim button | `HF_TI_AWESOME_BTN` | `/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain/GreenCTA/TouchArea` |
| Treasure Island — close | `HF_TI_CLOSE` | `/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/closeButton/closeButton/touchArea` |
| Treasure Island — total ammo text *(imported, unused — see Notes)* | `HF_TI_TOTAL_AMMO` | `/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/bottomSection/FIMainScreenAmmoUI/root/container/bg/textLabel/TextStyle_caption_extraSmall_black/text` |
| Treasure Island — chest FTUE *(imported, unused; typo "FortuneIslased" is in-game)* | `HF_TI_CHEST_FTUE` | `/Canvas/ModalLayer/FortuneIslasedMainModal(Clone)/Container/InitialFtueHandler/click` |
| Treasure Island — generic FTUE click *(imported, unused)* | `HF_TI_FTUE_CLICK` | `/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/InitialFtueHandler/click` |
| Treasure Island — level-complete reward *(imported, unused)* | `HF_TI_LEVEL_COMPLETE` | `/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/FortuneIslandLevelCompleteRewardsModal/ClickArea` |
| SkyRush — icon | `HF_SKYRUSH_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/liveOpsRaceWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| SkyRush — start popup modal | `HF_SKYRUSH_MODAL` | `/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)` |
| SkyRush — start-race CTA | `HF_SKYRUSH_START` | `/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)/rootMain/footerGrp/CTA/TouchArea` |
| SkyRush — info screen | `HF_SKYRUSH_INFO` | `/Canvas/ModalLayer/LiveOpsRaceInfoModal(Clone)/darkBG` |
| SkyRush — leaderboard | `HF_SKYRUSH_LEADERBOARD` | `/Canvas/ModalLayer/LiveOpsRaceLeaderboardModal(Clone)` |
| SkyRush — close | `HF_SKYRUSH_CLOSE` | `/Canvas/ModalLayer/LiveOpsRaceLeaderboardModal(Clone)/rootMain/closeCTA/touchArea` |
| Leagues — icon (Bronze badge only) | `HF_LEAGUE_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/leagueWidget/scaleAdjuster/root/Overlay Parent/badgeContainer/leagueBadge_Bronze(Clone)/root/body/main` |
| Leagues — rank text | `HF_LEAGUE_RANK` | `/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/layout/midSection/rewardTopInfo/heading/leagueHeading/text` |
| Leagues — close | `HF_LEAGUE_CLOSE` | `/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea` |
| Leagues — info screen | `HF_LEAGUE_INFO` | `/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg` |
| Pie Duel — icon | `HF_PIEDUEL_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/DuelEventLobbyButton/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Pie Duel — modal | `HF_PIEDUEL_MODAL` | `/Canvas/ModalLayer/DuelEventMainModal(Clone)` |
| Pie Duel — close | `HF_PIEDUEL_CLOSE` | `/Canvas/ModalLayer/DuelEventMainModal(Clone)/rootMain/closeCTA/touchArea` |
| Pie Duel — info screen | `HF_PIEDUEL_INFO` | `/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg` |
| Beach Buddies — icon | `HF_BB_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/CoOpEventLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Beach Buddies — info screen | `HF_BB_INFO` | `/Canvas/ModalLayer/CoOpEventInfoScreen(Clone)/bg` |
| Beach Buddies — start-popup CTA | `BB_LETS_GO` | `/Canvas/ModalLayer/CoOpEventStartPopup(Clone)/rootMain/CTA/TouchArea` |
| Beach Buddies — close | `BB_CLOSE` | `/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/closeButton/SorryButtonType-Misc/touchArea` |
| Ad Rewards — icon | `HF_AD_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/rewardedAdsWidget/scaleAdjuster/root/Overlay Parent/rewardedAdsIcon/WidgetIcon/mainIcon` |
| Ad Rewards — close | `HF_AD_CLOSE` | `/Canvas/ModalLayer/RewardedAdsProgressModal(Clone)/closeGrp/closeCTA/touchArea` |
| Welcome Pack — icon | `HF_WELCOME_PACK_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/welcomePackBtn /scaleAdjuster/root/buttonArea[1]` |
| Welcome Pack — close | `HF_WELCOME_PACK_CLOSE` | `/Canvas/ModalLayer/WelcomePackModal(Clone)/rootMain/SorryButtonType-Misc/touchArea` |
| EDLP — icon (fallback) | `HF_EDLP_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/EDLPPackBtn/scaleAdjuster/root/buttonArea` |
| EDLP — close | `HF_EDLP_CLOSE` | `/Canvas/ModalLayer/EdlpGold02(Clone)/rootMain/content/crossButton/touchArea` |
| Daily Tasks — icon | `HF_DAILY_TASKS_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/dailyTaskBtn/scaleAdjuster/root/touchArea` |
| Daily Tasks — close | `HF_DAILY_TASKS_CLOSE` | `/Canvas/ModalLayer/DailyTaskModal(Clone)/rootMain/closeButton/touchArea` |
| Endless Sale — icon | `HF_ENDLESS_SALE_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/mineRunWidget/scaleAdjuster/root/buttonArea` |
| Endless Sale — close | `HF_ENDLESS_SALE_CLOSE` | `/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea` |
| Puzzle Event — icon | `HF_PUZZLE_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/PuzzleEventWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Puzzle Event — free-ammo FTUE modal | `HF_PUZZLE_FTUE_MODAL` | `/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/PopupCommonHeader` |
| Puzzle Event — free-ammo count text | `HF_PUZZLE_AMMO_COUNT` | `/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/puzzleEventInnerContent(Clone)/content/rewardArea/BaseRewardInstantiator/root/SpriteRewardItem_72/visualParent/rewardMain/textMain/amountText/text` |
| Puzzle Event — collect button | `HF_PUZZLE_COLLECT` | `/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/puzzleEventInnerContent(Clone)/buttonsGroup/SorryButtonType-Text/TouchArea` |
| Puzzle Event — puzzle-piece FTUE nudge | `HF_PUZZLE_PIECE_FTUE` | `/Canvas/ModalLayer/CommonNudgeModal(Clone)/Btn(Clone)` |
| Puzzle Event — "all puzzles" icon | `HF_PUZZLE_ALL_ICON` | `/Canvas/ModalLayer/CommonNudgeModal(Clone)/buttonCTA(Clone)` |
| Puzzle Event — total ammo text | `HF_PUZZLE_TOTAL_AMMO` | `/Canvas/ModalLayer/PuzzleEventModal(Clone)/Container/footer/PuzzleHUD/layout/root/TextStyle_subText_medium_bold/text` |
| Puzzle Event — close | `HF_PUZZLE_CLOSE` | `/Canvas/ModalLayer/PuzzleEventModal(Clone)/Container/closeButton/closeGrpAnimate/SorryButtonType-Misc/touchArea` |
| Piggy Bank — icon | `PIGGY_BANK_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/PiggyBankWidget` |
| Piggy Bank — modal | `PIGGY_BANK_MODAL` | `/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain` |
| Piggy Bank — close | `PIGGY_BANK_CLOSE` | `/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/header/Close Button/touchArea` |
| Legendary Pawn — icon | `HF_PAWN_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/LegendaryPawnLobbyWidget/scaleAdjuster/root/Overlay Parent/bg` |
| Legendary Pawn — close | `PAWN_SALE_CLOSE` | `/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/CrossButton/touchArea` |
| BumpToSpin — icon | `HF_BTS_ICON` | *(blank in `utils/paths.py` — feature always SKIPs)* |
| BumpToSpin — info screen close | `HF_BTS_INFO` | `/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)/root/close/SorryButtonType-close/touchArea` |
| BumpToSpin — free-ammo FTUE modal | `HF_BTS_FTUE_MODAL` | `/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)` |
| BumpToSpin — free-ammo count text | `HF_BTS_FREE_AMMO_COUNT` | `/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)/rootMain/reward/BaseRewardInstantiator/root/SpriteRewardItem_136/visualParent/rewardMain/textMain/amountText/text` |
| BumpToSpin — claim button | `HF_BTS_CLAIM` | `/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)/rootMain/CTA_Green/TouchArea` |
| BumpToSpin — close | `HF_BTS_CLOSE` | `/Canvas/ModalLayer/BumpToSpinModal(Clone)/root/headerButtons/closeButton/SorryButtonType-close/touchArea` |
| Social Lobby — icon | `HF_SOCIAL_ICON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Soical/SoicalIcon/icon` |
| Social Lobby — Recent tab | `HF_SOCIAL_TAB_RECENT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Recent/inactiveTab` |
| Social Lobby — Chat tab | `HF_SOCIAL_TAB_CHAT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Chat/inactiveTab` |
| Social Lobby — Invites tab | `HF_SOCIAL_TAB_INVITE` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Invites/inactiveTab` |
| Social Lobby — Friends tab | `HF_SOCIAL_TAB_FRIENDS` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Friends/inactiveTab` |

## Data & DB interactions
No MongoDB access and no Unity in-memory (`UserManager`) reads. `_log_text()` (tests/test_02_happy_flow.py:113-120) reads `get_text()` off a handful of elements — Leagues rank, Treasure Island/Puzzle/BumpToSpin free-ammo counters, Puzzle total-ammo — purely for logging; no assertions or comparisons are made against these values. Each feature's PASS/SKIP/FAIL is also recorded via `event_tracker.record("Happy Flow", name, status)` (tests/test_02_happy_flow.py:835/838/842), which is an in-process results tracker, not a database.

## Pass / fail criteria
- `test_happy_flow` returns `unity_driver` only — there is **no** `{"status": ...}` dict, unlike `test_03_shop`/`test_04_lucky_cards`'s convention.
- Every feature's exception is caught inside the `FEATURES` loop (tests/test_02_happy_flow.py:840-846), so a raised error from any single `_do_*` function cannot fail `test_happy_flow` itself — it only adds that feature's name to the internal `failed` list and an `event_tracker` "FAIL" record.
- The pre-flight `handle_one_popup()` calls inside the popup-clearing loop (tests/test_02_happy_flow.py:815) are **not** wrapped in a try/except at that call site, so an internal exception there (not observed in this file — `handle_one_popup` lives in `utils/popup_handler`) could still propagate out of `test_happy_flow` and fail the test; this is the only unguarded call in the function.
- Net effect: a run where all 15 features SKIP or FAIL still returns normally — pass/fail visibility for individual features lives entirely in the logged summary (tests/test_02_happy_flow.py:848-853) and `event_tracker`, not in the function's return value or an exception.

## Notes & known flakiness
- The module docstring's "Order" list (tests/test_02_happy_flow.py:9-23) enumerates 14 features; the actual `FEATURES` list (tests/test_02_happy_flow.py:773-789) has 15 — **Social Lobby** (`_do_social`) runs last but is not mentioned in the docstring.
- BumpToSpin is permanently skipped in the current build: `HF_BTS_ICON` is blank in `utils/paths.py`, and `_do_bts` short-circuits to SKIP before any wait (tests/test_02_happy_flow.py:673-678).
- Treasure Island imports `HF_TI_TOTAL_AMMO`, `HF_TI_CHEST_FTUE`, `HF_TI_FTUE_CLICK`, `HF_TI_LEVEL_COMPLETE` (tests/test_02_happy_flow.py:65-67) but never references them in `_do_treasure_island` — the chest/kitty-bag/level-complete FTUE overlays are instead dismissed by a generic 6× blind-tap loop (`close_info_screen()`, tests/test_02_happy_flow.py:204-209), not per-element waits. Whether that loop reliably covers every overlay it's meant to replace is not verified by the test.
- `HF_BTS_INFO`'s path (utils/paths.py:561) targets the info modal's own close-button touch area rather than a generic "is this showing" marker — consistent in effect with the other `_INFO` constants (all are just presence probes fed into `_wait()`), but worth knowing if reused elsewhere.
- Two in-game typos are baked verbatim into path strings: `FortuneIslasedMainModal` (`HF_TI_CHEST_FTUE`, unused) and `Soical`/`SoicalIcon` (`HF_SOCIAL_ICON`, active) — must not be "corrected" when editing `utils/paths.py`.
- `HF_WELCOME_PACK_ICON` contains a literal trailing space in `"welcomePackBtn "` before `/scaleAdjuster` (utils/paths.py:487) — also verbatim from the game's object hierarchy.
- `HF_LEAGUE_ICON` targets the Bronze-tier badge specifically, so Leagues SKIPs for any player currently in a different tier (in-code comment, tests/test_02_happy_flow.py:282).
- A feature failure recovers via `_go_home()` + `clear_all_popups()` (tests/test_02_happy_flow.py:845-846) but does not retry that feature — it's simply marked FAIL and the loop moves on.
- No overall time budget is enforced across the 15 features; with up to a ~10 s icon wait each (plus FTUE handling), a run where several icons are absent or slow can still take a couple of minutes.
- Actual signature is `test_happy_flow(unity_driver, driver)`; `driver` is accepted but never referenced in the body.
