# Sorry! Automation — Tier 1 Web GUI

A small web page that replaces the Eclipse "run + type a choice" step. Pick a
run type (or a single test), tick **Slack message** / **HTML report**, hit
**Run**. The page launches the existing runner and streams its console live.

It does **not** change how tests run — it just feeds `run_this.py` the same
selections you used to type by hand:

```
python run_this.py --run-type complete --slack on --report on
```

## Run it

From the **repo root**, in the **same virtualenv** that runs the automation
(so Appium / AltTester / etc. resolve):

```bash
pip install -r webapp/requirements.txt
uvicorn webapp.app:app --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>. From another machine on the LAN/VPN, use
`http://<this-mac-ip>:8000`.

The device is tethered to **this** machine, so the web app must run here (or on
the future server the device is tethered to).

## What each control does

| Control        | Effect                                                            |
|----------------|-------------------------------------------------------------------|
| Project        | One entry today (this repo). Multi-project is Tier 2.             |
| Run type       | `--run-type <smoke\|regression\|iap\|bat\|complete>`             |
| Single test    | `--test "<name>"` — runs just that test                          |
| Slack message  | `--slack on\|off` → `SAT_ENABLE_SLACK`                           |
| HTML report    | `--report on\|off` → `SAT_ENABLE_HTML`                           |
| Device pill    | **Free** / **Busy** — Busy while a run is active                 |
| Report         | Opens the latest `automation_report.html`                        |

## Scope (Tier 1) and what's next

- **One run at a time.** A second run while one is active is refused (HTTP 409).
  A real **queue** is Tier 2.
- **Single project / single device.** The project dropdown and multi-device
  pool are Tier 2.
- **Scheduling** (auto-run on a new tagged Slack build, with an on/off toggle)
  is Tier 2.

## Office-LAN mode: run on YOUR device against a central AltTester server

By default everything runs locally (AltTester server on this machine). To let each
teammate run on their **own** device against a **shared, licensed** AltTester
server on a central box:

**Central server (once):** install AltTester Desktop, activate the license, start
its server on port 13000, and make sure it accepts LAN connections — verify from
another machine with `nc -vz <server-ip> 13000` (if it only binds localhost, run
the headless server `-batchmode -nographics -port 13000`, or add a relay
`socat TCP-LISTEN:13000,fork TCP:127.0.0.1:13000`).

**Each laptop:**
1. Install deps: `pip install -r webapp/requirements.txt` plus the automation deps
   (appium, alttester client, etc.). **You do NOT install AltTester Desktop here.**
2. Connect the device via USB (USB debugging on); keep it on the office Wi-Fi.
3. Point the scripts at the central server, then start the GUI:
   ```bash
   export SAT_ALT_HOST=<central-server-ip>
   uvicorn webapp.app:app --host 127.0.0.1 --port 8000
   ```
   Runs execute **locally** against your device; AltTester traffic goes to the
   central server. When `SAT_ALT_HOST` is unset it falls back to `127.0.0.1`
   (fully local), so nothing changes for the single-machine setup.

**Do you need AltTester Desktop on the laptop?** No. Only the central server runs
it (that's where the license lives). The laptop needs Python + Appium + ADB + the
`alttester` **Python client** (a pip package — the `AltDriver`, not the Desktop app).

**Game → central server (one remaining piece):** `SAT_ALT_HOST` routes the
*script's* AltDriver. The *game* is a separate connection and also needs to reach
the central server — either set the server IP in the in-game AltTester dialog
(no rebuild), or keep the game on `127.0.0.1` and add `adb reverse` + a local
relay to the server. Pick one once the central server exists.

**Concurrency** is capped by your AltTester licensed connections, not by the number
of laptops.

## Notes

- Optional env overrides: `SAT_ALT_HOST` (central AltTester server IP; default
  `127.0.0.1`), `SAT_PYTHON` (interpreter used to launch the runner), `SAT_ADB`
  (path to `adb` for the connected-devices status).
- Per-run console logs are written to `webapp/runs/` (git-ignored).
- The interactive Eclipse flow is untouched — `python run_this.py` with no args
  still shows the old menu.
