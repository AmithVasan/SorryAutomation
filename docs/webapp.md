# Web App (`webapp/app.py`)

## Overview
`webapp/app.py` is a FastAPI app (`app = FastAPI(title="Automation Runner")`, `webapp/app.py:110`) served by `uvicorn` on port **8000**. It is the team's single control surface — pick a project, a run type (or one test), toggle Slack / HTML report / screenshots, hit Run — and it is also the **parallel-run and bridge/agent orchestrator** for the whole automation suite.

It does **not** run tests itself. For a local or bridge-driven run it shells out to the existing interactive runner non-interactively:

```
python run_this.py --run-type <type> --slack on|off --report on|off --screenshots on|off [--test "<name>"]
```

as a `subprocess.Popen` (`webapp/app.py:604-647`), merges its stdout/stderr into a per-run log file, and exposes that log for the frontend to poll. For an **executor**-kind remote agent, it instead queues a job that the agent's own `agent.py` process claims and runs on its own machine (see "Bridge / agent dispatch" below).

Other structural facts:
- `PYTHON` = the interpreter running the app (`sys.executable`) unless overridden by `SAT_PYTHON` — so `run_this.py` always launches in whatever venv started uvicorn.
- `GET /` renders `templates/index.html` via Jinja2; `/static` is a `StaticFiles` mount of `webapp/static/` (CSS, logo, background images).
- `PROJECTS` (`webapp/app.py:99-105`) lists 5 projects for the dropdown; only `"Sorry! World"` has `runnable: True` (`_RUNNABLE`). The rest are Tier-2 placeholders — `/run` and `/dispatch` reject them with HTTP 400.
- `RUN_TYPES = ["smoke", "regression", "iap", "bat", "complete"]`. Individual-test names come live from `tests.test_registry.TEST_REGISTRY`, reloaded on every `/` page load and via `GET /tests`, so new tests appear without a server restart.
- A run can target any git branch via the `ref` form field: `_prepare_worktree()` checks it out into a sibling worktree (`../.sorry-branch-runs/<branch>`, with `.env` copied in) so the webapp's own working tree is never disturbed — the current branch (or a blank `ref`) just runs in place.
- The build/APK folder (`APK_FOLDER`) is auto-detected via `utils.env_config.detect_apk_folder()`, falling back to `<repo>/apks`.

## Hosting & startup
- **Manual / dev:** from the repo root, in the same virtualenv the automation uses:
  ```bash
  pip install -r webapp/requirements.txt
  uvicorn webapp.app:app --host 0.0.0.0 --port 8000
  ```
  (`webapp/README.md`, `SERVER_SETUP.md §1`). Dies when the terminal closes — fine for testing, not for a server.
