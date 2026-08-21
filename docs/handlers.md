# Handlers

`tests/handlers/` holds small, single-purpose modules that each detect and
dismiss (or fully play through) one specific popup or onboarding flow, so a
test can get back to a stable, known screen and keep going. `tests/handlers/__init__.py`
is empty — there are no package-level re-exports, so every consumer imports
the specific submodule it needs (e.g. `from tests.handlers import permissions_handler`
or `from tests.handlers.daily_handler import is_present, handle`).

**The common contract.** Most handlers expose two functions with the same
shape: `is_present(unity_driver, driver=None)` → truthy/`False` (or a
found element / `None`), and `handle(unity_driver, driver=None)` → performs
the taps/flow. `unity_driver` is the AltTester/Unity driver (used to find
and tap in-scene UI); `driver` is the Appium driver (used for native
Android UI). In practice the convention is **not** fully uniform — this doc
calls out every deviation found while reading the code:

- `permissions_handler.py` inverts the pattern entirely: `driver` is
  required (no default) and is the one actually used; `unity_driver` is
  accepted but never touched. This is because native Android permission
  dialogs live outside Unity's scene graph, so only Appium can see them.
- `ftue_handler.py`, `league_handler.py`, and `facebook_handler.py` all
  declare `is_present(unity_driver, driver)` (and `league_handler`/
  `facebook_handler` also `handle(unity_driver, driver)`) with **no
  default** for `driver`, even though they never use it.
- `piggy_bank_handler.handle()` returns a `(unity_driver, driver)` tuple
  instead of `True`/`False`, since a purchase can force a driver
  reconnect.
- `league_handler.handle()` returns nothing (implicit `None`).
- In most handlers the `driver` parameter is simply accepted and unused
  dead weight — only `permissions_handler.py` and `piggy_bank_handler.py`
  actually do anything with it.

**How the registry drives them.** `handlers_registry.py` builds an ordered
list, `HANDLERS`, of handler modules. `utils/popup_handler.py::run_handlers()`
walks that list, calling `is_present(unity_driver, driver)` on each and, on
the first truthy result, its `handle(unity_driver, driver)` — first match
wins, then it stops. However, `run_handlers()` is only actively invoked
from `tests/test_08_season_pass.py`; the call to it from inside
`utils/popup_handler.py::handle_one_popup()` is commented out, so the rest
of the framework's generic popup clearing (`handle_one_popup`,
`clear_all_popups`, `wait_for_safe`) runs on a separate, hard-coded
`POPUP_PRIORITY` path list instead and never touches this registry. Several
handlers are also imported and called directly by name in specific tests,
bypassing the registry altogether — see each handler's "Used by / notes"
below. Two modules in this directory (`piggy_bank_handler.py`,
`info_screen_handler.py`) aren't in the registry at all and, as far as a
repo-wide search shows, aren't called by anything else either.

At a glance:

| Module | In `HANDLERS` list? | Called directly by a test? |
|---|---|---|
| `permissions_handler.py` | Yes | Yes — `test_01_guest_login.py` |
| `beach_buddies_handler.py` | Yes | Yes — `test_01_guest_login.py` |
| `daily_handler.py` | Yes | Yes — `test_01_guest_login.py`, `test_08_season_pass.py` |
| `facebook_handler.py` | Yes | No |
| `album_ftue_handler.py` | Yes | Yes — `test_01_guest_login.py` |
| `ftue_handler.py` | Yes | No |
| `league_handler.py` | Imported, but commented out of the list | No |
| `piggy_bank_handler.py` | No | No (equivalent flow reimplemented inline in `test_05_piggy_bank.py`) |
| `info_screen_handler.py` | No | No |

## `tests/handlers/handlers_registry.py`

**Detects:** N/A — this module isn't a popup handler itself; it's the
lookup table other code imports to get the ordered handler list.

