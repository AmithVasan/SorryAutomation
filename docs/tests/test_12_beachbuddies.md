# Beach Buddies

`tests/test_12_beachbuddies.py` · `test_beach_buddies(unity_driver, driver=None)` · types: `complete`

## Purpose
Plays the Beach Buddies CoOp LiveOps event end-to-end: seeds event ammo directly in MongoDB, opens the event from the lobby, autospins through all 4 castles (accepting an invite where the entry gate requires one), collects each castle's 2 milestones + 1 completion giftbox, collects the overall Event Complete reward, and logs a full wallet/ammo summary throughout.

## Preconditions
- `state.user_info["player_id"]` should be populated — it is required both to top up ammo via Mongo (skipped with a warning if absent) and to read the DB wallet (`{}` if absent) (tests/test_12_beachbuddies.py:585-590, 137-138).
- The Beach Buddies event must be active in the build (lobby icon `BB_ICON` present) with at least one enterable castle.
- Mongo connectivity for `set_beach_buddies_ammo` / `get_user_wallet` (`utils/mongo_helper.py`).
- Home screen reachable; the test taps `HOME_BUTTON` itself (tolerant if not found) before starting.

## Flow
1. Log start banner (tests/test_12_beachbuddies.py:572).
2. Home + clear popups: `_wait(HOME_BUTTON, 5)` → `safe_tap` + sleep 1.5 s if found; `clear_all_popups(unity_driver)` (tests/test_12_beachbuddies.py:575-579).
3. `_log_wallet(unity_driver, "before Beach Buddies")`: UI (`HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`), Data (`get_wallet_from_data`), DB (`get_user_wallet(player_id)`, `{}` if no `player_id`) — logged only (tests/test_12_beachbuddies.py:582, helper at 133-151).
4. Ammo top-up: if `player_id` is missing, warn and skip; otherwise `set_beach_buddies_ammo(player_id, BB_AMMO_TOPUP=3000)` writes Mongo `bbData.ammAvail = 3000` directly, then sleep 2 s (tests/test_12_beachbuddies.py:585-590).
5. Open Beach Buddies: `wait_for_safe(By.PATH, BB_ICON, 15)`; raises `"❌ [BB] Beach Buddies lobby icon not found"` if missing; `safe_tap` + sleep 3 s (tests/test_12_beachbuddies.py:593-597).
6. Dismiss the start popup: `_wait(BB_LETS_GO, 3)` → tap + sleep 2 s if present; `clear_all_popups`; if `BB_EVENT_BG` still isn't present within 8 s, also try the universal `close_info_screen(unity_driver)` (taps topmost element at screen centre) + sleep 1 s (tests/test_12_beachbuddies.py:600-607).
7. Confirm the event screen: `_present(BB_EVENT_BG, 10)`; raises `"❌ [BB] Beach Buddies event screen did not open"` if still absent (tests/test_12_beachbuddies.py:609-611).
8. Read `start_ammo = _read_event_ammo(unity_driver)` (`parse_amount` of `BB_AMMO_EVENT`) (tests/test_12_beachbuddies.py:613-614).
9. Castle loop, `for castle_num in 1..NUM_CASTLES(4)`: calls `_play_castle(unity_driver, castle_num, summary)`, then sleep 2 s + `clear_all_popups` between castles (tests/test_12_beachbuddies.py:618-622). `_play_castle` (tests/test_12_beachbuddies.py:366-492) does:
   - a. **Enter** — `_open_castle` (tests/test_12_beachbuddies.py:328-360): waits 8 s for `BB_CASTLES[castle_num]`; `safe_tap` + sleep 2 s. Then `_accept_invite_if_present` (tests/test_12_beachbuddies.py:293-322): if `BB_INVITE_BG` isn't present within 4 s → `"no_modal"`; else probes `BB_ACCEPT_INVITE_TMPL.format(n=1..15)` (0.4 s wait each) for an acceptable invite — first hit is tapped → `"accepted"` (re-taps the castle to actually enter, sleep 2 s); if none of the 15 slots has an invite, taps `BB_INVITE_CLOSE` instead → `"none_available"`. Entry is then confirmed via `_present(BB_AMMO_CASTLE, 5)` → `"entered"`, else `"fail"`.
   - b. If the castle couldn't be opened (`"fail"`) or had no invite to accept (`"none_available"` → `_open_castle` returns `"no_invite"`), `_play_castle` records the castle in `summary` as `status: "FAIL"` or `"NO_INVITE"` (with `event_tracker.record` `"FAIL"`/`"SKIP"`) and returns `False` **without raising** — the castle loop just moves on (tests/test_12_beachbuddies.py:369-392).
   - c. On `"entered"`: reads `ammo_in` (`_read_castle_ammo`) and `progress0` (`_read_progress`) (tests/test_12_beachbuddies.py:394-396).
   - d. Segment loop, up to `MAX_SEGMENTS_PER_CASTLE(8)` iterations (tests/test_12_beachbuddies.py:403-456):
     - `_set_multiplier_max`: up to 6 attempts tapping `BB_MULT_NORMAL`/`BB_MULT_BUTTON` until `BB_MULT_HIGHEST` (x10) is active; only warns (doesn't fail) if it can't confirm x10 (tests/test_12_beachbuddies.py:157-175).
     - `_enable_autospin` (tests/test_12_beachbuddies.py:231-265): waits up to 5 s for `BB_SPIN_BTN` to reappear, then up to 4 attempts of `_long_press_spin` (AltTester `hold_button` at the button's screen position for `HOLD_DURATION=2.0` s, falling back to `pointer_down`/sleep/`pointer_up`), confirming the spin actually started via an immediate reward check or `_wheel_spinning` (castle ammo drops over a 3 s settle window). If it never starts after 4 attempts, the **segment loop breaks** (castle ends early — no exception).
     - `_wait_for_milestone_or_giftbox` polls up to `AUTOSPIN_TIMEOUT=120` s for `BB_GIFTBOX_BG` or `BB_MILESTONE_CTA`; returns `"giftbox"`, `"milestone"`, or `None` on timeout (segment loop also breaks on timeout — no exception) (tests/test_12_beachbuddies.py:268-278).
     - On `"giftbox"`: sleep 5 s (build animation), read amount via `_text_any([BB_GIFTBOX_AMOUNT, BB_GIFTBOX_AMOUNT_ANY])` and cardpack presence (`BB_GIFTBOX_CARDPACK`); tap `BB_GIFTBOX_COLLECT` if found; wait up to 15 s for the event screen to reappear (`_wait_for_event_screen`); set `completed=True`; break the segment loop — castle finished.
     - On `"milestone"`: sleep 2 s, read reward via `_text_any([BB_MILESTONE_AMOUNT, BB_MILESTONE_AMOUNT_ANY])` and append to `milestone_rewards`; tap `BB_MILESTONE_CTA` + sleep 3 s; compute ammo delta (`seg_ammo_before - ammo_after`, `None` if either read failed) into `milestone_deltas`; `continue` (autospin must be re-armed next iteration since it cancels on every reward).
   - e. After the segment loop: `total_used = ammo_in - _read_event_ammo_settled(unity, max_expected=ammo_in)` — the "settled" reader retries up to 8×0.8 s specifically because a raw read right after a giftbox collect can catch the event screen mid-transition and read `0` (tests/test_12_beachbuddies.py:104-119, 458-462). `giftbox_used = total_used - sum(non-None milestone_deltas)` when `total_used` is known.
   - f. Logs a per-castle summary block, `event_tracker.record("Beach Buddies", f"Castle {castle_num}", "PASS" if completed else "FAIL", ...)`, appends the full dict (`castle, status, ammo_in, total_used, milestone_deltas, milestone_rewards, giftbox, giftbox_used`) to `summary`, and returns `completed` (bool; unused by the caller) (tests/test_12_beachbuddies.py:470-492).
10. `_handle_event_complete(unity_driver, summary)` (tests/test_12_beachbuddies.py:625, body 498-527): waits up to 15 s for `BB_EVENT_COMPLETE_BG`; if absent, just logs and returns (not a failure). Else sleeps 5 s, reads `r1` via `_text_any([BB_EVENT_COMPLETE_R1, BB_MILESTONE_AMOUNT_ANY])`, `r2` via `_text_any([BB_EVENT_COMPLETE_R2])`, `r3_cardpack` via presence of `BB_EVENT_COMPLETE_R3_CARDPACK`; taps `BB_EVENT_COMPLETE_CTA` if found + sleep 2 s; `event_tracker.record(..., "Event Complete", "PASS", ...)`; appends `{"event_complete": {...}}` to `summary`.
11. Close the event: `_wait(BB_CLOSE, 8)` → tap + sleep 2 s if found (no raise if missing) (tests/test_12_beachbuddies.py:628-631).
12. Return home: `_wait(HOME_BUTTON, 5)` → tap + sleep 1 s if found; `clear_all_popups` (tests/test_12_beachbuddies.py:632-636).
13. `_log_wallet(unity_driver, "after Beach Buddies")` (tests/test_12_beachbuddies.py:639).
14. `_print_summary(summary, start_ammo)`: logs starting ammo, then per-castle status/ammo-in/used, each milestone's reward + ammo used, giftbox reward/cardpack/ammo used, and the event-complete rewards line (tests/test_12_beachbuddies.py:640, helper at 533-565).
15. Returns `unity_driver` (tests/test_12_beachbuddies.py:642).

## Key element paths
`_BB_MAIN`, `_BB_ZOUT`, `_BB_ZIN` are base-path segments (utils/paths.py:247-249); rows below show what's appended to the relevant base.

| Purpose | Constant | Path |
|---|---|---|
| CoOp modal root (base) | `_BB_MAIN` | `/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain` |
| Zoomed-out (event) state (base) | `_BB_ZOUT` | `_BB_MAIN + "/mainContainer/zoomedOutState"` |
| Zoomed-in (castle) state (base) | `_BB_ZIN` | `_BB_MAIN + "/mainContainer/zoomedInState"` |
| Lobby icon | `BB_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/CoOpEventLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Event start popup CTA | `BB_LETS_GO` | `/Canvas/ModalLayer/CoOpEventStartPopup(Clone)/rootMain/CTA/TouchArea` |
| Event screen confirmation | `BB_EVENT_BG` | `_BB_MAIN + "/bg"` |
| Event-screen ammo counter | `BB_AMMO_EVENT` | `_BB_ZOUT + "/ammoCount/CommonEventAmmoCount_1/layout/root/TextStyle_subText_medium_bold/text"` |
| Castle objectives 1-4 | `BB_CASTLES[1..4]` | `_BB_ZOUT + "/objectivesContainer/scaleAdjuster/Obj{1..4}"` |
| In-castle ammo counter | `BB_AMMO_CASTLE` | `_BB_ZIN + "/wheelContainer/root/bottomUI/CommonEventAmmoCount/layout/root/TextStyle_subText_medium_bold/text"` |
| Multiplier — current value | `BB_MULT_NORMAL` | `_BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier/root/value_Normal"` |
| Multiplier — x10 (highest) node | `BB_MULT_HIGHEST` | `_BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier/root/value_Highest"` |
| Multiplier button (tap target) | `BB_MULT_BUTTON` | `_BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier"` |
| In-castle progress text | `BB_PROGRESS` | `_BB_ZIN + "/ProgressBars/progressBar_1/root/TextStyle_caption_extraSmall_black/text"` |
| Spin button (long-press target) | `BB_SPIN_BTN` | `_BB_ZIN + "/wheelContainer/root/spinButtonContainer/button/buttonImage"` |
| Milestone reward CTA | `BB_MILESTONE_CTA` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea` |
| Milestone reward amount (indexed) | `BB_MILESTONE_AMOUNT` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_14/visualParent/rewardMain/textMain/amountText/text` |
| Milestone reward amount (wildcard fallback) | `BB_MILESTONE_AMOUNT_ANY` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)//amountText/text` |
| Giftbox modal background | `BB_GIFTBOX_BG` | `/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/darkBG` |
| Giftbox collect CTA | `BB_GIFTBOX_COLLECT` | `/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/collectCTA/TouchArea` |
| Giftbox amount (indexed) | `BB_GIFTBOX_AMOUNT` | `/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_8/visualParent/rewardMain/textMain/amountText/text` |
| Giftbox amount (wildcard fallback) | `BB_GIFTBOX_AMOUNT_ANY` | `/Canvas/ModalLayer/GiftBoxRewardModal(Clone)//amountText/text` |
| Giftbox card-pack indicator | `BB_GIFTBOX_CARDPACK` | `/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/rewardsSection/BaseRewardInstantiator(Clone)[1]/root/CardPackRewardItem_2` |
| Invite-friends modal background | `BB_INVITE_BG` | `/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/bgMain` |
| Invite accept button (templated) | `BB_ACCEPT_INVITE_TMPL` | `/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/ScrollView/viewport/content/CoOpEventInvitesScrollItem_{n}/rootMain/Content/RightContent/layout/AcceptButton/touchArea` |
| Invite modal close | `BB_INVITE_CLOSE` | `/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/closeCTA/touchArea` |
| Event-complete modal background | `BB_EVENT_COMPLETE_BG` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/darkBG` |
| Event-complete reward 1 | `BB_EVENT_COMPLETE_R1` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_23/visualParent/rewardMain/textMain/amountText/text` |
| Event-complete reward 2 | `BB_EVENT_COMPLETE_R2` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)[1]/root/SpriteRewardItem_24/visualParent/rewardMain/textMain/amountText/text` |
| Event-complete reward 3 card-pack | `BB_EVENT_COMPLETE_R3_CARDPACK` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)[2]/root/CardPackRewardItem_8/root/single/main` |
| Event-complete collect CTA | `BB_EVENT_COMPLETE_CTA` | `/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea` |
| Event modal close | `BB_CLOSE` | `/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/closeButton/SorryButtonType-Misc/touchArea` |
| Home nav icon | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Home gold/gems counters (UI) | `HOME_GOLD_TEXT` / `HOME_GEMS_TEXT` | `.../commonHUD/root/Container/coinBar/text` / `.../gemBar/text` |

