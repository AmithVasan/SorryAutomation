# Utils

Infrastructure modules under `utils/` — the central AltTester element-path
registry, MongoDB player-state helpers, thread-local run state, toolchain/
environment auto-detection, Appium+AltTester driver setup, HTML/Slack
reporting, screenshot capture, device naming, and Google Play IAP handling.
Tests and handlers import these rather than duplicating paths or plumbing.

## `utils/paths.py`
**Purpose:** Central AltTester element-path registry imported across nearly
every test/handler module. Maps human-readable constant names to the
AltTester object path strings (`/Canvas/.../Node`) — and a handful of literal
ADB tap coordinates — used to find and interact with in-game UI, so a UI
change is fixed in one file instead of hunted across tests.

**Size:** ~695 lines, ~300 top-level names (306 top-level assignments
including a few private `_BASE`-style helper strings) plus 3 small helper
functions (`_pack`, `_val`, `_price`) that programmatically build the indexed
shop-card paths. Several names are lists/dicts bundling multiple sub-paths
rather than a single string (`GOLD_PACKS`, `GEM_PACKS`, `LOOTBOX_PACKS`,
`INFO_SCREENS`, `BB_CASTLES`), so the real count of distinct UI paths is
higher than the constant count.

**Categories present** (representative constants only — not exhaustive):
- **Device coordinates** — `DEVICE_COORDS` (real vs. emulator `ip_field` / `restart` tap coords for raw ADB input)
- **Navigation** — `HOME_BUTTON`, `SHOP_BUTTON`
- **Login / FTUE** — `LOGIN_SCREEN`, `GUEST_BUTTON`, `FTUE_INTRO_CINEMATIC`, `FTUE_SKIP_BUTTON`, `MATCHMAKING_SCREEN`
- **Home/Shop HUD & wallet** — `HOME_GOLD_TEXT`, `HOME_GEMS_TEXT`, `SHOP_GEMS_TEXT`
- **Profile modal** — `PROFILE_BUTTON`, `PROFILE_NAME`, `PROFILE_LEVEL`, `PROFILE_PAWN`
- **Shop / IAP** — `PURCHASE_POPUP`, `GOLD_PACKS`/`GEM_PACKS` (built via `_pack()`/`_val()`/`_price()`), `LOOTBOX_PACKS`, `HOME_BANK`/`SHOP_BANK`, `PIGGY_BANK_MODAL`
- **Legendary Pawn Sale** — `PAWN_SALE_MODAL`, `PAWN_SALE_BUY`, `HF_PAWN_ICON`
- **Lucky Cards** — `LUCKY_CARDS_ICON`, `SEND_GET_CARDS_DRAWER`
- **Season Pass** — `SEASON_PASS_ICON`, `CLAIM_ALL_PATH`, `UNLOCK_CONFIRM_BTN`
- **Low Gem popup** — `LOW_GEM_MODAL`, `LOW_GEM_PURCHASE`
- **Beach Buddies (CoOp event)** — legacy happy-flow set (`BB_START_MODAL`, `BB_SPIN_WHEEL`) plus a fuller event-play set for `test_12_beachbuddies` (`BB_CASTLES` dict, `BB_MILESTONE_CTA`, `BB_EVENT_COMPLETE_CTA`)
- **Treasure Island / Fortune Island** — lobby widget `HF_TI_*` plus a full-play set for `test_13` (`TI_ICON`, `TI_CHEST_SLOTS`, `TI_BOMB_MODAL`, `TI_REVIVE_BUTTON`)
- **Bump To Spin (BTS)** — `HF_BTS_*` plus a full-play set for `test_14_bumptospin` (`BTS_SPIN_BTN`, `BTS_TIER_ITEM_TMPL`, `BTS_ROYAL_BUY`)
- **Puzzle Theatre / Puzzle Event** — `HF_PUZZLE_*` plus a full-play set for `test_15_puzzletheatre` (`PT_BOARD_TMPL`, `PT_PIECE_BTNS`, `PT_GRAND_REWARD_COLLECT`)
- **Other Happy Flow lobby widgets** (`test_02_happy_flow.py`) — SkyRush/SoapBox, Leagues, Pie Duel, Ad Rewards, EDLP, Welcome Pack, Daily Tasks, Endless Sale, Social Lobby, e.g. `HF_SKYRUSH_ICON`, `HF_LEAGUE_RANK`, `ES_TILE_BUY_BTN`
- **City Build** — `CB_ICON`, `CB_COLLECT`, `BUILD_ACTIVE_CARD`
- **Gameplay modes** (Classic + Fire & Ice, `test_09_gameplay.py`) — `GAME_BET_CLASSIC_TAB`, `GAME_CARD_DRAW`, `GAME_FIREICE_CARD_DRAW`, `GAME_OPP_PROFILE_BTN`
- **Popups / info overlays / misc** — `INFO_SCREENS` (list of `(label, path)` tuples), `QUIT_CONFIRM`, `REWARD_SUMMARY_CTA`, `PAWN_REWARDS_MODAL`

