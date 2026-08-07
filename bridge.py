#!/usr/bin/env python3
"""
bridge.py — Automation Runner LAPTOP BRIDGE (Phase 2).

Plug in your Android device (USB debugging on), then run ONE command:

    SAT_SERVER=http://<server-ip>:8000 python3 bridge.py

This turns your laptop into a thin bridge so the CENTRAL SERVER can run the test
scripts against YOUR plugged-in device. The scripts and the AltTester license
stay on the server — they never touch this laptop. This file only exposes the
device and registers with the server:

  • adb server (localhost) with your device
  • adb relay        0.0.0.0:5038  → 127.0.0.1:5037     (server drives adb)
  • AltTester relay  0.0.0.0:13000 → <server>:13000     (game → licensed AltTester)
  • Appium           0.0.0.0:4723                        (UiAutomator2, next to device)

Then open the webapp on the server and click "▶ Run here" on this device.

Requires on this laptop: python3, adb (Android platform-tools), and — for IAP
tests — appium (`npm i -g appium` + `appium driver install uiautomator2`).
Self-contained: standard library only, no repo checkout needed.

Env:
    SAT_SERVER       central server base URL (required, e.g. http://10.0.0.5:8000)
    SAT_AGENT_NAME   friendly name shown in the webapp (default: hostname)
    SAT_AGENT_ID     stable id (default: hostname)
    ADB_RELAY_PORT   default 5038      ALT_PORT default 13000     APPIUM_PORT default 4723
    SAT_ADB / SAT_APPIUM  explicit adb / appium paths (else auto-detected)
"""
import os
import sys
import json
import time
import socket
import shutil
import threading
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlparse, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVER = os.environ.get("SAT_SERVER", "").rstrip("/")
if not SERVER:
    print("❌ Set SAT_SERVER first, e.g.:\n"
          "   SAT_SERVER=http://<server-ip>:8000 python3 bridge.py")
    sys.exit(1)

SERVER_HOST    = urlparse(SERVER).hostname or "127.0.0.1"
ALT_PORT       = int(os.environ.get("ALT_PORT", "13000"))
ADB_RELAY_PORT = int(os.environ.get("ADB_RELAY_PORT", "5038"))
APPIUM_PORT    = int(os.environ.get("APPIUM_PORT", "4723"))
INSTALL_PORT   = int(os.environ.get("INSTALL_PORT", "8799"))
NAME           = os.environ.get("SAT_AGENT_NAME", socket.gethostname())
AGENT_ID       = os.environ.get("SAT_AGENT_ID", socket.gethostname())


def log(m):
    print(f"[bridge] {m}", flush=True)


def _detect_adb():
    for c in (os.environ.get("SAT_ADB"), os.environ.get("ADB_PATH"), shutil.which("adb"),
              os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
              os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
              os.path.expanduser("~/AppData/Local/Android/Sdk/platform-tools/adb.exe")):
        if c and os.path.exists(c):
            return c
    return "adb"   # hope it's on PATH


def _detect_appium():
    return os.environ.get("SAT_APPIUM") or shutil.which("appium")


ADB = _detect_adb()


