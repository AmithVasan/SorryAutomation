# Shop Purchase

`tests/test_03_shop.py` · `test_shop_purchase(unity_driver, driver)` · types: `smoke, iap, regression, complete`

## Purpose
Drives the real-money Shop flow end-to-end: claims the gold Bank bonus (Home or Shop, whichever is present), buys gold/gem currency packs through an actual Google Play purchase dialog (a run-type-dependent subset, or every pack for the `iap` run type), buys and claims cosmetic lootbox packs (including a low-gem-triggered gem top-up sub-flow), and finishes by logging a three-way Gold/Gems comparison across UI, Unity in-memory data, and MongoDB. **This is a live IAP/payment flow** — every purchase in this test spends real or sandbox currency via the Google Play UI, not a mock.

## Preconditions
- `check_preconditions()` requires `state.user_info["player_id"]` to already be set, raising `"❌ player_id missing — did test_01 run successfully?"` if not (tests/test_03_shop.py:65-67, called at :570).
- An active `unity_driver` (AltTester) session, and a working `driver` (Appium) session able to drive the Google Play purchase UI via `handle_google_play_purchase()` for every pack/lootbox purchase and the low-gem top-up.
- `state.get("device_id")` should be set for the ADB fallback tap (`_tap_screen_center`, tests/test_03_shop.py:39-47) used when a lootbox reward screen doesn't respond to a path-targeted tap; if unset, that fallback silently no-ops with a warning.
- `state.get("run_type", "complete")` selects the pack subset: `"smoke"`, `"regression"`, `"bat"`, and `"complete"` all purchase only the subset (`SMOKE_GOLD_PACKS = {"Gold 500K"}`, `SMOKE_GEM_PACKS = {"6000 Gems"}`, `SMOKE_LOOTBOX_PACKS = {"Common x1", "Legendary x3"}`); only `"iap"` buys every gold, gem, and lootbox pack (tests/test_03_shop.py:50-59, 601-616, 232-246).

## Flow
1. Log "Starting Shop Purchase Test", then `check_preconditions()` (tests/test_03_shop.py:566-570).
2. `handle_bank_if_available(unity_driver)` (tests/test_03_shop.py:110-200, called at :573):
   - Clears one popup, sleeps 2 s, checks `HOME_BANK` (5 s wait).
   - If present: snapshots Home gold/gems, `safe_tap`s it, polls `wait_for_gold_update()` (up to 8 s; "stable" after 3 consecutive non-increasing reads, 0.5 s apart) against `HOME_GOLD_TEXT`, logs the before/delta/after, records `event_tracker("Shop", "Bank", "PASS")`, returns `"home"`.
   - Else: re-reads Home gold as a baseline, waits for `SHOP_BUTTON` (10 s) and taps it, then checks `SHOP_BANK` (5 s wait). If present: taps it, sleeps 2 s, polls `wait_for_gold_update()` against `SHOP_GOLD_TEXT` using the Home-gold baseline, logs and records PASS, returns `"shop"`.
   - If neither bank is found, the function falls off the end and implicitly returns `None`.
3. If `bank_location != "shop"` (i.e. `"home"` or `None`), waits for `SHOP_BUTTON` (15 s, raises `"❌ Shop button not found"` if missing) and `safe_tap`s it, then sleeps 2 s; skipped if the Bank step already left the test inside the Shop (tests/test_03_shop.py:577-594).
4. `handle_one_popup(unity_driver)` once (tests/test_03_shop.py:596).
5. Builds `all_packs` from `GOLD_PACKS + GEM_PACKS`: the smoke/regression/bat/complete subset, or every pack for any other `run_type` (in practice `"iap"`) (tests/test_03_shop.py:601-616).
6. For each `(name, path, val_path, price_path)` in `all_packs` (tests/test_03_shop.py:618-714):
   - Find the buy button (10 s wait; one `scroll_shop()` retry if not immediately visible); warn and `continue` to the next pack if still not found.
   - Read the on-screen value/price text, falling back to the hardcoded `name` / `"N/A"` respectively.
   - Snapshot gold+gems (`get_wallet_snapshot` against `GOLD_TEXT`/`GEMS_TEXT`, which alias `SHOP_GOLD_TEXT`/`SHOP_GEMS_TEXT`).
   - `safe_tap` the pack, sleep 3 s, `handle_google_play_purchase(driver)`, sleep 3 s.
   - `reconnect_alttester(unity_driver)` — on failure, log an error and `continue` to the next pack.
   - Wait up to 15 s for `PURCHASE_OK` and tap it if present (in-code comment: this button is shared by the success **and** fail modals, so dismissing it "tells us NOTHING about whether the purchase succeeded", :665-668).
   - Snapshot gold+gems again; `success = after_gold > before_gold` (Gold packs) or `after_gems > before_gems` (Gem packs) — the wallet delta is the sole ground truth for outcome.
   - Log and `event_tracker.record("Shop", f"{pack_value} {pack_type} Pack", "PASS"/"FAIL", f"Cost: {pack_price}")`; sleep 1 s before the next pack.