**Notes:** No env vars; pure data module (plus 3 tiny path-builder functions).
Heavy aliasing between "happy flow" lobby-icon constants (`HF_*`) and the
dedicated per-event full-play constants (e.g. `TI_ICON = HF_TI_ICON`,
`BTS_ICON = HF_BTS_ICON`, `PT_ICON = HF_PUZZLE_ICON`) — the same UI node
often has 2 names. Beach Buddies is the exception: its legacy happy-flow set
and its full-event-play set both use the bare `BB_` prefix (distinguished
only by file position/comments), unlike TI/BTS/PT which use a dedicated
prefix alongside their `HF_*` counterpart. Unclear: the comment above
`HF_BTS_ICON` says "intentionally blank — path not yet provided", but the
constant is actually assigned a full non-empty path immediately below it —
looks like a stale comment. A few paths intentionally contain the game's own
node-name quirks preserved verbatim (a trailing space in `TI_REVIVE_BUTTON`'s
`"GreenCTA "` segment, a typo'd modal name `FortuneIslasedMainModal` in
`HF_TI_CHEST_FTUE`) — both are called out in inline comments as real, not
typos to fix.

## `utils/mongo_helper.py`
**Purpose:** Direct MongoDB read/write access to the player document, used to
boost a test account's currency/level or top up event ammo so tests don't
have to grind for state. All functions key on `{"info.gameCode": player_id}`
in `DB_NAME="sorry_users"`, `COLLECTION_NAME="users"`.

**Key functions:**
- `get_client()` — lazy singleton `MongoClient(MONGO_URI)`; raises `ValueError` if `MONGO_URI` is unset. Module-level `_client` cache.
- `close_client()` — closes and clears the singleton client.
- `boost_player_level(player_id, level=50, gold=5000, gems=1050, hammer=3000, name="NOOB")` — sets `pipPrgrsn.lvl`, `info.name`, `wallet.gold`, `wallet.gems`, `wallet.pips`. Logs an old→new diff summary. Returns `True`/`False`.
- `get_user_wallet(player_id)` — reads and returns the `wallet` sub-document; `{}` if not found or on error.
- `set_beach_buddies_ammo(player_id, ammo=3000)` — writes `bbData.ammAvail`. Docstring: call before opening Beach Buddies from the lobby.
- `set_treasure_island_ammo(player_id, ammo=900)` — writes `frtnIslndDt.ammCnt`. Docstring: call while the game is killed, then launch, so the value isn't overwritten by the running game.
- `set_bump_to_spin_ammo(player_id, ammo=500)` — writes `bmpToSpn.ammo`. Same "call while killed" caveat as Treasure Island.
- `set_puzzle_theatre_ammo(player_id, ammo=5000)` — writes `puzzleEventData.ammoBalance`. Docstring: call after closing the event to the lobby, then reopen it.
- `get_puzzle_theatre_ammo(player_id)` — reads `puzzleEventData.ammoBalance` via `get_user_from_db`; returns `None` if the user or field is missing.
- `get_user_from_db(player_id)` — returns the full user document (or `None`); used to cross-check UI state against the DB.
- `unlock_season_pass(player_id, points=30000)` — writes `seasonPass.points`. Returns `True`/`False`.

**Notes:** Requires env var `MONGO_URI`. External dep: `pymongo`. Every
public function catches all exceptions internally and returns a safe
default (`False` / `{}` / `None`) rather than raising — callers cannot
distinguish "not found" from "DB error" except via the log line. Logging is
emoji-tagged `logging.info/warning/error` throughout, no exceptions escape.