- **Always-on service:** a macOS LaunchAgent, `webapp/com.gameberrylabs.automation-runner.plist`, installed to `~/Library/LaunchAgents/` and loaded with `launchctl load`. Key settings from the plist:
  - `ProgramArguments`: `python3 -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000`
  - `RunAtLoad = true` (starts at login) and `KeepAlive = true` (auto-restarts on crash — a plain `kill` won't stop it; must `launchctl unload`/`bootout`)
  - `StandardOutPath` / `StandardErrorPath` both point to `webapp/runs/server.log`
  - The checked-in `WorkingDirectory` and Python path are for one specific machine and must be edited per host before installing elsewhere.
- Full install/restart/stop steps, companion-service requirements (AltTester Desktop, Appium, MongoDB), and a troubleshooting table live in **`../SERVER_SETUP.md`** — this doc only summarizes hosting; that one is the operational reference.

## Parallel-run model
- **`RUNS`** (`webapp/app.py:119-124`) is the in-memory live-run registry: `run_id -> {proc, log_path, log_file, label, display, project, started, ended, returncode, stopped, agent_id, device, slot, app_name}`. Run history persists independently as `webapp/runs/run_<id>.log` + `run_<id>.json` files on disk (git-ignored), so past runs still show up after a restart even though `RUNS` itself is wiped.
- **`PARALLEL_SLOTS`** = `int(os.environ.get("SAT_PARALLEL_SLOTS", "2"))` (`webapp/app.py:125`) — the max number of simultaneous runs, bounded in practice by the shared AltTester Desktop's licensed concurrent-connection capacity.
- Each run claims a free slot (`_free_slot()`, 1..`PARALLEL_SLOTS`) and gets a distinct identity so parallel runs don't collide on the shared AltTester Desktop: `SAT_APP_NAME = sorry<slot>` (e.g. `sorry1`, `sorry2`) and `SAT_SYSTEM_PORT = 8199 + slot` (e.g. 8200, 8201) — both injected into the subprocess env (`webapp/app.py:627-628`).
- **One-run-per-device gating:** independent of slot availability, `_device_active_run(device)` refuses a new run on a device that already has one active (`HTTP 409`).
- **Per-run env injection** (`webapp/app.py:623-642`): always `PYTHONUNBUFFERED=1`, `SAT_SKIP_BUILD_FETCH=1`, plus the app-name/systemPort pair above; a bridge-driven remote device additionally gets `SAT_ADB_HOST`, `SAT_ADB_PORT`, `SAT_DEVICE_ID`, and optionally `SAT_APPIUM_URL` / `SAT_BRIDGE_INSTALL_URL`; a local device gets `SAT_DEVICE_ID`; a chosen `build` (APK) that exists on disk sets `SAT_APK`.
- **`_watch(run_id)`** (`webapp/app.py:393-420`) is a daemon thread spawned right after each subprocess starts (`webapp/app.py:667`) — it is **not an HTTP endpoint**, just the internal per-run watcher. It blocks on `proc.wait()`, closes the log file, computes final status (`stopped` if `/stop` was called, else `passed`/`failed` from the return code), writes it into the run's `.json` metadata, frees the run's bridge agent back to `idle` if it was bridge-driven, and drops the run from the live `RUNS` dict (the on-disk log/metadata remain for history).
- **`/stop` + stale-state cleanup:** stopping SIGKILLs the run's whole process group at once (`_kill_proc_tree`, via `os.killpg`; the run starts with `start_new_session=True`, `webapp/app.py:372-390`). Because SIGKILL skips `run_this.py`'s own teardown, `/stop` then best-effort force-stops the game package and removes the `adb forward` for that slot's systemPort, but **only for local (non-bridge) runs** (`webapp/app.py:700-714`) — bridge-driven runs (`agent_id` set) skip this since the device isn't attached to the server.
- **History** (`GET /history`, `HISTORY_LIMIT = 10` shown) is rebuilt from `run_*.log` files on disk (newest first) so every past run shows up even without metadata, parsing a display name out of the log for pre-metadata runs (`_infer_type_from_log`). `_prune()` deletes the oldest log/json pairs beyond `KEEP_RUNS = 20`.

## Bridge / agent dispatch
Remote-device runs share the `AGENTS` / `AGENT_JOBS` registries and the `/agent/*` control-plane, but split into two models distinguished by the `kind` field sent at registration (`webapp/app.py:1007`):

- **`kind="bridge"`** — today's onboarding path (`bridge.py`, installed via `/install.sh` / `/install.ps1` / `/bridge.py`). The laptop only exposes its device (an adb relay port, an Appium URL, a small install-server URL) via `POST /agent/register`. The **server itself** still runs `run_this.py` (via `POST /run` with `agent=<agent_id>`), pointing the automation at the bridge's device over the network (`SAT_ADB_HOST`/`SAT_ADB_PORT`, `SAT_APPIUM_URL`, `SAT_DEVICE_ID`). Because the server drives it, a bridge run is tracked exactly like a local run — in `RUNS`, and via `/status` / `/log` / `/stop` — just with `agent_id` set. `/run` rejects the request if the bridge has no device or Appium isn't reported running there yet.
- **`kind="executor"`** — the older "Remote devices" model (`agent.py`, `kind` defaults to `"executor"` when omitted; see `AGENT_SETUP.md`). The laptop registers, then long-polls `GET /agent/poll` for queued jobs, runs `run_this.py` **locally** against its own device, and reports back via `POST /agent/log` (streamed console text; an empty call is just a heartbeat) and `POST /agent/result` (final status/returncode). `POST /dispatch` only enqueues a job into `AGENT_JOBS[agent_id]` and pre-creates the run's log/metadata files — the run is never added to the local `RUNS` dict, so the frontend polls `GET /runinfo?run_id=...` (reads the `.json` metadata) to detect completion instead of `/status`.
- Both kinds heartbeat through the same `last_seen` timestamp; an agent not heard from for `AGENT_OFFLINE_SEC = 20` seconds shows as `offline` in `GET /agents`. `POST /agent/register` is an idempotent upsert into `AGENTS` keyed by `agent_id`, so it also covers re-registration.
- Onboarding: `GET /install.sh` / `GET /install.ps1` serve installer scripts with the server address templated in from the **requesting client's own origin** (`request.base_url`), so a freshly-onboarded laptop can always reach the server back; the scripts install adb/Node/Appium as needed, then download and run `GET /bridge.py` (the repo's real `bridge.py`, served verbatim).

## Endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Render the main page (`templates/index.html`) with the project list, run types, and current test names. |
| GET | `/status` | JSON: active runs (multi-run), slots used/total, connected local devices, report availability; also legacy single-run fields mirroring the newest active run (back-compat). |
| GET | `/history` | JSON list of the last `HISTORY_LIMIT` (10) runs, newest first, rebuilt from disk. |
| GET | `/branches` | JSON: local git branches (current, then `master`/`dev`, then the rest) for the branch/version picker. |
| GET | `/tests` | Reloads `tests.test_registry` from disk and returns current test names (backs the "Refresh list" button). |
| GET | `/log` | Plaintext tail of a run's console log from a byte `offset` (query params: `run_id`, `offset`); no `run_id` → newest active run's log. Returns the new offset in an `X-Offset` response header. |
| POST | `/run` | Start a run (local device or bridge-driven remote device) as a `run_this.py` subprocess. Form fields: `project, mode, run_type, test, slack, report, screenshots, ref, agent, build, device`. |
| POST | `/stop` | Stop one run — by `run_id` or by `device` (form fields), else the newest active run. SIGKILLs its process group; best-effort cleanup for local runs. |
| GET | `/builds` | JSON list of APKs in the build folder, newest first. |
| GET | `/build` | Download one APK by filename (query `name`; basename-only, path-traversal guarded) — used by bridges to install a build over USB. |
| POST | `/builds/refresh` | Fetch new builds from Slack (`run_this.py --check-builds`), then return the refreshed `/builds` list. |
| GET | `/devices` | JSON list of server-local `adb` devices with human-readable names. |
| GET | `/reports` | JSON list of past HTML reports in `reports/`, newest first. |
| GET | `/report` | Serve a past report by query `name`, or `automation_report.html` (the latest) if no name given. |
| GET | `/screenshots.zip` | Extract every embedded base64 step screenshot from the latest report into a downloadable zip. |
| GET | `/bridge.py` | Serve the repo's `bridge.py` source file (for `curl … -o bridge.py`). |
| GET | `/install.sh` | Serve the macOS/Linux bridge installer script, with the server origin templated in. |
| GET | `/install.ps1` | Serve the Windows PowerShell bridge installer script, with the server origin templated in. |
| GET | `/runinfo` | JSON status (`status`, `running`, `returncode`, `label`) of any run — local or agent-dispatched — read from its `.json` metadata file. |
| GET | `/agents` | JSON list of registered bridge/executor agents: name, devices, online/offline status, kind, ip. |
| POST | `/agent/register` | Register (or re-register) an agent/bridge laptop. JSON body: `agent_id, name, devices, kind, ip, adb_port, appium_url, install_url, device_props`. |
| GET | `/agent/poll` | Executor-agent heartbeat + claim the next queued job for `agent_id` (required query param), if any. |
| POST | `/agent/log` | Append streamed console text from an executor agent's local run into that run's central log file; also acts as a heartbeat. JSON body: `agent_id, run_id, text`. |
| POST | `/agent/result` | Executor agent reports a run's final result. JSON body: `agent_id, run_id, status, returncode`. Updates metadata, frees the agent to `idle`. |
| POST | `/dispatch` | Queue a run job for an **executor**-kind agent to claim via `/agent/poll` and run on its own device. Form fields: `agent_id, project, mode, run_type, test, slack, report`. |

`/static/*` (GET) is also served, via a `StaticFiles` mount (`webapp/static/` — CSS, logo, background images), not a hand-written route.

## Notes & gotchas
- **Single process, in-memory state.** `RUNS`, `AGENTS`, and `AGENT_JOBS` are plain dicts guarded by `threading.Lock`s — correct for uvicorn's default single worker, but running this app with multiple workers/processes would fragment that state. A server restart loses all *live* run/agent tracking (on-disk `webapp/runs/*.json`/`.log` history survives; any still-running subprocess becomes an untracked orphan).
- **Frontend polling, no push.** `templates/index.html` polls `GET /status` every 1500 ms and `GET /log` every 1200 ms (`setInterval(pollStatus, 1500)` / `setInterval(pollLog, 1200)`); there is no WebSocket/SSE channel.
- **No authentication.** No route requires a login or token. Combined with `--host 0.0.0.0`, anyone who can reach port 8000 (LAN/VPN) can start/stop runs, download APKs and reports, or register as an agent; `SERVER_SETUP.md` relies on firewall/VPN boundaries, not app-level auth.
- **`SAT_PARALLEL_SLOTS` vs. license capacity.** Raising the slot count doesn't help if it exceeds the AltTester Desktop license's concurrent-connection limit.
- **Stops are always hard.** `/stop` has no graceful-shutdown path — it's SIGKILL only, so `run_this.py` never gets to run its own cleanup; the webapp compensates only for local runs (see "Parallel-run model" above), not bridge-driven ones.
- **Some sibling docs are stale.** `webapp/README.md` ("one run at a time", HTTP 409 on any second run) and `AGENT_SETUP.md` ("every run currently uses the same `app_name` (`sorry`)") describe a pre-`PARALLEL_SLOTS` version of this app; the code now supports `PARALLEL_SLOTS` concurrent runs with per-slot `app_name`/`systemPort` as documented above.
- Unclear: `SAT_BRIDGE_INSTALL_URL` (forwarded from a bridge's `install_url`) is set on the run subprocess's env, but what consumes it happens inside `run_this.py`/the driver layer, outside `webapp/app.py` — not verified as part of this doc.