7. `purchase_all_lootboxes(unity_driver, driver)` (tests/test_03_shop.py:717) — see breakdown below.
8. Wait for `HOME_BUTTON` (10 s); if found, `safe_tap` it, sleep 1 s, `handle_one_popup()` (tests/test_03_shop.py:720-733).
9. `get_user_snapshot(unity_driver)` (tests/test_03_shop.py:736) — presumed to populate `state.user_info["gold"/"gems"]`, since those keys are read immediately after; its internals are in `utils/helpers` and were not inspected for this doc.
10. `wallet_data = get_wallet_from_data(unity_driver)` (tests/test_03_shop.py:739) — Unity in-memory `UserManager` read (same `utils/helpers.py` helper documented for Lucky Cards: calls `UserManager.GetGold`/`GetGems`/`GetPips` via AltTester `call_static_method`).
11. `wallet_db = get_user_wallet(player_id) if player_id else {}` (tests/test_03_shop.py:742-749) — the only MongoDB read in this file.
12. Logs a three-way comparison — UI (`state.user_info`) vs. Data (Unity in-memory) vs. DB (MongoDB) for both Gold and Gems — purely informational, no assertion (tests/test_03_shop.py:751-768).
13. Returns `unity_driver` only (tests/test_03_shop.py:770).

### `purchase_all_lootboxes(unity_driver, driver=None)` (tests/test_03_shop.py:219-500)
14. Determines subset vs. full the same way as packs (`run_type`/`is_subset`, :232-233); the filter is applied per-pack inside the loop (:244-246).
15. For each `(name, path)` in `LOOTBOX_PACKS` (Common x1/x3, Legendary x1/x3), skipped if excluded by the subset filter (tests/test_03_shop.py:241-246): up to 2 attempts (`range(2)`, tests/test_03_shop.py:250-337):
    - Find (3 s) and `safe_tap` the pack; warn+break if missing.
    - Wait for `LOOTBOX_CONFIRM` (3 s) and tap it; warn+break if missing.
    - Check `LOW_GEM_MODAL` (3 s):
      - **Present** — record a deduped `event_tracker("Popups", "Low Gem Popup", "PASS", dedup=True)`, tap `LOW_GEM_PURCHASE`, run `handle_google_play_purchase(driver)` to buy gems, `reconnect_alttester()` (break on failure), dismiss the resulting `PURCHASE_OK` popup if present, then `continue` to retry the **same** lootbox now that gems are topped up.
      - **Absent** — the purchase is considered to have gone through: `purchased = True`, `break`.
