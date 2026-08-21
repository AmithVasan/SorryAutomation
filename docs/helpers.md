# Helpers

These are the reusable helper modules that `tests/*.py` and `tests/handlers/*.py`
import and call directly — UI wait/tap primitives with automatic popup
dismissal, wallet/profile reading, run-report event logging, and two
out-of-band device/DB utilities. None of them are pytest fixtures or CLI
entry points; every function here is invoked inline from test/handler code.

## `utils/helpers.py`

**Purpose:** Reads player wallet and profile data — either off Unity UI text
(TextMeshPro) or straight from the in-memory `UserManager` object via
AltTester RPC — and assembles a full profile snapshot into the shared
`state` singleton (`utils/state_manager.py`).

**Key functions:**
- `safe_text(obj)` — Reads the `TMPro.TextMeshProUGUI` `"text"` component property off an AltTester object; returns `None` if `obj` is falsy, the value is `None`/`""`/`"N/A"`, or the call raises.
- `fast_text(unity_driver, path, timeout=2)` — `unity_driver.wait_for_object(By.PATH, path, timeout)` then `safe_text(obj)`; returns `None` on not-found or any exception.
- `parse_amount(text)` — Parses UI strings like `"1.2K"`, `"3M"`, `"500"` (strips commas/spaces, case-insensitive) into an `int`, applying `K`/`M`/`B` multipliers (1e3/1e6/1e9); returns `0` for falsy input or a parse failure.
- `get_wallet_from_data(unity_driver)` — Reads gold/gems/pips directly from Unity's `UserManager` (the "Data" source, independent of UI text): tries `call_static_method("UserManager", "Get{Gold,Gems,Pips}", "Assembly-CSharp", [], [])` first, falls back to `find_object(By.COMPONENT, "UserManager")` + `call_component_method(...)` if the static call fails; logs the result and returns `{"gold": int|None, "gems": int|None, "pips": int|None}`.
- `get_user_snapshot(unity_driver)` — Opens the profile screen (`wait_for_safe` up to 5s for `PROFILE_BUTTON`; **raises** `Exception` if it never appears), taps it, reads name/country/ID/level/xp/equipped-pawn via `fast_text`, strips a `"PLAYER ID:"` prefix off the ID, closes the profile (`wait_for_safe` up to 3s for `PROFILE_CLOSE`, taps if found), then reads gold/gems/hammer off the home screen (`parse_amount(fast_text(...))`). Writes every field into `state` via `state.set_user_info(key, value)`, also calls `get_wallet_from_data` for a logged comparison, and logs a full summary block. Returns `None` — all results land in `state` (and the log), not in a return value. Side effects: two taps, ~1.5s of sleeps, mutates global `state`.

**Used by / notes:** Imports `wait_for_safe` from `utils.popup_handler`, so popup recovery is active while it waits for the profile button/close button. `get_user_snapshot` and `get_wallet_from_data` are called from nearly every test module (`test_01`, `03`, `04`, `06`–`15`) and from `tests/handlers/beach_buddies_handler.py`. Callers should expect `get_user_snapshot` to raise rather than return a sentinel if the profile button is missing.

## `utils/popup_handler.py`

**Purpose:** The central, thread-safe auto-popup-dismissal engine. Holds a
priority-ordered catalogue of known modal paths (`POPUP_PRIORITY`) and
provides the "safe" wait/tap primitives that almost all tests build their
flows on top of — waiting for or tapping a target element while
transparently closing any incidental popup that gets in the way. Per-thread
state (ignored-popup set, re-entrancy guard) is kept in `threading.local()`
so parallel per-device worker threads never interfere with each other.