**Behaviour:** Imports seven handler modules (`daily_handler`,
`album_ftue_handler`, `facebook_handler`, `league_handler`,
`permissions_handler`, `ftue_handler`, `beach_buddies_handler`) and defines
`HANDLERS`, a plain list consumed elsewhere as an ordered, first-match-wins
sequence. `league_handler` is imported but commented out of the `HANDLERS`
list (`#league_handler,`), so it's excluded from anything that iterates
`HANDLERS`. The active order is: `permissions_handler → beach_buddies_handler
→ daily_handler → facebook_handler → album_ftue_handler → ftue_handler`.
`piggy_bank_handler` and `info_screen_handler` aren't imported here at all.

**Signature:** No functions — module-level constant `HANDLERS: list[module]`.

**Used by / notes:** Consumed by `utils/popup_handler.py::run_handlers()`,
which lazy-imports `HANDLERS` via a local `_get_handlers()` (to avoid a
circular import) and iterates it as described above. `run_handlers()` is
only actively called from `tests/test_08_season_pass.py` (three call sites,
each as a fallback after `handle_one_popup()` finds nothing left to close).
See the intro above for why this means the registry sits outside the
framework's main popup-clearing path.

## `tests/handlers/daily_handler.py`

**Detects:** The Daily Login modal's claim button —
`/Canvas/ModalLayer/DailyLoginModal(Clone)/rootMain/claimButton` (8s wait).

**Behaviour:**
1. Reads `player_id` from `state.user_info`. If present, fetches a
   pre-claim snapshot from Mongo via `get_daily_info_from_db()`
   (`utils.mongo_helper.get_user_from_db`): login streak, the claimable
   login-streak "giftbox" list, and current gold/gems. Without a
   `player_id` it defaults to day 1 / no giftbox / 0-0.
2. Computes the active reward day as `((login_streak or 1) % 7) or 7` and
   looks up expected gold/gems/cosmetic from the local `DAILY_REWARDS`
   table (days 1–7; day 7 = 2000 gold + 10 gems + "Cowboy Pawn"). If any
   streak-giftbox rewards are claimable, looks up the matching entry in
   `GIFTBOX_REWARDS` (indexed by `len(giftbox_claimable) - 1`) and logs the
   combined expected totals.
3. Waits (5s) for the claim button and taps it; if missing, logs a warning
   and returns `False` immediately.
4. Waits (5s) for a `GiftBoxRewardModal` collect button and taps it if
   present, else logs "no giftbox today".
5. Waits (5s) for a `PawnRewardsModal` (cosmetic reward screen); if shown,
   tries the Equip button (3s), falling back to the "Later" button (3s) if
   Equip isn't found.
6. After a settle delay, reads the home-HUD gold/gems text (`HOME_GOLD` /
   `HOME_GEMS` paths) with its own local `fast_text`/`parse_amount`
   helpers, stores the parsed values via `state.set_user_info`, records
   each non-zero reward via `state.add_reward(...)`, logs a summary, calls
   `event_tracker.record("Popups", "Daily Login", "PASS")`, and returns
   `True`.

**Signature:** `is_present(unity_driver, driver=None)` /
`handle(unity_driver, driver=None)`. `driver` is accepted but never
referenced in either function body.

**Used by / notes:** Imported directly (bypassing the registry) by
`tests/test_01_guest_login.py` (`reach_home()` loop, plus a post-restart
check inside `test_guest_login()`) and by `tests/test_08_season_pass.py`
(post-restart daily-login check). Also reachable indirectly through
`handlers_registry.HANDLERS` → `run_handlers()`. Defines a
`get_wallet_from_db_after()` helper that is never called anywhere
(including within this file) — looks like leftover dead code from an
earlier post-claim comparison.

## `tests/handlers/album_ftue_handler.py`

**Detects:** The "new album" card-collection popup — `is_present` checks
`/Canvas/ModalLayer/CardCollectionNewAlbumPopup(Clone)/root/content/visitAlbumButton/TouchArea`
(0.5s wait; this is also the "Visit Album" tap target used in `handle`).

