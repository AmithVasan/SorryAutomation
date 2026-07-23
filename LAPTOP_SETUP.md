# Laptop setup — run the automation on YOUR device (office LAN)

After this one-time setup, using it is **zero-input**: plug in your device →
open the GUI → click **Run**. Toolchain paths (`adb`, `appium`, emulator, build
folder) are auto-detected — you don't configure them.

## What you need (install once)

1. **Android platform-tools (`adb`)** — via Android Studio, or `brew install android-platform-tools` (Mac) / your OS package. Auto-detected from `PATH`, `ANDROID_HOME`, or the standard SDK location.
2. **Appium 2** — `npm install -g appium` then `appium driver install uiautomator2`. Needs Node.js.
3. **Python 3.8+** and the project dependencies (see step 5).
4. **The project** — clone/copy this repo.
5. **A `.env` file** in the repo root — get the shared one from the admin (it holds the Mongo connection + Slack token). Without it, DB steps and Slack reports won't work.
6. **Your device**, with:
   - USB debugging **on**, plugged into your laptop (authorize the RSA prompt),
   - connected to the **office Wi-Fi** (same network as the central server),
   - your **test account** signed in.

> The **AltTester Desktop app is NOT installed on your laptop.** The licensed
> AltTester server runs on the central server; your laptop just points at it.

## Steps

```bash
# 1. Get the code
git clone <repo-url> && cd Sorry     # or copy the folder

# 2. Install Python deps (use the SAME python you'll run with)
python3 -m pip install -r webapp/requirements.txt
python3 -m pip install Appium-Python-Client AltTester-Driver pymongo requests python-dotenv

# 3. Put the shared .env in the repo root (from admin)

# 4. Point at the central AltTester server (ask admin for the IP)
export SAT_ALT_HOST=<central-server-ip>

# 5. Check everything is ready
python3 check_setup.py            # prints ✅ / ❌ per requirement

# 6. Start the GUI and run
uvicorn webapp.app:app --host 127.0.0.1 --port 8000
# open http://localhost:8000 → pick options → Run
```

> ⚠️ **Use one interpreter consistently.** Run `check_setup.py`, `pip install`,
> and `uvicorn` with the *same* `python3` (the GUI launches the runner with
> whichever python started it). If deps show missing, you're likely on a
> different python — check `which python3`.

## What still needs the admin / central server

- The **central server** must be running AltTester Desktop (with the license) on
  port `13000`, reachable on the LAN. `check_setup.py` verifies this when
  `SAT_ALT_HOST` is set.
- The **game→server hop**: point the in-game AltTester dialog at the server IP,
  or use `adb reverse` + a local relay. (Ask admin which method is in use.)
- **Concurrency** is capped by the AltTester license (Pro = 2 games at once);
  extra runs queue.

## Optional overrides (normally unneeded — everything auto-detects)

| Env var          | Overrides                                  |
|------------------|--------------------------------------------|
| `SAT_ALT_HOST`   | Central AltTester server IP (default local) |
| `SAT_ADB` / `ADB_PATH` | Path to `adb`                        |
| `SAT_APPIUM` / `APPIUM_PATH` | Path to `appium`               |
| `SAT_APK_FOLDER` / `APK_FOLDER` | Build download/pick folder  |
| `SAT_PYTHON`     | Interpreter the GUI uses to launch the runner |