def local_ip():
    """The laptop IP the server can reach (the outbound interface toward it)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((SERVER_HOST, 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def devices():
    try:
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10).stdout
        return [l.split("\t")[0] for l in out.splitlines()[1:] if "\tdevice" in l]
    except Exception as e:
        log(f"adb devices failed: {e}")
        return []


_NAME_PROPS = ("ro.product.brand", "ro.product.manufacturer", "ro.product.model",
               "ro.product.marketname", "ro.vendor.product.marketname",
               "ro.product.vendor.marketname", "ro.product.odm.marketname",
               "ro.config.marketing_name")


def device_props(serials):
    """Per-device name props so the server can show a friendly device name
    (Samsung Galaxy S23 FE) instead of a serial. {serial: {prop: value}}."""
    out = {}
    for s in serials:
        info = {}
        try:
            res = subprocess.run([ADB, "-s", s, "shell", "getprop"],
                                 capture_output=True, text=True, timeout=8).stdout
            props = {}
            for line in res.splitlines():
                line = line.strip()
                if line.startswith("[") and "]: [" in line:
                    k, v = line[1:].split("]: [", 1)
                    props[k] = v.rstrip("]")
            info = {k: props.get(k, "") for k in _NAME_PROPS if props.get(k)}
        except Exception:
            info = {}
        out[s] = info
    return out


# ── TCP relay ────────────────────────────────────────────────────────────────
def _pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass


def _relay(listen_port, dst_host, dst_port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", listen_port))
    except Exception as e:
        log(f"❌ relay bind failed on {listen_port}: {e}")
        return
    srv.listen(64)
    log(f"relay 0.0.0.0:{listen_port} → {dst_host}:{dst_port}")
    while True:
        try:
            c, _ = srv.accept()
        except Exception:
            break
        try:
            u = socket.create_connection((dst_host, dst_port), timeout=10)
        except Exception as e:
            log(f"relay upstream {dst_host}:{dst_port} failed: {e}")
            c.close()
            continue
        threading.Thread(target=_pipe, args=(c, u), daemon=True).start()
        threading.Thread(target=_pipe, args=(u, c), daemon=True).start()


# ── server API (stdlib urllib) ─────────────────────────────────────────────────
def _post(path, obj):
    try:
        data = json.dumps(obj).encode()
        req = urllib.request.Request(SERVER + path, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception:
        return False


def _get(path, params):
    try:
        q = "&".join(f"{k}={v}" for k, v in params.items())
        with urllib.request.urlopen(f"{SERVER}{path}?{q}", timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def _appium_up():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{APPIUM_PORT}/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def register():
    ip = local_ip()
    devs = devices()
    appium_ok = _appium_up()
    # Advertise the Appium URL ONLY when it's actually reachable — otherwise the
    # server would route a run to a dead Appium and fail 30s later. None = "not up".
    ok = _post("/agent/register", {
        "agent_id": AGENT_ID, "name": NAME, "devices": devs, "kind": "bridge",
        "ip": ip, "adb_port": ADB_RELAY_PORT,
        "appium_url": (f"http://{ip}:{APPIUM_PORT}" if appium_ok else None),
        "install_url": f"http://{ip}:{INSTALL_PORT}",
        "device_props": device_props(devs),
    })
    log(f"{'registered' if ok else 'register FAILED (server reachable?)'}: "
        f"{NAME}  ip={ip}  devices={devs or '(none — plug in your device)'}  "
        f"appium={'up' if appium_ok else 'DOWN'}")
    return devs


def _ensure_uia2_driver(ap):
    """UiAutomator2 driver is required to drive the device; install once if absent."""
    try:
        r = subprocess.run([ap, "driver", "list", "--installed"],
                           capture_output=True, text=True, timeout=60)
        if "uiautomator2" in (r.stdout + r.stderr):
            return
        log("installing Appium uiautomator2 driver (one-time)…")
        subprocess.run([ap, "driver", "install", "uiautomator2"], timeout=600)
    except Exception as e:
        log(f"uiautomator2 driver check/install skipped: {e}")


def _android_sdk_root():
    """A directory Appium can use as ANDROID_HOME (must contain platform-tools/adb).
    Uses the real SDK if adb lives in one; otherwise (e.g. Homebrew adb) builds a
    minimal SDK dir with a symlink to adb — enough for the uiautomator2 driver,
    which errors out if neither ANDROID_HOME nor ANDROID_SDK_ROOT is set."""
    adb = os.path.abspath(ADB) if (ADB and os.path.exists(ADB)) else (shutil.which("adb") or "")
    if adb:
        root = os.path.dirname(os.path.dirname(adb))
        if os.path.isdir(os.path.join(root, "platform-tools")):
            return root
        try:  # adb not in a standard SDK layout → construct a minimal one
            home = os.path.expanduser("~/.sat_android_home")
            ptdir = os.path.join(home, "platform-tools")
            os.makedirs(ptdir, exist_ok=True)
            link = os.path.join(ptdir, os.path.basename(adb))
            if not os.path.exists(link):
                os.symlink(adb, link)
            return home
        except Exception:
            pass
    for c in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
              os.path.expanduser("~/Library/Android/sdk"), os.path.expanduser("~/Android/Sdk")):
        if c and os.path.isdir(os.path.join(c or "", "platform-tools")):
            return c
    return None


def _kill_appium_port():
    """Best-effort: stop whatever is listening on the Appium port (macOS/Linux)."""
    try:
        pids = subprocess.run(["lsof", "-nP", f"-iTCP:{APPIUM_PORT}", "-sTCP:LISTEN", "-t"],
                              capture_output=True, text=True, timeout=8).stdout.split()
        for pid in pids:
            subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
        if pids:
            time.sleep(1.5)
    except Exception:
        pass


def start_appium():
    ap = _detect_appium()
    if not ap:
        log("⚠️ appium not found — re-run the one-command setup (it installs Appium), or:")
        log("     npm i -g appium  &&  appium driver install uiautomator2")
        log("   continuing WITHOUT Appium — the server will refuse runs until it is up.")
        return None

    root = _android_sdk_root()
    env = os.environ.copy()
    if root:
        env["ANDROID_HOME"] = root
        env["ANDROID_SDK_ROOT"] = root

    if _appium_up():
        # An Appium is already listening — but if it was started WITHOUT the SDK
        # env, uiautomator2 fails with "Neither ANDROID_HOME nor ANDROID_SDK_ROOT
        # ...". We own Appium here, so restart it with the env to be certain.
        log("Appium already running — restarting it with the Android SDK env…")
        _kill_appium_port()

    _ensure_uia2_driver(ap)
    log(f"starting Appium: {ap} --address 0.0.0.0 --port {APPIUM_PORT}  (ANDROID_HOME={root})")
    p = subprocess.Popen([ap, "--address", "0.0.0.0", "--port", str(APPIUM_PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(30):
        if _appium_up():
            log("✅ Appium up")
            return p
        time.sleep(1)
    log("⚠️ Appium not healthy within 30s — continuing (check its output)")
    return p


# ── local install server ──────────────────────────────────────────────────────
# The server asks us (POST /install {build, serial}) to pull the build from the
# server over HTTP and `adb install` it LOCALLY over USB — reliable, unlike the
# server pushing a ~380MB APK back over the adb relay.
def _local_install(build, serial):
    if not build:
        return False, "no build specified"
    url = f"{SERVER}/build?name={quote(build)}"
    tmp = os.path.join(tempfile.gettempdir(), build)
    try:
        log(f"install: downloading {build} from server…")
        urllib.request.urlretrieve(url, tmp)
    except Exception as e:
        return False, f"download failed: {e}"
    try:
        args = [ADB] + (["-s", serial] if serial else []) + ["install", "-r", "-d", tmp]
        log(f"install: adb install locally on {serial or 'default device'}…")
        r = subprocess.run(args, capture_output=True, text=True, timeout=1200)
        out = (r.stdout + r.stderr).strip()
        ok = not (r.returncode != 0 or "Failure" in out or "Exception" in out
                  or ("error" in out.lower() and "0 errors" not in out.lower()))
        log(f"install: {'OK' if ok else 'FAILED'} → {out}")
        return ok, out
    except Exception as e:
        return False, f"adb install failed: {e}"
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


class _InstallHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/") != "/install":
            self._reply({"ok": False, "output": "not found"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._reply({"ok": False, "output": f"bad request: {e}"}, 400)
            return
        ok, out = _local_install(os.path.basename(body.get("build", "") or ""),
                                 body.get("serial", ""))
        self._reply({"ok": ok, "output": out})


def start_install_server():
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", INSTALL_PORT), _InstallHandler)
    except Exception as e:
        log(f"⚠️ install server bind failed on {INSTALL_PORT}: {e}")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"install server on 0.0.0.0:{INSTALL_PORT}")


def main():
    log(f"server={SERVER}   adb={ADB}")
    subprocess.run([ADB, "start-server"], capture_output=True)
    devs = devices()
    if devs:
        log(f"device(s): {devs}")
        for dv in devs:   # prime the AltTester reverse (server also sets it per-run)
            subprocess.run([ADB, "-s", dv, "reverse", f"tcp:{ALT_PORT}", f"tcp:{ALT_PORT}"],
                           capture_output=True)
    else:
        log("⚠️ no device seen yet — plug it in + accept 'Allow USB debugging'; it'll be picked up")

    threading.Thread(target=_relay, args=(ADB_RELAY_PORT, "127.0.0.1", 5037), daemon=True).start()
    threading.Thread(target=_relay, args=(ALT_PORT, SERVER_HOST, ALT_PORT), daemon=True).start()
    start_install_server()
    start_appium()
    register()
    log("✅ bridge ready — open the webapp on the server and click ▶ Run here on this device. "
        "(Leave this running; Ctrl+C to stop.)")

    last = devs
    last_appium = _appium_up()
    try:
        while True:
            time.sleep(8)
            d = _get("/agent/poll", {"agent_id": AGENT_ID})
            if not d.get("known", True):
                register()                     # server restarted → re-register
                last, last_appium = devices(), _appium_up()
            else:
                cur, cur_appium = devices(), _appium_up()
                if cur != last or cur_appium != last_appium:   # hot-plug / Appium came up → refresh
                    register()
                    last, last_appium = cur, cur_appium
    except KeyboardInterrupt:
        log("stopping")


if __name__ == "__main__":
    main()