**Key functions (core API):**
- `wait_for_safe(unity_driver, by, value, timeout=6, driver=None)` — Polls `unity_driver.find_object(by, value)` every 0.05s until found or `timeout` (default **6s**) elapses. If more than **3s** have passed since the last recovery attempt, calls `handle_one_popup(unity_driver, driver)` to try to clear whatever might be blocking the target, then resets that 3s timer (first recovery fires ~3s in, not on the first loop pass). Returns the found object, or `None` (+ logs a warning) on timeout.
- `safe_tap(unity_driver, obj, driver=None)` — Raises immediately if `obj` is `None`. Taps and sleeps 0.1s; if the tap raises, logs a warning, calls `handle_one_popup(unity_driver, driver)` once, then retries the tap exactly once more — logging an error and re-raising if that retry also fails.
- `handle_one_popup(unity_driver, driver=None)` — Scans `POPUP_PRIORITY` groups in order (CRITICAL → HIGH → MEDIUM → LOW), skipping any path in the calling thread's ignored set, probing each with `unity_driver.wait_for_object(By.PATH, path, timeout=0.05)` (a fast existence check, not a real wait). On the first match: taps it directly, unless the path is in `INFO_SCREEN_PATHS`, in which case it calls `close_info_screen(unity_driver)` instead; sleeps 0.2s; records the closure via `event_tracker.record_popup(path)` (deduped, errors swallowed); returns `True`. Closes **at most one** popup per call; returns `False` if nothing matched. A call to `run_handlers(...)` at the top of this function exists in the source but is commented out, so the `HANDLERS` registry is *not* invoked from inside `handle_one_popup` today.
- `clear_all_popups(unity_driver, driver=None, timeout=5)` — Loops `handle_one_popup` (sleeping 0.1s between calls) until it returns `False` (nothing left) or `timeout` (default **5s**) is exceeded. Returns `True` if fully cleared, `False` (+ logs a warning) if popups were still being found when the timeout hit.
- `close_info_screen(unity_driver)` — Dismisses info/overlay screens whose stacked layers make a path-targeted tap land on the wrong layer, by tapping the topmost rendered element at a hardcoded screen centre (`x=540, y=1200`, i.e. a 1080×2400 canvas). Tries, in order: (1) `find_object_at_coordinates` + tap, (2) `unity_driver.tap(coords)`, (3) `begin_touch`/`end_touch`; sleeps 1s after any success; returns `True` on first success, `False` (+ logs a warning) if all three raise.

**Other functions:**
- `safe_find_and_tap(unity_driver, by, value, timeout=6)` — `wait_for_safe` then raises `Exception` if not found, else `safe_tap`s and returns the object. Not imported anywhere else in the repo today (verified by repo-wide search) — currently unused.
- `is_ui_blocked(unity_driver)` — Read-only version of `handle_one_popup`'s scan (same 0.05s probes over `POPUP_PRIORITY`, skipping ignored paths): returns `True`/`False` for "is a known popup present" without tapping/closing anything. Also unused elsewhere in the repo today.
- `ignore_popup(path)` / `unignore_popup(path)` / `clear_ignored_popups()` — Add/remove/clear entries in the calling thread's ignored-paths set, consulted by `handle_one_popup`, `fast_clear_popups`, and `is_ui_blocked`. Used heavily by tests (e.g. `test_02`, `05`, `07`, `08`, `14`, `tests/handlers/piggy_bank_handler.py`) to let one specific modal stay open during a flow the test wants to drive manually, then re-enable auto-closing after.
- `fast_clear_popups(unity_driver)` — Cheaper one-shot variant: a single pass over only the CRITICAL+HIGH groups (`POPUP_PRIORITY[:2]`), using a plain `find_object` (no wait) per path; taps and returns `True` on the first hit, `False` if none found. Ignores `INFO_SCREEN_PATHS` (always a plain `.tap()`) and does not call `event_tracker`. Only used by `tests/handlers/album_ftue_handler.py`.
- `run_handlers(unity_driver, driver=None)` — Iterates `HANDLERS` (lazily imported from `tests.handlers.handlers_registry` to avoid a circular import), calling each handler's `is_present(unity_driver, driver)` and, on the first `True`, its `handle(unity_driver, driver)`, then returns `True`. Guarded by a thread-local `handler_active` flag so re-entrant calls short-circuit to `False`. Per-handler exceptions are caught, logged, and skipped. `HANDLERS` currently = `[permissions_handler, beach_buddies_handler, daily_handler, facebook_handler, album_ftue_handler, ftue_handler]` (`league_handler` is commented out of that list). Called directly by `test_08_season_pass.py` as a fallback whenever `handle_one_popup` returns `False`; not called from within this module's own functions.
- `POPUP_PRIORITY` — Module-level list of 4 priority tiers (CRITICAL/HIGH/MEDIUM/LOW), each a list of hardcoded Unity hierarchy paths; every scan function above walks it in this order. Some entries carry comments noting a test intentionally `ignore_popup`s them during a purchase flow (e.g. `BumpToSpinRoyalPassModal` in test_14, `PiggyBankModal` in test_06).
- `INFO_SCREEN_PATHS` — Module-level set built from `utils.paths.INFO_SCREENS` (falls back to an empty set if that import fails) plus one hardcoded extra (`DuelEventInfoModal(Clone)/bg`). Determines which `POPUP_PRIORITY` paths get the `close_info_screen()` tap-topmost-layer treatment instead of a plain tap.