## Data & DB interactions
- **MongoDB write**: `set_beach_buddies_ammo(player_id, ammo=3000)` (utils/mongo_helper.py:141-179) looks up the user by `{"info.gameCode": player_id}`, logs the previous `bbData.ammAvail` for reference, then `update_one`'s `{"$set": {"bbData.ammAvail": ammo}}`. Returns `False` (with a warning) if `player_id` is falsy or no document matches. This is a direct gameplay-state seed executed **before** the event opens — unlike the read-only wallet checks in other tests, it changes the player's DB state.
- **MongoDB read**: `get_user_wallet(player_id)` (utils/mongo_helper.py:116-135) — same helper used by other tests; returns the `wallet` sub-document or `{}`. Called before and after via `_log_wallet`.
- **Unity in-memory**: `get_wallet_from_data(unity_driver)` (`utils/helpers.py`) for Gold/Gems via `UserManager`, same as other tests.
- The UI/Data/DB wallet triple and all ammo/reward readings are logged for information only — no assertion is made on gold, gems, ammo, or reward amounts anywhere in the test.

## Pass / fail criteria
- `test_beach_buddies` has **no top-level try/except and returns no dict** — on success it returns `unity_driver` (tests/test_12_beachbuddies.py:642). The generic harness (`run_this.py:969-1006`) treats this as **PASS** as long as no exception was raised, building `{"name": display_name, "status": "PASS", "steps": ...}` itself; only its own `except Exception` (run_this.py:1008-1021) turns a raised exception into `{"status": "FAIL", "steps": [..., f"Error: {e}"]}`.
- **Hard failures (raise → overall FAIL)**: the Beach Buddies lobby icon not found (tests/test_12_beachbuddies.py:595); the event screen never opening even after the `close_info_screen` fallback (tests/test_12_beachbuddies.py:610).
- **Soft failures (logged, do NOT raise)**: a castle that can't be entered, or whose invite gate has nothing to accept, is recorded in `summary`/`event_tracker` as `"FAIL"`/`"NO_INVITE"` but the castle loop just continues to the next castle. A segment loop that can't start autospin, or that times out waiting for a milestone/giftbox (120 s), simply breaks with `completed=False` → that castle's status is `"FAIL"` in `summary`. **None of this raises.** So it is possible for the function to return normally (overall harness PASS) while 1-4 castles individually show `FAIL`/`NO_INVITE` — that detail only exists in the test's own log output / `event_tracker` records and the (uninspected-by-the-harness) `summary` list, not in the return value.
- No `BB_EVENT_COMPLETE_BG` within 15 s is treated as "event not finished yet" and only logged — not a failure.

