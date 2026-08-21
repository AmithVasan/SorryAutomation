# Bump To Spin

`tests/test_14_bumptospin.py` · `test_bump_to_spin(unity_driver, driver=None)` · types: `complete`

## Purpose
Plays a full Bump To Spin (BTS) event pass: claims the FTUE free ammo, boosts spin ammo in Mongo, autospins a x10 multiplier until every reward tier unlocks, purchases the Royal Pass via Google Play IAP, claims every tier (free + royal), and confirms the equipped-cosmetic reward changed.

## Preconditions
- Account signed in, lobby reachable; BTS event live so `BTS_ICON` is present.
- `state.get("device_id")` set for the kill/relaunch ADB commands.
- `driver` (Appium) must be a working session — required for the Royal Pass Google Play purchase; the test recovers/reconnects it if the buy tap kills the session (`tests/test_14_bumptospin.py:456-469`).
- Player must be able to reach the profile modal (`PROFILE_BUTTON`) so `get_user_snapshot` can resolve `player_id` and the equipped cosmetic — the test raises if `player_id` is missing (`:824-827`).

## Flow
Mirrors the module docstring flow (`tests/test_14_bumptospin.py:1-44`); line refs point to `test_bump_to_spin`:
1. **Lobby + clear popups** — tap `HOME_BUTTON`, `clear_all_popups` (`:814-818`).
2. **Profile cosmetic (before) + player ID** — `get_user_snapshot(unity_driver)` opens/reads/closes the profile modal and populates `state.user_info`; reads `player_id` and `equipped_pawn` from it (`:820-830`).
3. **Wallet (before)** — `_log_wallet` logs UI/Data/DB gold, gems and hammer (`:833`, helper at `:161-176`).
4. **Open BTS + FTUE free ammo** — `_open_bts` taps `BTS_ICON`, sleeps 4s, calls `_handle_free_ammo_ftue` (checks `BTS_FTUE_MODAL`/`BTS_FREE_AMMO_MODAL`, scans `BTS_FREE_AMMO_CONTAINER` amounts, taps `BTS_CLAIM`), then `clear_all_popups`, confirming `BTS_MODAL`/`BTS_TOTAL_AMMO`/`BTS_SPIN_BTN` (`:200-229`, called at `:836`). Logs total ammo in hand (`:838-841`).
5. **Kill → boost → relaunch → reopen** — `_kill_game` stops the driver + `adb shell am force-stop`, sleeps 3s (`:234-249`). `set_bump_to_spin_ammo(player_id, BTS_AMMO_TOPUP=500)` writes the boost while the game is dead (`:844-847`). `_launch_and_reconnect` does `adb shell am start`, sleeps 10s, `connect_altunity`, stores the new driver (`:252-264`, called at `:849`). Up to 3 passes of `clear_all_popups`, then `_open_bts` again, then `_clear_bts_overlays` to remove anything sitting on top of the spin button (`:851-864`).
6. **Multiplier to x10** — `_set_multiplier_max` loops up to `MULT_TAPS=8` times tapping `BTS_MULT_BUTTON`/`BTS_MULT_NORMAL` until `BTS_MULT_HIGHEST` is present; logs a warning (does not fail) if it can't confirm x10 (`:270-287`, called at `:867`).
7. **Autospin until unlocked** — `_autospin_until_unlocked` clears overlays, long-presses `BTS_SPIN_BTN` **once** (autospin is a toggle — a second long-press would stop it) via `hold_button` (falls back to `pointer_down`/`pointer_up`), then polls up to `AUTOSPIN_TIMEOUT=300`s: reads the `BTS_PROGRESS` "num/den" tooltip (done when num≥den), otherwise watches `BTS_TOTAL_AMMO` dropping or (as a cross-check) `bmpToSpn.pnts` increasing in the DB via `get_user_from_db`; if idle >10s it clears overlays and re-holds once (bounded to 4 re-holds), and treats idle >28s as "done" (`:293-424`, called at `:870`).
8. **Buy the Royal Pass** — `popup_handler.ignore_popup(BTS_ROYAL_CLOSE)` first, so the popup handler won't auto-close the purchase modal mid-flow (`:883-885`). `_buy_royal_pass`: taps `BTS_ACTIVATE_BTN`, waits for `BTS_ROYAL_MODAL`, taps `BTS_ROYAL_BUY`, checks the Appium session is alive (reconnects via `set_driver` if not), calls `handle_google_play_purchase(driver)` (from `utils/google_play_helper.py`), falls back to checking `BTS_PURCHASE_SUCCESS` if Google Play timed out, cleans any lingering `com.android.vending` popups via `close_extra_google_play_popups`, reconnects AltTester with `reconnect_alttester`, then taps `BTS_PURCHASE_OK` on the in-game success modal (`:430-521`, called at `:887`). Any pawn/reward screen surfacing right after is drained via `_drain_bts_reward_screens` (`:892`).
9. **Claim every tier** — `_claim_all_tiers` discovers claimable slots by probing `BTS_TIER_ITEM_TMPL.format(n=n)` for `n` in `1..MAX_TIERS(20)`; the list is shown top=highest tier, so slot `n` maps to `game_tier = count - n + 1`. For each slot it scans reward amounts (`_scan_amounts`), then taps the `freePass`/`royalPass`/`bonusPass` claim buttons directly by path (no scrolling — AltTester can tap off-screen scroll items) via `_claim_tier_button`. A tier with a numeric reward is dismissed with the fast `_quick_dismiss`; a value-less tier (could be a lootbox) is drained with `_drain_bts_reward_screens`, which loops over `LOOTBOX_CLAIM` (draining consecutive lootbox screens via `_drain_lootboxes`, with a raw ADB tap-center fallback), `PAWN_REWARDS_MODAL` (tap `PAWN_REWARDS_EQUIP` or `PAWN_REWARDS_CONTINUE`), and `REWARD_SUMMARY_CTA`. Repeats passes until a pass claims nothing (up to 5) (`:628-717`, called at `:895`).
10. **Confirm via DB** — `_bts_db_state` reads `bmpToSpn.ammo`/`pnts`/`isRylPsActv`/`frePsClms`/`rylPsClms` from Mongo (`:723-736`). `purchase_ok = royal_active and len(royal_claimed) > 0`; if false, logs a `"FAIL"` step saying the Royal Pass purchase failed (`:898-921`).
11. **Re-enable Royal Pass close + close BTS → lobby** — `popup_handler.unignore_popup(BTS_ROYAL_CLOSE)` (also guaranteed in a `finally` block even on exception), tap `BTS_CLOSE`, tap `HOME_BUTTON`, `clear_all_popups` (`:923-936`, `finally` at `:977-983`).
12. **Confirm cosmetic equipped** — `_read_equipped_cosmetic` reopens the profile, reads `PROFILE_PAWN`, closes it; compares against `cosmetic_before` (`:181-194`, called at `:939-945`).
13. **Wallet (after) + summary** — `_log_wallet` "after", then `_print_summary` logs per-tier rewards, free/royal tiers claimed (from DB), cosmetic before/after, and UI/Data/DB deltas for gold/gems/hammer (`:948-950`, summary at `:742-794`).