16. Records `event_tracker("Shop", f"{name} Lootbox", "PASS"/"FAIL")`; if not purchased, warns and `continue`s to the next pack, skipping reward-claiming entirely for this one (tests/test_03_shop.py:339-349).
17. Claims exactly `_lootbox_expected_screens(name)` reward screens — regex `x(\d+)` on the pack name (`x1`→1, `x3`→3, default 1 if no match, tests/test_03_shop.py:206-213) — via a loop (tests/test_03_shop.py:357-418): wait up to 10 s for `LOOTBOX_CLAIM` (warn+`continue` — not break — if missing, so a later-appearing screen can still be caught), sleep 2 s, read/accumulate `LOOTBOX_AMMO`, re-find `LOOTBOX_CLAIM` and tap it (fallback to `_tap_screen_center()` ADB tap if the element is gone by then), then poll up to 8 s for the screen to disappear before moving to the next.
18. **Final sweep** (tests/test_03_shop.py:425-477): up to 60 s repeatedly checking for a leftover `LOOTBOX_CLAIM`, `_tap_screen_center()`-dismissing it and confirming it stays gone, to guarantee no reward screen is left on-screen before returning; logs a warning but proceeds anyway if the 60 s cap is hit.
19. Returns home: up to 20 s loop calling `handle_one_popup()` + checking `HOME_BUTTON` (2 s wait per pass) and tapping it once found; warns and continues anyway if never found (tests/test_03_shop.py:483-498).
20. Returns `(unity_driver, driver)` — both possibly refreshed by `reconnect_alttester`/Google Play reconnects (tests/test_03_shop.py:500).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Bottom-nav Home icon | `HOME_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon` |
| Bottom-nav Shop icon | `SHOP_BUTTON` | `/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Shop/ShopIcon` |
| Home HUD gold counter | `HOME_GOLD_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text` |
| Home HUD gems counter | `HOME_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text` |
| Shop HUD gold counter | `SHOP_GOLD_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/coinBar/text` |
| Shop HUD gems counter | `SHOP_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/gemBar/text` |
| Home Bank icon (locker) | `HOME_BANK` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/bankWidget/scaleAdjuster/root/Overlay Parent/BankIcon/WidgetIcon/Pivot/lockerParent/lockerClosed` |
| Shop Bank card button | `SHOP_BANK` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/Bank/bg/cardContent/bankShopCard(Clone)/root/Button` |
| Gold pack buy/value/price paths (6 tiers) | `GOLD_PACKS` | List of `(name, buy_button_path, value_path, price_path)` from `_pack()/_val()/_price()` (utils/paths.py:88-116) off `_GOLD_BASE = ".../ShopScreenRevamped/.../golds/cardContent"`; tiers: Gold 4000 / 12.5K / 42K / 90K / 250K / 500K |
| Gem pack buy/value/price paths (6 tiers) | `GEM_PACKS` | Same tuple shape off `_GEM_BASE = ".../ShopScreenRevamped/.../gems/cardContent"`; tiers: 50 / 155 / 540 / 1100 / 3000 / 6000 Gems |
| Purchase result modal container | `PURCHASE_POPUP` | `/Canvas/ModalLayer/PurchaseNotifModal(Clone)/darkBG` |
| Purchase-failed icon | `PURCHASE_FAIL` | `/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/mask/failed/icon` |
| Purchase modal "Okay" (shared success/fail) | `PURCHASE_OK` | `/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/ButtonLayer/Okay Button/TouchArea` |
| Lootbox pack buy buttons (4 packs) | `LOOTBOX_PACKS` | List of `(name, path)`: Common x1, Common x3, Legendary x1, Legendary x3 (utils/paths.py:137-142) |
| Lootbox purchase confirm | `LOOTBOX_CONFIRM` | `/Canvas/ModalLayer/SorryCommonModal(Clone)/rootMain/layout/CTA_Green/TouchArea` |
| Lootbox reward ammo count text | `LOOTBOX_AMMO` | `/Canvas/ModalLayer/LootboxRewardsModal(Clone)/rootMain/scaleAdjuster/root/header/cosmeticAmmoBarHUD/text` |
| Lootbox reward "tap to continue" | `LOOTBOX_CLAIM` | `/Canvas/ModalLayer/LootboxRewardsModal(Clone)/rootMain/scaleAdjuster/root/TapToContinueButton/ctaButton` |
| Low-gem sliding popup | `LOW_GEM_MODAL` | `/Canvas/ModalLayer/LowGemSlidingPopup(Clone)` |
| Low-gem "buy gems" CTA | `LOW_GEM_PURCHASE` | `/Canvas/ModalLayer/LowGemSlidingPopup(Clone)/rootMain/safeArea/cardContent/card/bg/greenCTA/TouchArea` |
| Raw ADB dismiss tap (not an element path) | `_tap_screen_center()` | Hardcoded device coordinate `540, 1200` via `adb shell input tap` (tests/test_03_shop.py:39-47) — used because lootbox reward screens don't reliably respond to a path-targeted tap |

## Data & DB interactions
- **MongoDB**: `get_user_wallet(player_id)` from `utils.mongo_helper` (imported tests/test_03_shop.py:13, called :746-749) — the only MongoDB access in this file, called once at the very end with `state.user_info["player_id"]`. Read via `.get('gold')`/`.get('gems')` for the final log; if `player_id` is falsy, `wallet_db` is `{}` and both reads are `None`. Purely informational — never asserted against the UI/Data values.
- **Unity in-memory**: `get_wallet_from_data(unity_driver)` (`utils/helpers.py`, tests/test_03_shop.py:739) — same helper documented for Lucky Cards; reads `UserManager.GetGold`/`GetGems`/`GetPips` via AltTester's `call_static_method`.
- **UI**: `get_user_snapshot(unity_driver)` (tests/test_03_shop.py:15, 736) runs immediately before the Data/DB reads; `state.user_info["gold"/"gems"]` are read right after (:751-752), implying this call refreshes them from the UI, but its implementation was not opened for this doc.
- **Real purchases**: every pack and lootbox purchase is routed through `utils.google_play_helper.handle_google_play_purchase(driver)` — an actual Google Play purchase dialog is driven, not a stub.
- `event_tracker.record(...)` is called after every Bank/pack/lootbox/low-gem action (e.g. tests/test_03_shop.py:149, 199, 280, 339-343, 700-705) — an in-process results tracker, separate from MongoDB.

