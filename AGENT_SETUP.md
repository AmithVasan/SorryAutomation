# Remote agent setup (second laptop)

Turns a teammate's laptop into a runner: plug in their device, and the central
server (this Mac) can dispatch runs to it from the browser. The device stays on
the laptop; the agent runs the test locally and streams logs back.

## On the SERVER (this Mac) — already done
- Webapp running on `:8000`, AltTester server on `*:13000` (LAN-reachable ✔).
- Server address for agents: **http://GBL-Admins-MacBook-Air.local:8000**
  (or `http://<mac-ip>:8000`).

## On the AGENT laptop (one-time)
1. **Install the runtime** (same as `LAPTOP_SETUP.md`):
   - Python 3, then: `pip install Appium-Python-Client AltTester-Driver pymongo requests python-dotenv`
   - Appium 2: `npm i -g appium` + `appium driver install uiautomator2`
   - Android platform-tools (`adb`)
2. **Copy the repo** to the laptop (the agent runs `run_this.py` from it).
3. **Copy `.env`** into the repo root (Mongo + Slack — the tests need it).
4. **Device:** USB debugging on, plugged in, and on the **office Wi-Fi**
   (the game reaches the central AltTester over the LAN).
5. **Do NOT run AltTester Desktop on this laptop** — the agent uses port 13000
   for a relay to the central server; the license lives only on the server.

## Start the agent
From the repo root, in the same Python you installed the deps into:
```bash
SAT_SERVER=http://GBL-Admins-MacBook-Air.local:8000 \
SAT_AGENT_NAME="QA Laptop 2" \
python3 agent.py
```
It registers, then waits for jobs. You'll see it appear under **Remote devices**
in the browser.

Env vars:
| Var | Meaning | Default |
|-----|---------|---------|
| `SAT_SERVER` | Central server URL | `http://GBL-Admins-MacBook-Air.local:8000` |
| `SAT_AGENT_NAME` | Name shown in the GUI | hostname |
| `SAT_AGENT_ID` | Stable id | hostname |
| `SAT_PROJECT` | Project label | `Sorry! World` |

## Make it auto-start (so daily use is hands-off)
So nobody has to launch the agent manually each time, install it as a LaunchAgent —
it starts at login and restarts if it crashes, so the agent is always running and
daily use is just *plug in device → open browser → Run here*.

```bash
# edit the <PLACEHOLDERS> in the plist for this laptop first
cp com.gameberrylabs.automation-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gameberrylabs.automation-agent.plist
tail -f webapp/runs/agent.log        # watch it register
```
Requires the laptop to stay awake + logged in (same as the server). The device
also needs its one-time "Allow USB debugging" prompt accepted.

## Using it
1. On any laptop, open the server URL in a browser.
2. Under **Remote devices**, find the agent (green = idle).
3. Pick the **project / run type / toggles** at the top, then click **▶ Run here**
   on that agent.
4. The test runs on the agent's device; live logs stream into the console, and
   the run shows up in History.

## How the AltTester routing works (no build change)
The agent sets `adb reverse tcp:13000 tcp:13000` and runs a tiny TCP relay
(`laptop:13000 → server:13000`). So both the game and the AltDriver reach the
**central** AltTester using the default `127.0.0.1:13000` — the license stays on
the server.

## Limits (for now)
- **Run one at a time** across the whole team: the AltTester Pro license allows
  **2 concurrent games**, and every run currently uses the same `app_name`
  (`sorry`), so simultaneous runs on the same project would collide. Per-device
  `app_name`s (to truly parallelize) are the next step.
- The agent runs the repo copied to that laptop. Auto-pulling scripts from the
  server at job time is a later enhancement.