## Key element paths
| Purpose | Constant | Path |
|---|---|---|
| Profile button / pawn name / close | `PROFILE_BUTTON` / `PROFILE_PAWN` / `PROFILE_CLOSE` | `.../profileSection/profileIcon/ProfileButton` / `.../Cosmetics-Button/.../CosmeticNameText/text` / `SelfProfileModal(Clone)/.../closeCTA/touchArea` |
| BTS lobby icon / modal | `BTS_ICON` (=`HF_BTS_ICON`) / `BTS_MODAL` | `.../BumpToSpinWidget/.../mainIcon` / `/Canvas/ModalLayer/BumpToSpinModal(Clone)` |
| Free-ammo FTUE modal / claim | `BTS_FTUE_MODAL` / `BTS_CLAIM` (=`HF_BTS_CLAIM`) | `FreeBTSAmmoClaimModal(Clone)/darkBG` / `.../CTA_Green/TouchArea` |
| Total ammo counter | `BTS_TOTAL_AMMO` | `.../root/ticketCounter/root/TextStyle_bodyText_small/text` |
| Multiplier highest / button | `BTS_MULT_HIGHEST` / `BTS_MULT_BUTTON` | `.../Multiplier/root/value_Highest` / `.../rightCornerGrp/Multiplier` |
| Spin button / progress tooltip | `BTS_SPIN_BTN` / `BTS_PROGRESS` | `.../rollButtonParent/spinButton/TouchArea` / `.../tierProgressTooltip/.../text` |
| Activate / Royal modal / buy | `BTS_ACTIVATE_BTN` / `BTS_ROYAL_MODAL` / `BTS_ROYAL_BUY` | `.../activateButton/.../TouchArea` / `BumpToSpinRoyalPassModal(Clone)` / `.../content/CTA/TouchArea` |
| Purchase success / OK | `BTS_PURCHASE_SUCCESS` / `BTS_PURCHASE_OK` | `PurchaseNotifModal(Clone)/darkBG` / `.../ButtonLayer/Okay Button/TouchArea` |
| Tier scroll content / item template | `BTS_TIER_CONTENT` / `BTS_TIER_ITEM_TMPL` | `.../mainSection/scrollView/viewport/content` / `.../content/BumpToSpinTierScrollItem_{n}` |
| BTS close | `BTS_CLOSE` (=`HF_BTS_CLOSE`) | `BumpToSpinModal(Clone)/root/headerButtons/closeButton/.../touchArea` |
| Royal Pass close (ignored during purchase) | `BTS_ROYAL_CLOSE` | `BumpToSpinRoyalPassModal(Clone)/rootmain/.../crossButton/touchArea` |