## Pass / fail criteria
- **No top-level try/except and no status dict.** Unlike `test_04_lucky_cards`, `test_shop_purchase` returns only the bare `unity_driver` object on success (tests/test_03_shop.py:770) — there is no `{"status": "PASS"/"FAIL", ...}` shape anywhere in this file. Any unhandled exception (`check_preconditions()`'s `"player_id missing"`, or `"❌ Shop button not found"` at tests/test_03_shop.py:587-590) propagates straight out of `test_shop_purchase`; the caller must treat a raised exception as FAIL and a normal return as PASS.
- Per-pack outcome is `after_gold > before_gold` / `after_gems > before_gems` (tests/test_03_shop.py:688-691) — the wallet delta is ground truth because `PURCHASE_OK` is shared between the success and fail modals and proves nothing by itself (in-code comment, :665-668).
- Per-pack and per-lootbox results are recorded only via `event_tracker.record("Shop", ..., "PASS"/"FAIL", ...)` calls (tests/test_03_shop.py:700-705, 339-343) — a pack that doesn't credit currency, or a lootbox whose purchase never completes, is logged as `"FAIL"` for that item **without** raising or stopping the test; the loop simply continues to the next pack/lootbox.
- A missing buy button, missing confirm button, or missing reward screen is logged as a warning and skipped, also without raising.
- Net effect: `test_shop_purchase` can return normally (i.e. "pass" at the function level) even if every pack and lootbox purchase failed to credit currency — failure visibility lives entirely in the `event_tracker` records and console warnings, not in the function's return value or an exception.

## Notes & known flakiness
- `PURCHASE_OK` is the same button for both the purchase-success and purchase-fail modals (in-code comment, tests/test_03_shop.py:665-668); dismissing it confirms only that a modal was closed, never the purchase outcome.
- The low-gem retry in `purchase_all_lootboxes` allows at most one extra Google Play gem purchase per lootbox pack (`for attempt in range(2)`, tests/test_03_shop.py:252) before giving up on that pack.
- `wait_for_gold_update()` (tests/test_03_shop.py:80-104) declares the balance "stable" after 3 consecutive non-increasing polls (0.5 s apart) within an 8 s budget — an unusually slow bank-credit animation could be read as final before it has actually finished crediting.
- The final lootbox sweep has a 60 s hard cap (tests/test_03_shop.py:434) and only warns (does not fail) if a reward screen is still present afterward — a genuinely stuck screen here would desync whatever runs next rather than fail this test loudly.
- `check_preconditions()` only checks `player_id`, not `run_type`; an unset `run_type` silently defaults to `"complete"` (subset packs) via `state.get("run_type", "complete")` (tests/test_03_shop.py:601, 232).
- `handle_bank_if_available()` has no explicit final `return` — if neither `HOME_BANK` nor `SHOP_BANK` is found, it falls off the end and returns `None` implicitly. The caller only checks `bank_location != "shop"` (tests/test_03_shop.py:578), so a fully-missing bank is treated the same as `"home"` for control flow (the Shop still gets opened next).
- `_lootbox_expected_screens()` (tests/test_03_shop.py:206-213) defaults to expecting 1 reward screen for any pack name that doesn't match `x<N>` — currently all 4 `LOOTBOX_PACKS` names do match, so this default path isn't exercised today.
- Several imports are unused within this file itself: `AltDriver`, `reconnect_appium_no_launch`, `UIA2_CRASH_SIGNAL` (tests/test_03_shop.py:4-9), and `clear_all_popups` (tests/test_03_shop.py:14) are imported but never referenced in the code shown here — they may be used only for side effects of import or by other modules.
- `PACKAGE_NAME` / `ACTIVITY_NAME` (tests/test_03_shop.py:30-31) are defined but not referenced anywhere in this file.
- This test buys real/sandbox currency on every run: the `"iap"` run type purchases all 6 gold packs, all 6 gem packs, and all 4 lootbox packs (plus any low-gem top-ups triggered along the way) in a single execution.