## `utils/state_manager.py`
**Purpose:** Thread-local, in-memory run state (current user info + collected
rewards + a generic key/value store) shared across a test run without
global-variable bleed between parallel device workers.

**Key functions / classes:**
- `StateManager` — wraps `threading.local()`; `_init()` lazily bootstraps per-thread `_store` (dict), `rewards` (list), and `user_info` (dict, defaulted from `_DEFAULT_USER_INFO`: `player_id`, `player_name`, `name`, `country`, `gold`, `gems`, `hammer`, `level`, `xp`, `equipped_pawn`, all `None`).
- `.rewards` (property) / `add_reward(source, reward_type, amount)` — appends `{"source", "type", "amount"}` to the thread's reward list.
- `.user_info` (property) / `set_user_info(key, value)` — sets a known key; logs a warning and no-ops on an unknown key.
- `get_user_info(key, default=None)` — like dict `.get`, but also treats the literal string `"None"` as `default`.
- `get_all_user_info()` — shallow copy of the user_info dict.
- `set(key, value)` / `get(key, default=None)` — generic per-thread key/value store (used elsewhere for things like `device_id`, `last_gp_console_opened`).
- `state = StateManager()` — module-level singleton instance imported by other modules (e.g. `google_play_helper.py`).

**Notes:** No env vars, no external deps. Because storage is thread-local,
each parallel device-worker thread gets an isolated copy; in single-device
mode this behaves like the old global-variable approach since only the main
thread exists.

## `utils/env_config.py`
**Purpose:** Auto-detects local toolchain paths (adb, Appium, emulator, APK
folder) so the suite runs on any laptop with zero manual configuration, with
legacy hard-coded fallbacks to the original Mac paths.

**Key functions / classes:**
- `_sdk_roots()` — candidate Android SDK root dirs that actually exist: `ANDROID_HOME`/`ANDROID_SDK_ROOT` env first, then the standard macOS/Linux/Windows SDK install locations.
- `_first_existing(paths)` / `_env(*names)` — small helpers: first existing path, first set env var.
- `detect_adb()` — resolution order: `SAT_ADB`/`ADB_PATH` env → SDK root `platform-tools/adb` → `PATH` (`shutil.which`) → legacy hard-coded Mac path.
- `detect_appium()` — `SAT_APPIUM`/`APPIUM_PATH` env → `PATH` → common install dirs (Intel/Apple-silicon Mac, Linux) → legacy path.
- `detect_emulator()` — `SAT_EMULATOR`/`EMULATOR_PATH` env → SDK root `emulator/emulator` → legacy path.
- `detect_apk_folder()` — `SAT_APK_FOLDER`/`APK_FOLDER` env (created if missing) → the original Mac folder if it still exists → a repo-relative `builds/` dir (auto-created). Returns a path string.
- `remote_adb_target()` — reads `SAT_ADB_HOST`/`SAT_REMOTE_ADB` (+ `SAT_ADB_PORT`, default `5038`); returns `(host, port)` or `(None, None)`.
- `apply_remote_adb()` — if a remote target is set, exports `ADB_SERVER_SOCKET`, `ANDROID_ADB_SERVER_HOST`, `ANDROID_ADB_SERVER_PORT` so both the `adb` CLI and Appium's internal adb point at the remote host; idempotent no-op when unset; returns `"host:port"` or `None`.

**Notes:** Env vars: `SAT_ADB`/`ADB_PATH`, `ANDROID_HOME`/`ANDROID_SDK_ROOT`,
`SAT_APPIUM`/`APPIUM_PATH`, `SAT_EMULATOR`/`EMULATOR_PATH`,
`SAT_APK_FOLDER`/`APK_FOLDER`, `SAT_ADB_HOST`/`SAT_REMOTE_ADB`,
`SAT_ADB_PORT`. This is the Phase-2 remote-execution groundwork referenced in
project memory (server runs scripts, a teammate's laptop is a thin
adb/Appium bridge). Legacy fallback constants hard-code the original
developer's Mac paths (e.g. `/Users/amithvasan/Library/Android/sdk/...`).