**Used by / notes:** The most-imported utils module — used directly by nearly every file in `tests/` and `tests/handlers/`, plus `utils/helpers.py` and `utils/session_detector.py`. Across every call site found in the repo, the optional `driver` parameter (meant for the Appium native driver, e.g. for `permissions_handler`) is never actually supplied — callers only ever pass `unity_driver`, so it is effectively always `None` in current usage.

## `utils/ui_helpers.py`

**Purpose:** A minimal wait/tap helper set with the *same function names* as
part of `popup_handler.py`'s API, but deliberately simpler — no popup
auto-recovery, no retry-on-failure.

**Key functions:**
- `wait_for_safe(unity_driver, by, value, timeout=6)` — A single `unity_driver.wait_for_object(by, value, timeout=timeout)` call wrapped in try/except; returns the object or `None`. No polling loop and no popup-recovery retries (unlike `popup_handler.wait_for_safe`).
- `safe_tap(unity_driver, obj)` — Raises if `obj` is `None`; otherwise taps, sleeps 0.2s; on exception logs an error and re-raises immediately — no retry or popup-clear step (unlike `popup_handler.safe_tap`).
- `fast_wait(unity_driver, path, timeout=1)` — `unity_driver.wait_for_object(By.PATH, path, timeout=timeout)` wrapped in try/except; returns the object or `None`.

**Used by / notes:** Only imported by `tests/handlers/album_ftue_handler.py` (`wait_for_safe`, `safe_tap`) and `tests/handlers/league_handler.py` (`wait_for_safe`). **Gotcha:** `wait_for_safe`/`safe_tap` exist in both this module and `popup_handler.py` with different behavior (no auto popup-dismissal here); importing from the wrong one silently changes retry/recovery behavior. In `league_handler.py` specifically, the imported `wait_for_safe` is immediately shadowed by a locally-defined `def wait_for_safe(unity, path, timeout=2)` later in that same file, so the import there has no effect. `fast_wait` is not imported anywhere else in the repo today.

## `utils/event_tracker.py`

**Purpose:** Thread-local, zero-dependency event log used to build the
end-of-run report — tests and handlers call `record()` (or the
`record_popup()` wrapper) to note pass/fail/skip items, and the report/Slack
generator reads them back with `get_all()`.

