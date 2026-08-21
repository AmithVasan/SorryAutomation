# Core & Scripts

The engine and entry points that turn "run a suite" into executed tests against
a real Android device, plus the remote-execution scripts that let a central
server drive a device plugged into someone else's laptop. `run_this.py` is the
one script a human or the webapp actually invokes; `core/execution_engine.py`
is a separate (and, per the code, effectively unused) class-based runner;
`config.py` holds shared constants; `check_setup.py` is a preflight sanity
check; `agent.py` and `bridge.py` are the two flavors of "remote laptop"
process that let a device on a teammate's machine be driven from the central
server.

## `run_this.py`

**Role:** The main, single-file test runner. Boots Appium + AltTester,
resolves a device, installs the right APK, launches the game, connects
Appium/AltTester drivers, runs the selected tests from `tests.test_registry.TEST_REGISTRY`,
and sends reports. Supports single-device, multi-device "parallel", and
single-test ("individual") modes, plus a Slack build-watcher. Doubles as the
script the GUI/webapp shells out to and as an interactive CLI (`python
run_this.py` with no args prompts a menu).

**CLI** (`build_config_from_args()`, argparse with `parse_known_args`, so extra
launcher argv is ignored):

| Flag | Values | Effect |
|---|---|---|
| `--run-type` | `smoke`\|`regression`\|`iap`\|`bat`\|`complete` | Single-device run filtered to tests whose `type` list contains this value. |
| `--test` | name or 1-based index | Run one `TEST_REGISTRY` entry ("individual" mode). Guest Login is auto-prepended unless it's the one selected (it seeds `player_id` in state). |
| `--slack` | `on`\|`off` | Sets `SAT_ENABLE_SLACK` env for `report_manager`. |
| `--report` | `on`\|`off` | Sets `SAT_ENABLE_HTML` env for `report_manager`. |
| `--screenshots` | `on`\|`off` | Sets `SAT_SCREENSHOTS`; `on` also forces `SAT_ENABLE_HTML=1` since screenshots render inside the HTML report. |
| `--list-tests` | flag | Prints `index<TAB>name` for every `TEST_REGISTRY` entry and exits (0). |
| `--check-builds` | flag | Runs the Slack build fetch once and exits (0) — used by the GUI's "Check for new builds" button. |

With no run-selecting flag, `build_config_from_args()` returns `None` and
`__main__` falls back to the interactive `select_run_type()` menu (options
1–5 single-device, 6–7 two-device parallel presets, 8 individual test
picker).

**Key env vars:**

| Var | Effect |
|---|---|
| `SAT_APP_NAME` | Per-run AltTester app name for parallel execution. When set, `_run_single_device` force-stops the app first, and after connecting renames the AltTester app (via `utils.alttester_appname.rename_alttester_app`) from the baked-in default `"sorry"` to this value so concurrent runs don't collide. |
| `SAT_SYSTEM_PORT` | Per-run Appium `systemPort`; when set (parallel mode) its stale `adb forward` is removed before relaunch so UiAutomator2 doesn't reject the new session as "port busy". |
| `SAT_DEVICE_ID` | Forces `get_device_id()` to return this serial/IP directly (skips USB/WiFi auto-detection) — used so remote/parallel runs target a specific device deterministically. |
| `SAT_APK` | Absolute path to a specific APK; `get_selected_apk()` uses it if set and existing, else falls back to the newest `*.apk` in `APK_FOLDER`. |
| `SAT_SKIP_BUILD_FETCH` | When `"1"` (and `SAT_APK` unset), skips the automatic Slack "fetch latest build" at startup — the GUI sets this since it owns build-fetching via its own button. |
| `SAT_ADB_HOST` / `SAT_ADB_PORT` | Read by `utils.env_config.apply_remote_adb()` (called at import time, stored as `REMOTE_ADB`). If `SAT_ADB_HOST` is set, exports `ADB_SERVER_SOCKET`, `ANDROID_ADB_SERVER_HOST`, `ANDROID_ADB_SERVER_PORT` so every `adb` subprocess call and Appium's own adb calls transparently target a remote adb server (a teammate's `bridge.py`) instead of the local one. Port defaults to `5038`. |
| `SAT_APPIUM_URL` | Appium base URL (default `http://127.0.0.1:4723`). If it doesn't contain `127.0.0.1`/`localhost`, `start_appium()` treats it as remote — Appium must already be running there — and only health-checks it (30 s) instead of launching a local instance. |
| `SAT_BRIDGE_INSTALL_URL` | When set, `install_apk()` POSTs `{build, serial}` to `<url>/install` (a `bridge.py` laptop) instead of running `adb install` locally — the bridge downloads the build from the server and installs it over its own USB link, avoiding a large APK push over an adb-relay connection. |
| `SAT_ALT_HOST` | Host passed to `rename_alttester_app()` for the AltTester rename call (default `127.0.0.1`). |
| `SLACK_BUILD_CHANNEL`, `SLACK_BOT_TOKEN` | (from `.env`, not `SAT_*`) Configure the Slack build watcher; watcher is skipped entirely if either is empty. |