**Behaviour:** A fixed 6-step walkthrough; each step waits up to 8s and
(other than step 1) logs a warning and returns `False` if its element isn't
found:
1. Tap "Visit Album". If this specific tap target is missing, also records
   `event_tracker.record("FTUE", "Album FTUE", "FAIL")` before returning.
2. Tap the pack-open widget inside `CommonNudgeModal`.
3. Tap the pack icon on the pack-open screen.
4. Tap the close button on the card pack-open screen.
5. Call `popup_handler.fast_clear_popups(unity_driver)` to clear any
   incidental popups.
6. Loop for up to 30s, alternating `handle_one_popup(unity_driver)` with a
   check for the Home icon; taps Home and breaks once found, otherwise
   logs a warning and returns `False` after the timeout.

On full success, records `event_tracker.record("FTUE", "Album FTUE", "PASS")`
and returns `True`.

**Signature:** `is_present(unity_driver, driver=None)` /
`handle(unity_driver, driver=None)`. `driver` is accepted but unused
throughout — all waits/taps go through `unity_driver` via
`utils.ui_helpers.wait_for_safe`/`safe_tap`.

**Used by / notes:** Imported directly by `tests/test_01_guest_login.py`'s
`reach_home()` loop (checked after Daily Login, before Beach Buddies) and
reachable via `handlers_registry.HANDLERS` → `run_handlers()`. Also calls
`utils.popup_handler.handle_one_popup`/`fast_clear_popups` internally, so it
indirectly exercises the `POPUP_PRIORITY` path list even though it isn't a
`POPUP_PRIORITY` entry itself.

## `tests/handlers/beach_buddies_handler.py`

**Detects:** The Beach Buddies (Co-Op event) start popup — `BB_START_MODAL`
= `/Canvas/ModalLayer/CoOpEventStartPopup(Clone)/darkbg` (2s wait). All
paths are the `BB_*` constants imported from `utils/paths.py`.

**Behaviour:** A linear 12-step flow. Only step 1 aborts the whole handler
on failure; every other step logs a warning and simply falls through to the
next step if its element isn't found:
1. Tap "Let's Go" (`BB_LETS_GO`) — on failure, records
   `event_tracker.record("FTUE", "Beach Buddies", "FAIL")` and returns `False`.
2. Tap the Invite-Friend icon (`BB_INVITE_ICON`).
3. If the Invite Friends modal (`BB_INVITE_MODAL`) is up, tap Accept
   (`BB_ACCEPT_INVITE`).
4. Tap Castle 1 (`BB_CASTLE_1`).
5. If a Free-Ammo modal (`BB_FREE_AMMO_MODAL`) appears, read the ammo count
   (`BB_FREE_AMMO_COUNT`, via `utils.helpers.fast_text`/`parse_amount`) and
   tap "Awesome" (`BB_AWESOME_BTN`).
6. Tap the FTUE spin wheel (`BB_FTUE_SPIN_WHEEL`).
7. Tap the spin multiplier (`BB_SPIN_MULTIPLIER`).
8. Tap the spin wheel again (`BB_SPIN_WHEEL`), waiting 5s for the spin
   animation.
9. Close the castle-build screen (`BB_CLOSE`).
10. Tap Castle 2 (`BB_CASTLE_2`).
11. If the Invite Friends modal reappears, tap Send (`BB_SEND_INVITE`),
    then Send All (`BB_SEND_ALL`), then close it (`BB_INVITE_CLOSE`). A code
    comment notes that a "deny friend invite" step was intentionally removed
    here, because denying an invite consumed one the test later needs to
    open the final castle.
12. Close the Beach Buddies screen (`BB_CLOSE`).

Regardless of which optional steps after step 1 were skipped, it finishes by
recording `event_tracker.record("FTUE", "Beach Buddies", "PASS")` and
returning `True`.