**Key functions:**
- `record(section, name, status="PASS", detail="", dedup=False)` — Appends `{"name","status","detail"}` to this thread's `sections[section]` list (creating it on first use). `status` is a free-form convention string (`"PASS"`/`"FAIL"`/`"SKIP"`), not validated. If `dedup=True`, silently no-ops when an event with the same `name` already exists in that section.
- `record_popup(path, status="PASS")` — Shortcut for `record("Popups Surfaced", _path_to_name(path), status=status, dedup=True)`; called by `popup_handler.handle_one_popup` every time it auto-closes a popup.
- `_path_to_name(path)` *(internal)* — Converts a Unity hierarchy path to a friendly name: exact match in `POPUP_NAME_OVERRIDES` first; else takes the path segment right after `"ModalLayer"`, strips `"(Clone)"` and one trailing suffix (`StartPopup`/`InfoModal`/`MainModal`/`Modal`/`Screen`/`Popup`), then splits CamelCase into spaced words; returns the raw path unchanged if no `ModalLayer` segment exists.
- `get_all()` — Returns a shallow `dict` copy of this thread's `{section: [event, …]}` store.
- `reset()` — Clears this thread's event store.
- `merge_into(target, lock=None)` — Copies this thread's sections into a shared `target` dict (extending existing lists), holding `lock` while doing so. **Caveat:** if `lock` is omitted, a brand-new `threading.Lock()` is created for just that one call, which gives no real protection against other threads calling `merge_into` concurrently unless every caller passes the *same* shared lock object.

**Used by / notes:** `popup_handler.py` calls `record_popup`. Nearly every test file and most `tests/handlers/*.py` modules call `record()` directly. `run_this.py` (top-level runner) calls `reset()` once per run and `merge_into(shared_events, lock=events_lock)` per device thread with a shared lock, so the caveat above doesn't currently bite; `utils/slack_reporter.py` calls `get_all()` to build the report payload.

## `utils/device_helpers.py`

**Purpose:** One Appium-level helper for dismissing the native Android
OS runtime-permission dialog — this operates on the Appium `driver`
(WebDriver), not the AltTester `unity_driver` used everywhere else in this
doc.

**Key functions:**
- `handle_permissions(driver)` — Tries, in order, to find and click `com.android.permissioncontroller:id/permission_allow_button` then `.../permission_allow_foreground_only_button` via `driver.find_element("id", btn).click()`; returns `True` on the first successful click, `False` if neither is present. Per-attempt exceptions are swallowed silently (bare `except: pass`, no logging).

**Used by / notes:** Only called from `tests/test_01_guest_login.py`, once, near the start of the login flow (right after driver/app startup) — presumably to dismiss the one-time Android permission prompt before the Unity UI is reachable. No other module references it today.

## `utils/booster.py`

**Purpose:** Standalone MongoDB "god-mode" player booster — writes a
player's level/currencies directly into the database, bypassing the app UI.

**Key functions:**
- `boost_player(player_id, level=50, gold=500000, gems=25000, hammer=25000, name="NOOB")` — Opens its own `MongoClient` connection using a hardcoded placeholder connection string literal, `"YOUR_CONNECTION_STRING"` (not an env var, not config-driven), against db `sorry_users`, collection `users`. Always sets `pipPrgrsn.lvl` and `info.name`; conditionally (if not `None`) sets `wallet.gold`, `wallet.gems`, and — note the field-name mismatch — the `hammer` argument is written to the `wallet.pips` field. Matches the target document by `info.gameCode == player_id` via `update_one(...)`. Logs success if `modified_count > 0`, otherwise logs a warning to check the game code. Returns nothing.

**Used by / notes:** Not imported or called anywhere else in this repository (verified by repo-wide search) — appears to be dead/superseded code. The active test suite instead uses `utils/mongo_helper.py`'s `boost_player_level(player_id, level=50, gold=5000, gems=1050, hammer=3000, name="NOOB")` (called from `tests/test_01_guest_login.py`), which reads its connection string from the `MONGO_URI` env var via a shared client instead of a hardcoded literal. *Unclear: whether `boost_player` is an intentionally-kept template/reference or simply leftover from before `mongo_helper.py` existed.*