**Main flow** (`if __name__ == "__main__"`):
1. Build config from CLI args (`build_config_from_args()`); if none, show the interactive menu (`select_run_type()`).
2. Unless `SAT_APK` or `SAT_SKIP_BUILD_FETCH=1`, poll Slack for a newer matching build (`fetch_latest_build_from_slack()`) and download it into `APK_FOLDER`.
3. Dispatch on `config["mode"]` via `run_flow()` → `_run_single_device`, `_run_parallel`, or the individual-test path (which still calls `_run_single_device` with an explicit test list).
4. Each single-device path: `start_appium()` → `start_alttester()` → `get_device_id()` → `install_apk()` (picks USB serial over a WiFi id when both are visible, unless `SAT_DEVICE_ID` pins it) → (parallel-identity reset if `SAT_APP_NAME` set) → `setup_reverse_forward()` (adb reverse tcp:13000) → `launch_game()` → sleep 20s for AltTester registration → `set_driver()` (Appium + AltTester/Unity driver) → optional AltTester app rename → `run_all_tests()`.
5. `run_all_tests()` filters `TEST_REGISTRY` by run type (or uses an explicit list), dynamically loads each test module by file path (`importlib.util.spec_from_file_location`, so filenames with special characters work), health-checks/reconnects AltTester before each test, runs the test function, collects a result dict (`name`/`status`/`steps`), and — if `send_report=True` — calls `send_reports()`.
6. Parallel mode (`_run_parallel`) discovers all connected devices, spins one thread per device running `_device_worker()` (own install/launch/driver/`run_all_tests(send_report=False)`), merges results/events under locks, and sends one combined report.
7. On exit, the process is force-terminated (comment notes Appium/Mongo/AltTester keepalive threads would otherwise hang the process, leaving the webapp's device status stuck on "Busy").

**Key functions** (one line each):
- `get_device_id()` — resolves a device via `SAT_DEVICE_ID` override, cached/auto WiFi IP, static WiFi IP, USB, or starts an emulator as last resort; returns `(device_id, is_emulator)`.
- `install_apk(device_id)` — per-device checksum/version comparison against the selected APK; uninstalls a mismatched build and installs (locally via `adb install -r -d`, retried with `--no-streaming`, or via `SAT_BRIDGE_INSTALL_URL`) only when needed.
- `get_selected_apk()` / `get_latest_apk()` — pick `SAT_APK` or the newest file by ctime in `APK_FOLDER`.
- `launch_game(device_id)` — disables screen sleep/lock (`keep_screen_awake`) then `am start`s the activity.
- `setup_reverse_forward()` / `teardown_reverse_forward()` — `adb reverse tcp:13000 tcp:13000` so the on-device AltTester client can dial `127.0.0.1:13000` to reach the desktop/host AltTester (teardown exists but is intentionally not called after a run).
- `run_all_tests(...)` — the core test loop described above; returns `(test_results, duration_text, apk_name)`.
- `_run_single_device()` / `_run_parallel()` / `_device_worker()` — single-device, multi-device orchestration, and the per-thread device worker body.
- `run_flow(config)` — dispatches a `select_run_type()`/`build_config_from_args()` config dict to the right runner.
- `fetch_latest_build_from_slack()` — polls `conversations.history` on `SLACK_BUILD_CHANNEL`, matches message text or `.apk` filename against `SLACK_MATCH_KEYWORDS` (`["[SAT]", "alttester"]`), downloads the newest match, records its ts in `.slack_last_build_ts`.
- `_alt_launch_lock(enabled)` — a cross-process `fcntl` file lock (`$TMPDIR/sat_alt_launch.lock`) serializing the launch→rename window so concurrent parallel runs don't collide while both are transiently on the default AltTester app name `"sorry"`.

## `core/execution_engine.py`

**Role:** A small `ExecutionEngine` class (`__init__(unity_driver, appium_driver)`, `run_all()`) intended to time and run a suite and print a summary via `state.print_summary()`.

**Caveat (unclear/likely dead code):** This file is **not imported anywhere else in the repo** (`grep` for `ExecutionEngine`/`execution_engine` finds only its own definition), and it does not compile: line 4 reads `from tests import test_01_guest_login.test_guest_login`, which is a `SyntaxError` in Python (confirmed via `python3 -m py_compile`, dotted names aren't valid in a `from...import` clause). Its `run_all()` also only ever calls a single hard-coded test (`test_01_guest_login`) rather than iterating `TEST_REGISTRY` — the actual registry-driven loop, driver setup, and results/report collection described in this doc's task live in `run_this.py`'s `run_all_tests()` / `_run_single_device()` / `_run_parallel()`, not here. Treat this file as legacy/unused scaffolding rather than part of the live execution path.

**What it does contain, at face value:**
- `start_timer()` / `end_timer()` — wall-clock timing via `time.time()`.
- `run_all()` — would call `test_01_guest_login(self.unity, self.driver)`, log a summary block, and call `state.print_summary()` (from `utils.state_manager`), inside a try/except that logs (but does not re-raise) any exception.

## `config.py`

Shared constants imported elsewhere in the repo (note: `run_this.py` does **not** import this module — it redeclares its own copies of most of these constants inline near its top, so the two can in principle drift).

- **Auto-detected toolchain paths**, via `utils/env_config.py` (`detect_adb`, `detect_appium`, `detect_emulator`, `detect_apk_folder` — see below): `APK_FOLDER`, `ADB_PATH`, `APPIUM_PATH`, `EMULATOR_PATH`.
- `EMULATOR_NAME` — from env `EMULATOR_NAME`, default `"Tab"`.
- App identity: `PACKAGE_NAME = "com.gameberry.sorry.card.board.game"`, `ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"`, `APP_NAME = "sorry"`.
- Appium: `APPIUM_URL = "http://127.0.0.1:4723"`, `APPIUM_PORT = 4723` (this file's `APPIUM_URL` is a plain constant, unlike `run_this.py`'s which reads `SAT_APPIUM_URL`).
- `ALTTESTER_PORT = 13000`.
- `DEVICE_COORDS` — hard-coded on-screen tap coordinates (`ip_field`, `restart`) for `"real"` vs `"emulator"` device layouts.
- `CHECKSUM_FILE = "apk_checksum.txt"`.

Toolchain path resolution (in `utils/env_config.py`, used by both `config.py` and `run_this.py`) is: explicit env var (`SAT_ADB`/`ADB_PATH`, `SAT_APPIUM`/`APPIUM_PATH`, `SAT_EMULATOR`/`EMULATOR_PATH`, `SAT_APK_FOLDER`/`APK_FOLDER`) → auto-detect from `ANDROID_HOME`/`ANDROID_SDK_ROOT` or the OS-standard SDK location → a hard-coded legacy Mac path fallback (or, for the APK folder, an auto-created repo-relative `builds/` directory).

## `check_setup.py`

**Role:** One-shot, non-crashing preflight readiness check (`python3 check_setup.py`). Prints PASS/MISSING/WARN per item and exits `0` only if nothing is missing (exits `1` otherwise; a missing `SAT_ALT_HOST` is a neutral WARN, not a failure).

**What it checks:**
- Python version `>= 3.8`.
- Toolchain detection via `utils.env_config` (`detect_adb`, `detect_appium`, `detect_apk_folder`): binary/path existence for adb, appium, and the APK folder.
- At least one authorized device in `adb devices` output (only if adb was found).
- Python dependencies importable: `appium`, `alttester`, `pymongo`, `requests`, `dotenv`, `fastapi`, `uvicorn` (each reports the matching `pip install` name if missing).
- `.env` file present in the repo root, and whether it contains `MONGO` and `SLACK` keys (both just substring-checked, not validated).
- If `SAT_ALT_HOST` is set, opens a raw socket to `<SAT_ALT_HOST>:13000` to confirm a central AltTester server is reachable; if unset, reports (as a WARN, not a failure) that the run will use LOCAL mode.
- On success, suggests the next command: `uvicorn webapp.app:app --host 127.0.0.1 --port 8000`.

## `agent.py`

**Role:** "Automation Runner remote agent" — runs on a teammate's laptop with a device on USB. Registers with the central server/webapp, long-polls for a job, and when one arrives runs `run_this.py` **locally** as a subprocess (Appium/adb are host-local), streaming its stdout back to the server line-by-line so it renders live in the browser. Per its own docstring, the device itself never leaves the laptop — only console output and pass/fail travel over HTTP.

**How it registers + polls + runs:**
- `register(devices)` — `POST {SERVER}/agent/register` with `agent_id`, `name`, and the current `adb devices` list.
- `main()` loop: registers once at startup, then repeatedly `poll()`s (`GET {SERVER}/agent/poll?agent_id=...`, 15s timeout). If the server reports `known: False` (it restarted), re-registers. If a job is returned, calls `run_job(job)`; otherwise re-registers only when the device list changed, and sleeps 2s.
- `run_job(job)` — picks the first attached device, sets `adb -s <device> reverse tcp:13000 tcp:13000` and starts a local TCP relay thread (`localhost:13000` → central server's `ALT_HOST:ALT_PORT`) so both the game and AltDriver reach the **central, licensed** AltTester over the default `127.0.0.1` config with no build change; also starts a heartbeat thread that pings `post_log(run_id, "")` every 10s (server just bumps `last_seen`). Builds the `run_this.py` command from the job (`--test <name>` or `--run-type <type>`, plus `--slack`/`--report`), runs it via `subprocess.Popen` with `SAT_ADB` pinned to this agent's adb and `PYTHONUNBUFFERED=1`, and streams each output line to `post_log()`. Removes the adb reverse and posts the final `post_result(run_id, "passed"/"failed", returncode)` in a `finally` block.

**Env vars:**

| Var | Effect |
|---|---|
| `SAT_SERVER` | Central server base URL (default `http://GBL-Admins-MacBook-Air.local:8000`). |
| `SAT_AGENT_NAME` | Friendly name shown in the GUI (default: hostname). |
| `SAT_AGENT_ID` | Stable agent id (default: hostname). |
| `SAT_PROJECT` | Project label sent nowhere visible in this file besides being read (default `"Sorry! World"`) — not included in `register()`'s payload, so its effect is unclear from this file alone. |
| `SAT_ALT_PORT` | AltTester port for the relay and `adb reverse` (default `13000`). |

## `bridge.py`

**Role:** The thin, self-contained (stdlib-only, no repo checkout needed) "laptop bridge" for Phase 2 remote execution. Unlike `agent.py` (which runs the scripts locally), `bridge.py` runs **nothing** of the test suite itself — it only exposes a plugged-in device to a central server that holds the scripts and the AltTester license, by opening three relays/services and registering their addresses.

**The relays + ports it opens:**
- **adb relay** — `0.0.0.0:<ADB_RELAY_PORT default 5038>` → `127.0.0.1:5037` (the local adb server), via a generic threaded TCP pipe (`_relay`/`_pipe`). Lets the central server drive this laptop's adb as if local.
- **AltTester relay** — `0.0.0.0:<ALT_PORT default 13000>` → `<SERVER_HOST>:13000`, so the game (once `adb reverse`d) reaches the server's licensed AltTester instance.
- **Appium** — started locally on `0.0.0.0:<APPIUM_PORT default 4723>` by `start_appium()` (auto-detects the `appium` binary, ensures the `uiautomator2` driver is installed, computes/sets `ANDROID_HOME`/`ANDROID_SDK_ROOT` — synthesizing a minimal SDK dir with a symlinked `adb` if needed — restarts any already-running Appium so it definitely has that env, and health-polls `/status` for up to 30s). Must run next to the device since UiAutomator2 needs local adb access.
- **Local install HTTP server** — `0.0.0.0:<INSTALL_PORT default 8799>` (`ThreadingHTTPServer` + `_InstallHandler`), exposing `POST /install {build, serial}`: downloads that build from `{SERVER}/build?name=...` and runs `adb install -r -d` locally over USB. This is how `run_this.py`'s `SAT_BRIDGE_INSTALL_URL` path installs a build without pushing a large APK back over the adb relay.

**How the server drives it:** `register()` posts to `{SERVER}/agent/register` with `agent_id`, `name`, `kind: "bridge"`, this laptop's outbound-facing IP (`local_ip()`, found by opening a UDP socket toward the server host), current `adb devices`, `adb_port`, an `appium_url` (only advertised if Appium's `/status` actually responds — so the server never routes a run to a dead Appium), `install_url`, and per-device friendly-name properties (`device_props()`, reads marketing-name `getprop` keys like `ro.product.marketname`). `main()` then loops every 8s calling `GET /agent/poll`; if the server says `known: False` (restarted) it re-registers, and it also re-registers whenever the device list or Appium's up/down state changes (hot-plug detection). There is no job-polling/execution loop here (that's `agent.py`'s job) — the server presumably reaches this laptop directly over the relays/URLs it registered.

**Env vars:**

| Var | Effect |
|---|---|
| `SAT_SERVER` | Central server base URL — **required**; the script exits immediately if unset. |
| `SAT_AGENT_NAME` | Friendly name shown in the webapp (default: hostname). |
| `SAT_AGENT_ID` | Stable agent id (default: hostname). |
| `ADB_RELAY_PORT` | Local port for the adb relay (default `5038`). |
| `ALT_PORT` | AltTester relay port, both listen and forward to on the server (default `13000`). |
| `APPIUM_PORT` | Port Appium binds to (default `4723`). |
| `INSTALL_PORT` | Local install-HTTP-server port (default `8799`). |
| `SAT_ADB` / `ADB_PATH` | Explicit adb path (else auto-detected: `SAT_ADB`/`ADB_PATH` env → `PATH` → common SDK locations → bare `"adb"`). |
| `SAT_APPIUM` | Explicit appium binary path (else `shutil.which("appium")`). |