## Data & DB interactions
- **Boost field**: `bmpToSpn.ammo` via `set_bump_to_spin_ammo(player_id, ammo=500)` (`utils/mongo_helper.py:233-276`). `BTS_AMMO_TOPUP = 500` (`tests/test_14_bumptospin.py:86`). Written while the game is force-stopped, same rationale as Treasure Island.
- **Other `bmpToSpn` fields read (not written)**: `pnts` (tier points, cross-checked live during autospin via `get_user_from_db`), `isRylPsActv` (royal pass bought flag), `frePsClms` / `rylPsClms` (maps of claimed tier numbers) — all read post-claim by `_bts_db_state` (`get_user_from_db`, `utils/mongo_helper.py:334-348`) to authoritatively confirm the purchase and claims, per the module docstring's "DB fields verified against a live doc" note (`:41-43`).
- **3-way wallet check** (`_log_wallet`, `:161-176`): UI via `fast_text` on `HOME_GOLD_TEXT`/`HOME_GEMS_TEXT`/`HOME_HAMMER_TEXT`; Data via `get_wallet_from_data(unity)` (`UserManager.GetGold`/`GetGems`/`GetPips`, `utils/helpers.py:50-88`); DB via `get_user_wallet(player_id)` (`utils/mongo_helper.py:116-135`).
- `get_user_snapshot(unity_driver)` (`utils/helpers.py:91-145`) is the source of `player_id` and `equipped_pawn` (before), and populates `state.user_info`.
- `event_tracker.record(...)` is called for Open, Autospin, Royal Pass Purchase, and Claim Tiers (`:840-841, 876-877, 889, 917-921`).

## Pass / fail criteria
- Always returns `{"name": "Bump To Spin", "status", "duration", "steps", "unity_driver"}`.
- `status` is computed from the DB check: `"PASS"` if `purchase_ok` (`isRylPsActv` true **and** at least one `rylPsClms` entry) else `"FAIL"` (`tests/test_14_bumptospin.py:900-901, 952-957`) — this is the one test of the three where the DB-verified outcome directly determines the top-level pass/fail, not just an exception.
- `status = "FAIL"` also on any unhandled exception (e.g. missing `player_id`, BTS failing to open/reopen, Royal Pass buttons not found, Google Play purchase failing) — caught in the outer `try/except` (`:966-975`).
- The `finally` block unconditionally re-enables the `BTS_ROYAL_CLOSE` popup-close handler even on failure, so a failed run doesn't leave that popup permanently suppressed for later tests (`:977-983`).

## Notes & known flakiness
- Autospin detection is a toggle mechanism — the code is deliberately careful to press-hold only once and to re-hold only after confirmed idleness, because a spurious second long-press would stop autospin entirely; this is inherently timing-sensitive on a real device.
- Tier count is adaptive (`MAX_TIERS=20` safety cap; docstring notes 15 exist today) — claim-button discovery and the slot→tier index mapping depend on how many `BumpToSpinTierScrollItem_N` nodes are actually rendered.
- Reward-screen draining distinguishes "has a numeric reward" (fast dismiss, can't be a lootbox) from "value-less" (must patiently drain possible lootbox/pawn/reward-summary screens) — mis-detection here could either slow the run or leave a screen stuck.
- The Royal Pass purchase reuses the shared `utils/google_play_helper.py` IAP flow (session crash-recovery, "safe" post-purchase dismiss labels only, never Cancel) — failures here are Google Play/UiAutomator2 timing issues outside this test's control.
- Full correctness (autospin actually reaching all tiers, Royal Pass genuinely unlocking paid rewards, cosmetic equip actually changing) needs a live, currently-running BTS event and a working Google Play sandbox purchase on-device; it cannot be validated from source alone.