**Signature:** `is_present(unity_driver, driver=None)` /
`handle(unity_driver, driver=None)`. `driver` is accepted but unused. A
module-level `_tap_center()` helper (raw ADB tap at device coords 540,1200
via `state.get("device_id")`) is defined but never called anywhere in
`handle()` — dead code.

**Used by / notes:** Imported directly by `tests/test_01_guest_login.py`'s
`reach_home()` loop (checked after Album FTUE) and reachable via
`handlers_registry.HANDLERS` → `run_handlers()`. Note `utils/paths.py` also
defines a separate, more elaborate Beach Buddies path (`BB_ICON`,
`BB_CASTLES` dict, autospin, milestone/giftbox/event-complete screens) for
the dedicated `tests/test_12_beachbuddies.py` full-play test — this handler
only covers the short first-time FTUE popup, not that full event loop.

## `tests/handlers/ftue_handler.py`

**Detects:** The Build FTUE modal's skip button —
`/Canvas/ModalLayer/BuildFTUEModal(Clone)/skipGrp/closeCTA/TouchArea` (2s
wait in `is_present`, wrapped in a bare `try/except` that returns
`True`/`False`).

**Behaviour:** `handle()` re-waits for the same skip button (5s) and taps
it, recording `event_tracker.record("FTUE", "Build FTUE", "PASS")` on
success or `"FAIL"` (with the exception logged) if the wait/tap raises.

**Signature:** `is_present(unity_driver, driver)` — `driver` has **no
default** and is unused; `handle(unity_driver, driver=None)` — `driver`
unused, and the function returns nothing (implicit `None`) rather than
`True`/`False`.

**Used by / notes:** Only reachable via `handlers_registry.HANDLERS` →
`run_handlers()` — no test file imports `ftue_handler` directly. Because
`is_present` requires `driver` positionally, `run_handlers()`'s call style
(`handler.is_present(unity_driver, driver)`) works, but calling it with a
single argument would raise `TypeError`.

## `tests/handlers/permissions_handler.py`

