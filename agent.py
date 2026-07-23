"""
agent.py — Automation Runner remote agent.

Runs on a teammate's laptop with their device plugged in via USB. It registers
with the central server (the webapp), waits for a job, and when one arrives it
runs `run_this.py` LOCALLY against the USB device — streaming the console back
to the server so it shows in the browser. The device never leaves this laptop.

Why an agent is needed: Appium drives a device over ADB, which is host-local —
so the test must execute on the machine the device is attached to. The agent is
that local executor; the browser (served by the central server) is just the
trigger + live view.

AltTester routing: the central server holds the AltTester license. The agent
sets `adb reverse tcp:13000 tcp:13000` and runs a tiny TCP relay
(localhost:13000 → <server>:13000), so both the game and the AltDriver reach the
central AltTester with NO build change and the default 127.0.0.1 config.

Run it (from the repo root, in the same venv as the automation):
    SAT_SERVER=http://GBL-Admins-MacBook-Air.local:8000 \
    SAT_AGENT_NAME="QA Laptop 2" \
    python3 agent.py

Env:
    SAT_SERVER      central server base URL (required; e.g. http://<mac-ip>:8000)
    SAT_AGENT_NAME  friendly name shown in the GUI (default: hostname)
    SAT_AGENT_ID    stable id (default: hostname)
    SAT_PROJECT     project label (default: "Sorry! World")
    SAT_ALT_PORT    AltTester port (default: 13000)
"""

import os
import sys
import time
import socket
import threading
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
from utils.env_config import detect_adb          # noqa: E402

SERVER   = os.environ.get("SAT_SERVER", "http://GBL-Admins-MacBook-Air.local:8000").rstrip("/")
ALT_HOST = urlparse(SERVER).hostname or "127.0.0.1"
ALT_PORT = int(os.environ.get("SAT_ALT_PORT", "13000"))
AGENT_ID = os.environ.get("SAT_AGENT_ID") or socket.gethostname()
NAME     = os.environ.get("SAT_AGENT_NAME", AGENT_ID)
PROJECT  = os.environ.get("SAT_PROJECT", "Sorry! World")
ADB      = detect_adb()
PYTHON   = sys.executable


def log(msg):
    print(f"[agent] {msg}", flush=True)


# ── device helpers ────────────────────────────────────────────────────────────
def list_devices():
    try:
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10).stdout
        return [l.split("\t")[0] for l in out.splitlines()[1:]
                if l.strip() and "\tdevice" in l]
    except Exception as e:
        log(f"adb devices failed: {e}")
        return []


# ── AltTester relay: localhost:ALT_PORT → <server>:ALT_PORT ───────────────────
def _pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass


def _relay(listen_port, dst_host, dst_port, stop_evt):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", listen_port))
    except Exception as e:
        log(f"relay bind failed on {listen_port}: {e} (is AltTester Desktop running here? it shouldn't be)")
        return
    srv.listen(50)
    srv.settimeout(1.0)
    log(f"relay up: 127.0.0.1:{listen_port} → {dst_host}:{dst_port}")
    while not stop_evt.is_set():
        try:
            cli, _ = srv.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        try:
            up = socket.create_connection((dst_host, dst_port), timeout=10)
        except Exception as e:
            log(f"relay upstream connect failed: {e}")
            cli.close()
            continue
        threading.Thread(target=_pipe, args=(cli, up), daemon=True).start()
        threading.Thread(target=_pipe, args=(up, cli), daemon=True).start()
    srv.close()


# ── server API ─────────────────────────────────────────────────────────────────
def register(devices):
    try:
        requests.post(f"{SERVER}/agent/register",
                      json={"agent_id": AGENT_ID, "name": NAME, "devices": devices},
                      timeout=10)
        log(f"registered as '{NAME}' ({AGENT_ID}) devices={devices}")
        return True
    except Exception as e:
        log(f"register failed: {e}")
        return False


def poll():
    try:
        r = requests.get(f"{SERVER}/agent/poll", params={"agent_id": AGENT_ID}, timeout=15)
        d = r.json()
        return d.get("job"), d.get("known", True)
    except Exception:
        return None, True


def post_log(run_id, text):
    try:
        requests.post(f"{SERVER}/agent/log",
                      json={"agent_id": AGENT_ID, "run_id": run_id, "text": text},
                      timeout=10)
    except Exception:
        pass


def post_result(run_id, status, rc):
    try:
        requests.post(f"{SERVER}/agent/result",
                      json={"agent_id": AGENT_ID, "run_id": run_id,
                            "status": status, "returncode": rc},
                      timeout=10)
    except Exception:
        pass


# ── run a dispatched job ────────────────────────────────────────────────────────
def _heartbeat(run_id, stop_evt):
    while not stop_evt.wait(10):
        post_log(run_id, "")   # empty → server just bumps last_seen


def run_job(job):
    run_id = job["run_id"]
    devices = list_devices()
    if not devices:
        post_log(run_id, "[agent] ❌ no device connected — aborting\n")
        post_result(run_id, "failed", -1)
        return
    device = devices[0]
    log(f"running job {run_id} on {device}")

    stop_evt = threading.Event()
    # Route the game + AltDriver to the CENTRAL AltTester (no build change).
    subprocess.run([ADB, "-s", device, "reverse", f"tcp:{ALT_PORT}", f"tcp:{ALT_PORT}"], check=False)
    threading.Thread(target=_relay, args=(ALT_PORT, ALT_HOST, ALT_PORT, stop_evt), daemon=True).start()
    threading.Thread(target=_heartbeat, args=(run_id, stop_evt), daemon=True).start()

    cmd = [PYTHON, "-u", "run_this.py"]
    if job.get("mode") == "test" and job.get("test"):
        cmd += ["--test", job["test"]]
    else:
        cmd += ["--run-type", job.get("run_type", "complete")]
    cmd += ["--slack", job.get("slack", "off"), "--report", job.get("report", "off")]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["SAT_ADB"] = ADB                          # ensure the run uses this device's adb
    post_log(run_id, f"[agent] starting: {' '.join(cmd)}\n")

    rc = -1
    try:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=env, text=True, bufsize=1)
        for line in proc.stdout:
            post_log(run_id, line)
        rc = proc.wait()
    except Exception as e:
        post_log(run_id, f"[agent] ❌ run error: {e}\n")
    finally:
        stop_evt.set()
        subprocess.run([ADB, "-s", device, "reverse", "--remove", f"tcp:{ALT_PORT}"], check=False)

    post_result(run_id, "passed" if rc == 0 else "failed", rc)
    log(f"job {run_id} finished rc={rc}")


# ── main loop ────────────────────────────────────────────────────────────────
def main():
    log(f"server={SERVER}  alt-relay→{ALT_HOST}:{ALT_PORT}  adb={ADB}")
    register(list_devices())
    last_devices = None
    while True:
        job, known = poll()
        if not known:
            register(list_devices())             # server restarted → re-register
            time.sleep(1)
            continue
        if job:
            run_job(job)
        else:
            # refresh device list occasionally so hot-plugs show up
            devs = list_devices()
            if devs != last_devices:
                register(devs)
                last_devices = devs
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped")
