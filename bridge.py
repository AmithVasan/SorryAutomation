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
import urllib.request
from urllib.parse import urlparse

SERVER = os.environ.get("SAT_SERVER", "").rstrip("/")
if not SERVER:
    print("❌ Set SAT_SERVER first, e.g.:\n"
          "   SAT_SERVER=http://<server-ip>:8000 python3 bridge.py")
    sys.exit(1)

SERVER_HOST    = urlparse(SERVER).hostname or "127.0.0.1"
ALT_PORT       = int(os.environ.get("ALT_PORT", "13000"))
ADB_RELAY_PORT = int(os.environ.get("ADB_RELAY_PORT", "5038"))
APPIUM_PORT    = int(os.environ.get("APPIUM_PORT", "4723"))
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


def register():
    ip = local_ip()
    devs = devices()
    ok = _post("/agent/register", {
        "agent_id": AGENT_ID, "name": NAME, "devices": devs, "kind": "bridge",
        "ip": ip, "adb_port": ADB_RELAY_PORT, "appium_url": f"http://{ip}:{APPIUM_PORT}",
    })
    log(f"{'registered' if ok else 'register FAILED (server reachable?)'}: "
        f"{NAME}  ip={ip}  devices={devs or '(none — plug in your device)'}")
    return devs


def start_appium():
    ap = _detect_appium()
    if not ap:
        log("⚠️ appium not found — install with:  npm i -g appium  &&  appium driver install uiautomator2")
        log("   continuing WITHOUT Appium (AltTester tests will run; IAP tests won't)")
        return None
    log(f"starting Appium: {ap} --address 0.0.0.0 --port {APPIUM_PORT}")
    p = subprocess.Popen([ap, "--address", "0.0.0.0", "--port", str(APPIUM_PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{APPIUM_PORT}/status", timeout=2) as r:
                if r.status == 200:
                    log("✅ Appium up")
                    return p
        except Exception:
            time.sleep(1)
    log("⚠️ Appium not healthy within 30s — continuing (check its output)")
    return p


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
    start_appium()
    register()
    log("✅ bridge ready — open the webapp on the server and click ▶ Run here on this device. "
        "(Leave this running; Ctrl+C to stop.)")

    last = devs
    try:
        while True:
            time.sleep(8)
            d = _get("/agent/poll", {"agent_id": AGENT_ID})
            if not d.get("known", True):
                register()                     # server restarted → re-register
            else:
                cur = devices()
                if cur != last:                # hot-plug / unplug → refresh
                    register()
                    last = cur
    except KeyboardInterrupt:
        log("stopping")


if __name__ == "__main__":
    main()