**Detects:** Native Android runtime-permission dialogs (OS-level, outside
Unity's scene graph) by Appium element `id`, not AltTester path — a fixed
`ALLOW_IDS` list covering the Android 10/11/12 permission-allow button
variants, the older `packageinstaller` allow button, a `continue_button`,
and a generic `android:id/button1` OK.

**Behaviour:** `is_present` loops `ALLOW_IDS`, calling
`driver.find_elements("id", btn_id)` for each, and returns the first found
element (or `None`). `handle()` also loops all `ALLOW_IDS`, but clicks
**every** id that currently matches (not just the first), via
`elements[0].click()`, sleeping 1s after each click, and returns `True` if
anything was clicked. `start_permission_watcher(unity_driver, driver,
stop_event)` runs `handle()` on a 2s cycle inside a
`while not stop_event.is_set()` loop, swallowing exceptions — a
background-thread variant of the same logic.

**Signature:** `is_present(unity_driver, driver)` /
`handle(unity_driver, driver)` — both require `driver` positionally (no
default), and **`unity_driver` is accepted but never used** anywhere in
this module. This is the one handler that inverts the framework's usual
"AltTester primary, Appium secondary" pattern, since native permission
dialogs aren't part of the Unity scene graph AltTester inspects.

**Used by / notes:** Called two different ways: (1) directly in
`tests/test_01_guest_login.py`'s `test_guest_login()`, in a
`for _ in range(5)` retry loop right after tapping the Guest button; (2) via
`handlers_registry.HANDLERS` (first in the list) → `run_handlers()`.
Separately, `utils/device_helpers.py::handle_permissions(driver)` duplicates
the same `ALLOW_IDS`/click logic independently — that's what
`reach_home()` in `test_01_guest_login.py` actually calls on every loop
iteration, not this module. `start_permission_watcher` is defined but not
called anywhere else in the repo.

## `tests/handlers/piggy_bank_handler.py`

**Detects:** The Piggy Bank modal's Buy button — `PIGGY_BANK_BUY` =
`/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/content/ClaimButton/TouchArea`
(2s wait). Per an in-file comment, `is_present` is deliberately keyed only
on the Buy button so it returns `False` once the bank has already been
bought that session — a reappearing modal after purchase is left for the
generic `POPUP_PRIORITY` close entry instead.

**Behaviour:**
1. Lazy-imports `handle_google_play_purchase`/`reconnect_alttester` from
   `utils.google_play_helper` (avoids a circular import at module load).
2. Falls back to `state.get("appium_driver")` if no `driver` was passed; if
   still `None`, just closes the modal (`PIGGY_BANK_CLOSE`) without buying
   and returns `(unity_driver, None)`.
3. Calls `popup_handler.ignore_popup(PIGGY_BANK_CLOSE)` so the generic
   `POPUP_PRIORITY` clearing doesn't auto-close the modal mid-purchase.
4. Taps Buy (8s wait); if not found, closes the modal and returns.
5. Runs the Google Play purchase (`handle_google_play_purchase(driver)`),
   records `event_tracker.record("Shop", "Piggy Bank", "PASS"/"FAIL")`,
   reconnects AltTester (`reconnect_alttester`, since Google Play backgrounds
   the app), and republishes the refreshed `unity_driver`/`driver` into
   `state`.
6. Waits (15s) for the Piggy Bank claim screen (`PIGGY_BANK_CLAIM_SCREEN`)
   and taps it to collect.
7. If the Piggy Bank modal reappears, closes it (`PIGGY_BANK_CLOSE`).
8. In a `finally` block, calls `popup_handler.unignore_popup(PIGGY_BANK_CLOSE)`
   so future appearances go back to being auto-closed.

**Signature:** `is_present(unity_driver, driver=None)` /
`handle(unity_driver, driver=None)`. Unlike every other handler in this
doc, `handle()` returns a **`(unity_driver, driver)` tuple**, not
`True`/`False`/`None` — per the module's own comment, callers that can't
unpack the return value are expected to re-read
`state.get("unity_driver")`/`state.get("appium_driver")` instead.

**Used by / notes:** Not imported by `handlers_registry.py`, and a
repo-wide search for `piggy_bank_handler` turns up nothing outside this
file. `tests/test_05_piggy_bank.py` (whose own docstring header calls
itself `test_06_piggy_bank.py` — a stale filename reference) implements the
same Buy → Google Play → claim flow independently/inline rather than
calling this module. As far as this repo shows, this handler is currently
unreachable/standalone.

## `tests/handlers/league_handler.py`

**Detects:** Either the League info/FTUE modal
(`/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg`) or the League reward-claim
screen (`/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/darkBG`), each
with a 1s wait.

**Behaviour:** Unlike the other handlers, `handle()` runs its own internal
loop for up to 20s rather than a single pass. Each iteration first
re-checks for the reward-claim screen and, if present, taps its "continue"
button (`LeagueRewardClaimScreen(Clone)/.../buttonPrimaryCTA_Stroked/text`,
2s wait), waits 3s, and loops again. Otherwise it checks for the info/FTUE
screen: tries a dedicated close button
(`LeagueModal(Clone)/.../closeCTA/touchArea`, 2s wait) first, falling back
to a normalized-center tap (`unity_driver.tap(0.5, 0.5)`) if no close button
is found. The loop exits as soon as one pass finds nothing left to handle;
otherwise it exits on the 20s timeout with a logged warning. There is no
`event_tracker.record(...)` call anywhere in this handler, unlike every
other one in this doc.

**Signature:** `is_present(unity_driver, driver)` /
`handle(unity_driver, driver)` — both require `driver` positionally (no
default) and never use it. `handle()` returns nothing (implicit `None`), so
it can't be read as a boolean success/failure signal the way most other
handlers can.

**Used by / notes:** Imported by `handlers_registry.py` but **commented out
of the `HANDLERS` list**, so it does not currently run via `run_handlers()`;
no other file references `league_handler` at all. It is effectively
disabled/unwired in this snapshot of the repo.

## `tests/handlers/facebook_handler.py`

**Detects:** The "Connect to Facebook" modal, via two-tier detection in
`is_present`: (1) exact path
`/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/darkbg` (0.5s wait); (2)
fallback — scan every `CanvasGroup` component
(`unity_driver.find_objects_by_component("CanvasGroup")`) for one whose
`.name` contains "facebook" or "connecttofacebook".

**Behaviour:** `handle()` retries up to 3 times. Each attempt first tries
the exact close-button path
(`ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea`, 1s wait)
and taps it if found; otherwise it falls back to scanning every `Button`
component (`find_objects_by_component("Button")`) for one whose name
contains "close", "cancel", or "no", and taps the first match. Returns
`True` (after a 1s sleep) on the first successful tap via either path, or
`False` with a warning logged if all 3 attempts fail.

**Signature:** `is_present(unity_driver, driver)` /
`handle(unity_driver, driver)` — both require `driver` positionally (no
default) and never use it. Module-level constants `PRIORITY = 1` and
`HANDLER_NAME = "Facebook Connect Popup"` are defined but not read anywhere
else in the repo — `handlers_registry.HANDLERS` ordering is plain Python
list order, not driven by this `PRIORITY` value.

**Used by / notes:** Only reachable via `handlers_registry.HANDLERS` →
`run_handlers()` — no test file imports `facebook_handler` directly. Its
close path is duplicated in `utils/popup_handler.py`'s `POPUP_PRIORITY`
HIGH group (`ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea`),
so the generic popup clearing used throughout the rest of the suite can
close this same modal without ever going through this handler.

## `tests/handlers/info_screen_handler.py`

**Detects:** Any of the "tap anywhere to close" info overlays listed in
`utils/paths.py::INFO_SCREENS` (a list of `(friendly_name, path)` tuples) —
currently Leagues Info, Leaderboard Info, Treasure Island Info, BumpToSpin
Info, Beach Buddies Info, and Sky Rush Info. `is_present` checks each path
with a 1s wait and returns `True` on the first hit.

**Behaviour:** `handle()` re-scans `INFO_SCREENS` in order and, for the
first path found, taps that object directly
(`utils.popup_handler.safe_tap(unity_driver, obj)` — a plain `obj.tap()`
with one retry-after-popup-clear on exception), records
`event_tracker.record("Info Screens", name, status="PASS", dedup=True)`,
and returns `True`. Returns `False` if none of the `INFO_SCREENS` paths are
found.

**Signature:** `is_present(unity_driver, driver=None)` /
`handle(unity_driver, driver=None)`. `driver` is accepted but unused.

**Used by / notes:** Not imported by `handlers_registry.py`, and a
repo-wide search for `info_screen_handler` turns up nothing outside this
file — it appears unreachable/standalone. Notably, `utils/popup_handler.py`
implements an independent, more careful mechanism for these same
`INFO_SCREENS` paths: its `close_info_screen()` deliberately avoids tapping
the matched path object, because — per that function's own comment — these
screens have multiple stacked overlay layers, and tapping a specific path
like `/bg` "lands on the wrong layer" so "Unity's EventSystem never receives
the event and the screen stays open"; instead it taps the topmost object at
screen-centre via `find_object_at_coordinates` (with two further fallback
tap methods). `close_info_screen()` is what `handle_one_popup()` actually
calls for any `INFO_SCREEN_PATHS` match, and what `test_02_happy_flow.py`,
`test_12_beachbuddies.py`, `test_13_treasureisland.py`,
`test_14_bumptospin.py`, and `test_15_puzzletheatre.py` call directly. In
other words, this handler's direct-tap approach is the exact technique
`popup_handler.py` was written to avoid for these screens — plausibly why
it was never wired into the registry.