## `utils/driver_manager.py`
**Purpose:** Stands up the Appium (UiAutomator2) driver and the AltTester
`AltDriver`, i.e. the two live connections every test needs to a device.

**Key functions / classes:**
- `get_local_ip()` — opens a UDP socket to `8.8.8.8:80` (no data sent) purely to read back the machine's outbound local IP.
- `wait_for_altserver(host="127.0.0.1", port=13000, timeout=40)` — polls a raw TCP connect to the AltTester Desktop port until reachable or timeout; returns bool.
- `connect_altunity(alt_port=13000, app_name="sorry", retries=15, host=None)` — resolves host from the `host` arg or env `SAT_ALT_HOST` (default `127.0.0.1`); waits for the server then retries constructing `AltDriver(host, port, app_name)` up to `retries` times (5s between attempts); raises `Exception` if all attempts fail.
- `set_driver(device_id, app_package, app_activity, alt_port=13000, connect_alt=True, app_name="sorry", system_port=None)` — builds `UiAutomator2Options` (Android/UiAutomator2, `noReset=True`, `newCommandTimeout=3600`); sets `systemPort` from the `system_port` arg or env `SAT_SYSTEM_PORT` (needed so 2 parallel UiAutomator2 sessions on one Appium server don't clobber each other); sets `udid=device_id` when env `SAT_ADB_HOST` or `SAT_DEVICE_ID` is present (remote-device mode); connects to Appium at env `SAT_APPIUM_URL` (default `http://127.0.0.1:4723`) via `webdriver.Remote`; optionally calls `connect_altunity`. Returns `(driver, unity_driver)`.

**Notes:** Env vars: `SAT_ALT_HOST`, `SAT_SYSTEM_PORT`, `SAT_ADB_HOST`,
`SAT_DEVICE_ID`, `SAT_APPIUM_URL`. External deps: `appium` (Python client),
`alttester`. The long `newCommandTimeout` is explicitly to survive
multi-minute AltTester-only tests (e.g. Happy Flow) without Appium killing
the session — `google_play_helper.py`'s session-recovery logic exists partly
to defend against this anyway.

## `utils/report_manager.py`
**Purpose:** Thin orchestration layer that turns the two reporting toggles
(HTML report, Slack post) on/off for a run and delegates the actual work to
`utils/slack_reporter.py`.

**Key functions / classes:**
- `_flag(env_name, default)` — resolves a boolean toggle: if the env var is set, `True` unless its lowercased/stripped value is one of `"0"`, `"false"`, `"off"`, `"no"`, `""`; else returns `default`.
- `send_reports(results, total_duration, apk_name, run_type, device_id, device_info, start_time, end_time)` — resolves `enable_html`/`enable_slack` via `_flag("SAT_ENABLE_HTML", ENABLE_HTML)` / `_flag("SAT_ENABLE_SLACK", ENABLE_SLACK)` (module defaults both `True`); if enabled, calls `slack_reporter.generate_html_report(...)` and/or `slack_reporter.post_test_report(...)`, printing (not raising) on failure of either. Returns the HTML report file path (or `None`).

**Notes:** Env vars `SAT_ENABLE_HTML`, `SAT_ENABLE_SLACK` (this is how the
web GUI's checkboxes reach a run without editing code). Gotcha: when both
toggles are enabled, `generate_html_report` runs **twice** — once directly
from `send_reports`, and again inside `post_test_report` (which has its own
hard-coded `ENABLE_HTML = True` in `slack_reporter.py`, independent of the
`_flag`-resolved value here) — harmless (same content, file gets
overwritten) but redundant work. `send_reports` also does not forward
`device_info` to `post_test_report`, which re-derives it itself via adb.

## `utils/slack_reporter.py`
**Purpose:** Builds the self-contained HTML test report and posts the Slack
summary/upload. Does the actual work `report_manager.py` orchestrates.

**Key functions / classes:**
- `get_device_info(device_id)` — runs several `adb -s <id> shell getprop ...` + `wm size` calls (via `subprocess` and `config.ADB_PATH`); returns a dict (`device_name`, `device_brand`, `android_version`, `resolution`, `device_type` = `"Emulator"` if `"emulator" in device_id.lower()` else `"Real Device"`, `platform="Android"`). Any adb failure yields `"Unknown"` for that field.
- `generate_html_report(results, total_duration, apk_name="Unknown", run_type="complete", device_info=None, start_time=None, end_time=None)` — renders a single dark-themed HTML page: summary cards, device-info cards, a pass/fail table, a "What Was Handled" section sourced from `utils.event_tracker.get_all()`, and a per-test collapsible accordion of per-step cards (status badge, timestamp, text, optional inline screenshot that toggles zoom on click). Writes it to **two** files under `<repo_root>/reports/`: a timestamped `<run_type>_<DD-MM-YYYY>_<HHMM>.html` and an overwritten `<repo_root>/automation_report.html` "latest" pointer. Returns the timestamped path.
- `post_test_report(results, total_duration="N/A", apk_name="Unknown", run_type="complete", device_id="Unknown", start_time=None, end_time=None)` — calls `get_device_info`, optionally `generate_html_report` (gated on this module's own `ENABLE_HTML`), then if `ENABLE_SLACK` builds a Slack Block Kit summary (header + fields + one line per test with a pass/fail emoji) and `requests.post`s it to `SLACK_WEBHOOK_URL`; if an HTML report was produced, uploads it via `slack_sdk.WebClient(token=SLACK_BOT_TOKEN).files_upload_v2(channel=SLACK_CHANNEL, ...)`, catching only `SlackApiError`.

**Notes:** Env vars `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`.
External deps: `slack_sdk`, `requests`. Imports `ADB_PATH` from the repo-root
`config.py` and reads `utils/event_tracker.py`'s global handled-events store.
This module's own `ENABLE_SLACK`/`ENABLE_HTML` constants are hard-coded
`True` and are separate variables from `report_manager.py`'s `_flag`-resolved
ones (see that module's Notes). The `requests.post` Slack call has no
try/except around it — an unset/invalid `SLACK_WEBHOOK_URL` raises out of
`post_test_report`.

## `utils/screenshots.py`
**Purpose:** Per-step screenshot capture for the HTML report, captured via
the Appium driver (full device screen, so it also works for OS-level Google
Play / permission dialogs, not just Unity).

**Key functions / classes:**
- `screenshots_enabled()` — `True` iff env `SAT_SCREENSHOTS == "1"`.
- `_thumb_data_uri(png_bytes, width, quality)` — downscales via Pillow to a JPEG data URI (`LANCZOS` resample, capped to `width`); falls back to embedding the raw PNG as a data URI if Pillow is unavailable or on any error.
- `capture(driver, width=480, quality=60)` — calls `driver.get_screenshot_as_png()`, then `_thumb_data_uri`; returns `None` (never raises) on any failure at any step, so a screenshot problem can never fail a test.

**Notes:** Env var `SAT_SCREENSHOTS`. Optional dependency Pillow (`PIL`) —
degrades gracefully to raw PNG embedding if not installed.

## `utils/session_detector.py`
**Purpose:** One-shot "get to a known-good lobby state" bootstrap run at the
start of a session — clears popups, logs in as guest if needed, skips FTUE,
claims daily login, and confirms the home screen is reachable.

**Key functions / classes:**
- `detect_session_state(unity_driver, driver)` — sequence: (1) clears popups 3× via `popup_handler.clear_all_popups`; (2) if the login screen is present, taps the guest CTA and waits, else logs "already logged in"; (3) taps FTUE-skip up to 10× until it's gone; (4) claims the daily-login button up to 5× (clearing popups between); (5) waits for `HOME_BUTTON` up to 5× (clearing popups each attempt) — raises `Exception("❌ HOME not reachable")` if never found. Returns `True` on success.

**Notes:** Defines its own local `LOGIN_PATH`/`HOME_BUTTON`/`DAILY_LOGIN`/
`FTUE_SKIP` path constants rather than importing the equivalents from
`utils/paths.py` (a small duplication to be aware of if the UI changes).
Unclear: the `driver` parameter is accepted but never referenced in the
function body. Depends on `utils.popup_handler` (`clear_all_popups`,
`wait_for_safe`) and `utils.state_manager.state` (imported but not visibly
used in this function).

## `utils/error_handler.py`
**Purpose:** Small guard that detects and dismisses the game's generic
`ErrorDisplayScreen` popup before/after an action.

**Key functions / classes:**
- `handle_error_display(unity_driver)` — looks up `/ErrorDisplayScreen/Background/buttons/CloseButton/text` with a 2s timeout; taps it if found. Never raises — catches and prints a warning.
- `safe_action(unity_driver, action_fn, *args, **kwargs)` — calls `handle_error_display` before and after invoking `action_fn(unity_driver, *args, **kwargs)`; returns the action's result.

**Notes:** No env vars. Uses `print()` rather than the `logging` module used
everywhere else in `utils/` — inconsistent but functionally harmless. Imports
`By` from `alttester.by` directly rather than `from alttester import By` used
elsewhere — same symbol, different import path.

## `utils/device_names.py`
**Purpose:** Resolves a human-friendly marketing device name (e.g. "Samsung
Galaxy S23 FE") from an adb serial/model, for the GUI and reports, instead of
a bare serial or model code.

**Key functions / classes:**
- `_load_map()` — lazily loads and caches `utils/device_models.json` (a bundled Google device-list dump) into module-level `_MAP`; `{}` on failure.
- `_lookup_model(model)` — exact match against the loaded map, else the marketing name of the longest same-prefix model (≥6 shared characters, to resolve regional variants like `SM-S711B` vs `SM-S711U`); `None` if nothing matches.
- `_all_props(serial, adb_path)` — one `adb -s <serial> shell getprop` call parsed into a `{prop: value}` dict; `{}` on failure.
- `resolve(brand="", model="", marketname="")` — public: prefers a non-empty/non-"unknown" `marketname` (brand-prefixed via `_brandize`); else `_lookup_model(model)`; else raw brand+model.
- `name_from_props(props)` — public: pulls brand + the first set marketname property (checked in order: `ro.product.marketname`, `ro.vendor.product.marketname`, `ro.product.vendor.marketname`, `ro.product.odm.marketname`, `ro.config.marketing_name`) out of a getprop dict, then calls `resolve`.
- `pretty_name(serial, adb_path)` — top-level convenience: `_all_props` → `name_from_props`; falls back to the raw serial on any failure or empty result.

**Notes:** No env vars. Reads the bundled `utils/device_models.json`
(~800 KB). Every function is defensive and never raises — always falls back
to something displayable (brand+model, or the raw serial).

## `utils/alttester_appname.py`
**Purpose:** Renames a running app's AltTester app-name at runtime, so two
parallel test runs can share one AltTester Desktop license (limited to 2
concurrent app registrations) without needing per-build app-name changes.

**Key functions / classes:**
- `_screen_height(adb_path, device_id)` — parses `adb shell wm size` to get the device's pixel height (for a Unity-bottom-left → adb-top-left Y-flip); `None` on failure.
- `rename_alttester_app(current_driver, target_name, device_id=None, adb_path=None, host="127.0.0.1", port=13000, settle=1.5, attempts=10)` — taps the hidden AltTester icon dialog, sets the app-name input field to `target_name`, then restarts the app: if `device_id`+`adb_path` are given, disconnects `current_driver` first and taps the Restart button via raw `adb shell input tap` at its on-screen coordinates (fast, ~1s reconnect, per the module's own measurement); otherwise taps Restart through the driver itself (slow, ~70s reconnect — the module docstring explains why: a still-connected AltDriver client delays the server's re-registration). Then polls (up to `attempts`, 1s apart) constructing a new `AltDriver(host, port, app_name=target_name)` and probing `get_current_scene()`. Returns the new `AltDriver`; raises `RuntimeError` if reconnection never succeeds.

**Notes:** No env vars — host/port/device_id/adb_path are all caller-supplied.
Hardcodes the AltTester rename-dialog's own UI paths (`_ICON`, `_FIELD`,
`_RESTART`). External dep: `alttester`.

## `utils/google_play_helper.py`
**Purpose:** Centralised Google Play in-app-purchase flow handling — tapping
Buy, waiting out the purchase, dismissing post-purchase popups, and
recovering from UiAutomator2/AltTester session drops — so every IAP test
gets consistent timeout and crash-recovery behavior. The largest and most
complex module in `utils/`.

**Key functions / classes** (per the module's own documented public API):
- `UIA2_CRASH_SIGNAL` — string constant `"instrumentation process is not running"`; one of several substrings in `_SESSION_DEAD_SIGNALS` used to recognize a dead Appium/UiAutomator2 session (crash OR idle-timeout kill).
- `handle_google_play_purchase(driver, timeout=90)` → `(success, driver)` — ensures the Appium session is alive; waits up to 15s (load-bearing — querying too early can wedge UiAutomator2) for the GP payment sheet to render; loops trying an ordered list of Buy-button locators (UiSelector text/resource-id, plain resource-ids, XPath exact/contains text); on a successful tap, hands off to the internal `_wait_purchase_complete`; recovers from UiAutomator2 crashes inline (up to 3×); logs all visible clickables each iteration Buy isn't found. Returns `(False, driver)` on timeout.
- `handle_purchase_failure(unity_driver)` → `"success" | "retry" | "skip"` — call once after `reconnect_alttester()` in every IAP test. Suppresses `popup_handler`'s auto-dismiss for the Purchase-Failed modal, checks for it (5s), dismisses via Okay/Close if present, and returns `"retry"` if the GP console had opened (`state.get("last_gp_console_opened")`) or `"skip"` if it never did; `"success"` if no failure popup appeared.
- `close_extra_google_play_popups(driver, timeout=20)` → `(bool, driver)` — safety-net loop that dismisses any residual safe GP popups; returns `(True, driver)` once clear.
- `reconnect_appium_no_launch(old_driver)` → `driver | None` — quits `old_driver` and opens a fresh UiAutomator2 session attached to `state.get("device_id")` with no `appPackage`/`appActivity` (attaches without launching anything).
- `reconnect_alttester(unity_driver=None)` → `AltDriver` — stops the given driver if any; tries foregrounding the game (`adb shell am start`) and reconnecting up to 3×; if that fails, force-stops and restarts the app and retries up to 5× with longer waits; raises `RuntimeError` if all attempts fail.
- Internal helpers: `_is_session_dead(exc)`, `_appium_alive(driver)`, `_ensure_appium_session(driver)` (revives a dead session before a purchase starts), `_wait_alt(...)`, `_appium_scan_post_buy(driver)` (XPath-based scan for sheet-present / safe-dismiss-button / clickables — explicitly not the `android uiautomator` UiSelector engine, which the module notes returns nothing on this game's GP sheet), `_wait_purchase_complete(...)` (waits for the screen to stay "clear" for a full grace window after Buy is tapped).

**Notes:** Env vars `SAT_ALT_HOST`, `SAT_APPIUM_URL`. Imports `ADB_PATH` from
repo-root `config.py`; depends on `utils.state_manager.state` (`device_id`,
`last_gp_console_opened`) and `utils.popup_handler` (`ignore_popup`/
`unignore_popup`, imported lazily inside `handle_purchase_failure`).
Hardcodes the game's package name (`com.gameberry.sorry.card.board.game`)
and activity (`com.unity3d.player.SorryUnityPlayerActivity`). External deps:
`alttester`, `appium`.

## `utils/test_logger.py`
**Purpose:** A `logging.Handler` that collects each logged test step (and,
when enabled, a matching screenshot) into a list the HTML report renders as
per-test accordions.

**Key functions / classes:**
- `TestStepCollector(logging.Handler)` — `__init__(driver=None, min_interval=0.3, max_shots=200)` stores `self.steps = []` and computes `self.capture_shots = screenshots_enabled() and driver is not None`.
- `.emit(record)` — ignores noisy infra log lines (containing `"Websocket connected"` or `"[wait_for_safe]"`); if screenshots are enabled and under `max_shots` and at least `min_interval` seconds have passed since the last shot, captures one via `utils.screenshots.capture(self.driver)`; appends either `{"step": msg, "screenshot": shot}` or the plain message string to `self.steps`.

**Notes:** No env vars directly (delegates to `utils.screenshots.
screenshots_enabled()`, i.e. `SAT_SCREENSHOTS`). Meant to be attached as a
handler on the run/test logger so `slack_reporter.generate_html_report`'s
per-step cards have both text and (optionally) a screenshot.
