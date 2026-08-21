# Server setup — host & maintain the automation web app (Mac Mini)

How to run the Automation Runner web GUI on the **central server** (the Mac Mini)
and keep it running, **without Claude**. Companion to `LAPTOP_SETUP.md` (teammate
laptops) and `AGENT_SETUP.md` (remote bridge). Everything here is run **on the
server itself** (directly or over Screen Sharing).

> **What the web app is:** one lightweight `uvicorn` process (FastAPI) on
> **:8000**. It does *not* run tests itself — each run is a `run_this.py`
> subprocess it launches and whose log it streams. So "hosting the web app" =
> keeping that one process alive. The heavy work (Appium, AltTester, adb) lives
> in the per-run subprocesses.

---

## 0. Prerequisites (one-time on the server)

Same toolchain as a laptop (see `LAPTOP_SETUP.md`), plus the repo and `.env`:

1. **Android platform-tools (`adb`)**, **Appium 2** (`npm i -g appium` +
   `appium driver install uiautomator2`), **Python 3.8+**.
2. **The repo** cloned/copied to the server, e.g. `~/Sorry`.
3. **`.env`** in the repo root (Mongo + Slack) — from the admin.
4. **AltTester Desktop** installed **with the license** (server only).
5. Python deps installed **into the same interpreter you'll host with**:

   ```bash
   cd ~/Sorry
   python3 -m pip install -r webapp/requirements.txt
   python3 -m pip install Appium-Python-Client AltTester-Driver pymongo requests python-dotenv
   ```

6. Verify the box is ready:

   ```bash
   python3 check_setup.py
   ```

> ⚠️ **One interpreter, consistently.** The web app launches `run_this.py` with
> **whichever `python3` started uvicorn**. Use the *same* `python3` for
> `pip install`, `check_setup.py`, and hosting. Confirm with `which python3`.

---

## 1. Host it manually (foreground) — for a quick test

```bash
cd ~/Sorry
python3 -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000
```

- On the server: <http://localhost:8000>
- From the LAN / over VPN: `http://<server-static-ip>:8000`
- **Ctrl-C** to stop.

This dies when you close the Terminal or log out — fine for testing, **not** for a
server. For always-on, use the service below.

---

## 2. Host it as an always-on service (LaunchAgent) — the real way

A macOS **LaunchAgent** starts the web app at login and restarts it if it
crashes. The repo ships a template: `webapp/com.gameberrylabs.automation-runner.plist`.

### 2a. Point the plist at THIS machine

Its paths are for the old laptop — edit these keys before installing:

| Key in the plist | Set to (on the Mac Mini) | Find it with |
|---|---|---|
| `ProgramArguments` → first `<string>` | the Python that has the deps, e.g. `/opt/homebrew/bin/python3` | `which python3` |
| `WorkingDirectory` | the repo path, e.g. `/Users/<user>/Sorry` | `pwd` in the repo |
| `EnvironmentVariables` → `PATH` | include the server's `platform-tools` dir | `dirname $(which adb)` |
| `StandardOutPath` / `StandardErrorPath` | `<repo>/webapp/runs/server.log` | — |

> The Python path is the big one: **do not assume** `/usr/local/bin/python3` or
> `/opt/homebrew/bin/python3` — use exactly what `which python3` prints on the
> Mac Mini.

### 2b. Install & start

```bash
cp webapp/com.gameberrylabs.automation-runner.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gameberrylabs.automation-runner.plist
```

It's now running on :8000, starts at login (`RunAtLoad`), and auto-restarts on
crash (`KeepAlive`).

> **Auto-login is required.** A LaunchAgent only runs while a user is **logged
> in**. On a headless server, enable **auto-login** for the automation account
> (and disable sleep) so the service — and AltTester Desktop's GUI session —
> come up after a reboot with nobody present.

---

## 3. Maintain it — day-to-day commands

Run these from the repo root (`cd ~/Sorry`).

**Is it up?**
```bash
launchctl list | grep automation-runner
```
```bash
curl -s http://localhost:8000/status
```

**Watch the log**
```bash
tail -f webapp/runs/server.log
```

**Restart** (e.g. after pulling a code change)
```bash
launchctl kickstart -k gui/$(id -u)/com.gameberrylabs.automation-runner
```

**Update the code, then restart**
```bash
cd ~/Sorry && git pull
launchctl kickstart -k gui/$(id -u)/com.gameberrylabs.automation-runner
```

**Stop it** (and keep it stopped)
```bash
launchctl unload ~/Library/LaunchAgents/com.gameberrylabs.automation-runner.plist
```

**Start it again**
```bash
launchctl load ~/Library/LaunchAgents/com.gameberrylabs.automation-runner.plist
```

> ⚠️ **`KeepAlive` means a plain `kill` won't stop it** — launchd just respawns
> it. To actually stop it, `unload` (or `launchctl bootout gui/$(id -u)/com.gameberrylabs.automation-runner`).

---

## 4. Companion services (must also be up for runs to pass)

The web app only supervises runs. A run also needs:

- **AltTester Desktop** — GUI app, **must be open and licensed** (`:13000`). It
  does not auto-start; launch it after login (add it to **System Settings →
  General → Login Items** so it comes up automatically).
- **Appium** — **auto-started per run** by `run_this.py` (`start_appium()`); you
  only need the `appium` binary installed. No manual start.
- **MongoDB** — if running **locally** on the Mac Mini, make sure the service is
  started (e.g. `brew services start mongodb-community`). If `MONGO_URI` points
  at a hosted cluster, nothing to run locally.

---

## 5. Gotchas & quick troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Not reachable from another machine | Host must be `0.0.0.0` (it is, in the plist). Allow **incoming :8000** in the macOS firewall; use the server's **static IP**; off-site must be on the **VPN**. |
| Service starts then dies immediately | Read `webapp/runs/server.log`. Usually: wrong `python3` (deps missing), missing `.env`, or wrong `WorkingDirectory`. |
| `Address already in use` on :8000 | A stale uvicorn is running: `lsof -iTCP:8000 -sTCP:LISTEN` then `kill <pid>`, or `pkill -f "webapp.app:app"`, then reload. |
| Web app is up but runs fail | Not a hosting problem — check the **run's** log in the GUI. Confirm AltTester Desktop is open + licensed, device is authorised (`adb devices`), and `.env`/Mongo are reachable. |
| Changes not taking effect | You edited code but didn't restart — `launchctl kickstart -k …` (see §3). |
| Reboot didn't bring it back | Auto-login not enabled, or the machine slept. Enable auto-login + disable sleep (§2b). |

---

## 6. TL;DR

```bash
# host now (foreground, testing)
cd ~/Sorry && python3 -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000

# host forever (service): edit the plist paths, then
cp webapp/com.gameberrylabs.automation-runner.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gameberrylabs.automation-runner.plist

# maintain
tail -f webapp/runs/server.log                                             # logs
launchctl kickstart -k gui/$(id -u)/com.gameberrylabs.automation-runner    # restart
launchctl unload ~/Library/LaunchAgents/com.gameberrylabs.automation-runner.plist  # stop
```