## Notes & known flakiness
- `driver` is accepted (default `None`) but never referenced in the function body.
- Because the harness only fails on an uncaught exception, a run where every castle fails/skips individually but nothing raises will still be reported as an overall **PASS** — see Pass/fail criteria above. Anyone auditing results needs the log / `event_tracker` output, not just the harness's PASS/FAIL.
- Autospin is explicitly documented (module docstring, tests/test_12_beachbuddies.py:24-32) as a non-persistent toggle the game cancels on every milestone; `_enable_autospin` re-verifies via ammo-drop (`_wheel_spinning`, 3 s settle) and retries the long-press up to 4 times before giving up on that castle.
- `_read_event_ammo_settled` exists specifically to avoid `total_used` collapsing to the full starting ammo when the event-screen counter is read immediately after a giftbox collect and returns `0` mid-transition (in-code comment, tests/test_12_beachbuddies.py:104-119).
- `BB_ACCEPT_INVITE_TMPL` is probed for scroll-item slots `n=1..15` (0.4 s wait each, up to ~6 s) before concluding no invite is available for that castle.
- The module docstring says only castles 2-4 show the invite gate, but the code itself checks `BB_INVITE_BG` (4 s wait) on every castle including castle 1.
- `MAX_SEGMENTS_PER_CASTLE=8` and `AUTOSPIN_TIMEOUT=120`s are safety ceilings, not expected norms — across 4 castles the worst-case (all timing out) is long, though normal play resolves in far fewer segments per castle.
- `BB_MILESTONE_AMOUNT` / `BB_GIFTBOX_AMOUNT` hardcode a `SpriteRewardItem_N` index that "varies by reward type" (in-code comment); the `_ANY` wildcard variants are the documented robust fallback and are always tried alongside the indexed path via `_text_any`.
