# Sorry! World — Automation Framework Documentation

Internal reference for the QA automation framework that drives automated
functional tests against the **Sorry! World** Android game
(Python · Appium/UiAutomator2 · AltTester · MongoDB · FastAPI web app).

> All docs live under this `docs/` folder so they can be tracked in git alongside
> the code. Generated 13 Aug 2026.

## How the pieces fit

- **Tests** (`tests/test_XX_*.py`) are registered in `tests/test_registry.py` and
  launched by **`run_this.py`** (via `core/execution_engine.py`), which handles
  APK install, Appium, the AltTester connection, DB setup and reporting.
- Tests lean on shared **helpers** (element lookup, popups, wallet reads),
  **utils** (paths, MongoDB, state, reporting, device naming), and per-popup
  **handlers**.
- The **web app** (`webapp/app.py`) is the team's control surface and the
  parallel-run / bridge-dispatch orchestrator.

## Tests

One document per test under [`docs/tests/`](tests/README.md) — see the
**[test index](tests/README.md)** for the full table.

## Module reference

| Doc | Covers |
|---|---|
| [helpers.md](helpers.md) | Reusable helper API tests call directly — `utils/helpers.py`, `popup_handler.py`, `ui_helpers.py`, `event_tracker.py`, `device_helpers.py`, `booster.py` |
| [utils.md](utils.md) | Infrastructure modules — `paths.py`, `mongo_helper.py`, `state_manager.py`, `env_config.py`, `driver_manager.py`, `report_manager.py`, `slack_reporter.py`, `screenshots.py`, `session_detector.py`, `error_handler.py`, `device_names.py`, `alttester_appname.py`, `google_play_helper.py`, `test_logger.py` |
| [handlers.md](handlers.md) | The 10 popup/flow handlers in `tests/handlers/` (daily login, album FTUE, beach buddies, permissions, piggy bank, league, facebook, info screen, FTUE, registry) |
| [core-and-scripts.md](core-and-scripts.md) | Engine & entry points — `run_this.py`, `core/execution_engine.py`, `agent.py`, `bridge.py`, `config.py`, `check_setup.py` |
| [webapp.md](webapp.md) | `webapp/app.py` — FastAPI endpoints, parallel slots, bridge/agent dispatch |

## Setup & operations (repo root)

| Doc | For |
|---|---|
| `../LAPTOP_SETUP.md` | Running on a teammate's own laptop + device |
| `../AGENT_SETUP.md` | Turning a laptop into a remote bridge/agent runner |
| `../SERVER_SETUP.md` | Hosting & maintaining the web app on the central server |
