"""
webapp/app.py — web GUI for the Sorry automation suite.

Replaces the Eclipse "run + type a choice" step with a web page. Pick a project,
a run type (or a single test), tick Slack / HTML report, and hit Run. The backend
launches the EXISTING runner non-interactively:

    python run_this.py --run-type <type> --slack on|off --report on|off

…as a subprocess, streams its console output live, keeps a short history of past
runs, and shows the device as Busy / Free. It changes nothing about how the tests
themselves run.

Run it (from the repo root, in the SAME virtualenv as the automation):
    pip install -r webapp/requirements.txt
    uvicorn webapp.app:app --host 0.0.0.0 --port 8000
"""

import os
import re
import sys
import json
import time
import logging
import signal
import shutil
import threading
import subprocess
import io
import base64
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ─────────────────────────────────────────────────────────────────────────────
# Paths & static config
# ─────────────────────────────────────────────────────────────────────────────
WEBAPP_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBAPP_DIR.parent                      # where run_this.py lives
RUNS_DIR = WEBAPP_DIR / "runs"                      # per-run console logs + metadata
RUNS_DIR.mkdir(exist_ok=True)

HISTORY_LIMIT = 10     # runs shown in the History dropdown
KEEP_RUNS     = 20     # per-run log/metadata files kept on disk (older pruned)

# Interpreter used to launch run_this.py.  Defaults to the one running this app
# (so run in the automation venv).  Override with SAT_PYTHON if needed.
PYTHON = os.environ.get("SAT_PYTHON", sys.executable)

# Make tests.test_registry importable for the test dropdown (pure metadata).
sys.path.insert(0, str(REPO_ROOT))
import importlib
try:
    import tests.test_registry as _registry_mod
except Exception:
    _registry_mod = None

# Build folder (where APKs live / Slack downloads land). Auto-detected, same as
# the automation uses; falls back to a local ./apks if detection fails.
try:
    from utils.env_config import detect_apk_folder
    APK_FOLDER = Path(detect_apk_folder())
except Exception:
    APK_FOLDER = REPO_ROOT / "apks"


def _load_test_names():
    """(Re)read the test registry from disk so newly-added tests show up
    WITHOUT a server restart.

    The registry is pure metadata (a list of dicts) with no import side
    effects, so reloading it is safe.  Used at startup, on every page load,
    and by the /tests refresh endpoint (the ⟳ Refresh button)."""
    global _registry_mod
    try:
        if _registry_mod is None:
            import tests.test_registry as _rm
            _registry_mod = _rm
        else:
            importlib.reload(_registry_mod)
        return [t["name"] for t in _registry_mod.TEST_REGISTRY]
    except Exception as e:
        logging.warning(f"[tests] could not load registry: {e}")
        return []


TESTS = _load_test_names()

RUN_TYPES = ["smoke", "regression", "iap", "bat", "complete"]

# Project registry. `runnable` = wired to a real suite on this server. Only
# "Sorry! World" runs today (this repo); the rest are placeholders for the
# multi-project (Tier 2) work — they appear in the dropdown and drive the theme,
# but Run is blocked until their runner is configured. Add more here.
PROJECTS = [
    {"name": "Sorry! World",       "runnable": True},
    {"name": "Backgammon Friends", "runnable": False},
    {"name": "Ludo Star",          "runnable": False},
    {"name": "LS - Clubs",         "runnable": False},
    {"name": "Parchisi Star",      "runnable": False},
]
_RUNNABLE = {p["name"] for p in PROJECTS if p["runnable"]}

templates = Jinja2Templates(directory=str(WEBAPP_DIR / "templates"))

app = FastAPI(title="Automation Runner")
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Single-run state  (one device, one run at a time)
# ─────────────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
STATE = {
    "running": False,
    "run_id": None,
    "label": None,
    "started": None,      # epoch seconds
    "ended": None,
    "returncode": None,
    "log_path": None,
    "proc": None,
    "stopped": False,     # set when the user clicks Stop
    "agent_id": None,     # set when this server-run drives a remote bridge device
}

_SAFE_ID = re.compile(r"^[0-9_]+$")   # run_id is a timestamp → digits + "_" only

# ── Remote agents (other laptops that run jobs on their own USB devices) ──────
# Each agent registers, heartbeats via /agent/poll, and runs run_this.py locally
# on its device, streaming logs back here. Agent runs reuse the same run_<id>.log
# / run_<id>.json files as local runs, so the console + history work uniformly.
_agents_lock = threading.Lock()
AGENTS = {}         # agent_id -> {name, devices, last_seen, status, run_id}
AGENT_JOBS = {}     # agent_id -> [job dict, ...]  (dispatched, not yet claimed)
AGENT_OFFLINE_SEC = 20   # no poll for this long → shown as offline


# ── Run metadata (for history) ───────────────────────────────────────────────
def _meta_path(run_id):
    return RUNS_DIR / f"run_{run_id}.json"


def _write_meta(run_id, **fields):
    """Merge `fields` into the run's metadata file."""
    meta = {}
    p = _meta_path(run_id)
    if p.exists():
        try:
            meta = json.loads(p.read_text())
        except Exception:
            meta = {}
    meta.update(fields)
    try:
        p.write_text(json.dumps(meta))
    except Exception:
        pass


def _infer_type_from_log(logp):
    """Best-effort: read the run type / test name from the start of a log file.
    Used for older runs that have no metadata. Returns a display string or None."""
    try:
        with open(logp, "r", errors="replace") as f:
            head = f.read(8192)
    except Exception:
        return None
    lines = head.splitlines()
    run_type = None
    for line in lines:
        if "Run Type:" in line:
            run_type = line.split("Run Type:", 1)[1].strip()
            break
    if run_type and run_type.upper() != "INDIVIDUAL":
        return run_type.capitalize()                    # e.g. "Complete", "Smoke"
    for line in lines:                                   # individual → test name(s)
        if "Individual mode" in line and "→" in line:
            return line.split("→", 1)[1].strip()
    for line in lines:
        if "Running:" in line:
            return line.split("Running:", 1)[1].strip()
    return run_type.capitalize() if run_type else None


def _list_history(limit):
    """List recent runs, newest first — driven by the .log files so EVERY past
    run shows up. Uses the .json metadata when present, otherwise synthesizes a
    minimal entry (parsing the run type from the log for pre-metadata runs)."""
    metas = []
    for logp in sorted(RUNS_DIR.glob("run_*.log"), reverse=True):   # newest first
        run_id = logp.stem[len("run_"):]
        meta = {}
        jp = logp.with_suffix(".json")
        if jp.exists():
            try:
                meta = json.loads(jp.read_text())
            except Exception:
                meta = {}
        meta.setdefault("run_id", run_id)
        meta.setdefault("status", "unknown")
        if not meta.get("started"):
            try:
                meta["started"] = logp.stat().st_mtime
            except Exception:
                meta["started"] = None
        # `display` = run type or test name (what the dropdown shows). New runs
        # store it; older runs get it parsed from the log.
        if not meta.get("display"):
            meta["display"] = _infer_type_from_log(logp) or f"run {run_id}"
        metas.append(meta)
        if len(metas) >= limit:
            break
    return metas


def _prune(keep=KEEP_RUNS):
    logs = sorted(RUNS_DIR.glob("run_*.log"), reverse=True)
    for old in logs[keep:]:
        for f in (old, old.with_suffix(".json")):
            try:
                f.unlink()
            except Exception:
                pass


# ── Branch / version selection ────────────────────────────────────────────────
# Runs can target any git branch (master = frozen baseline, dev, feature
# branches). The selected branch runs in its OWN git worktree so the webapp's
# working tree (which has the webapp code) is never disturbed — critical since
# older branches like `master` don't even contain webapp/.
BRANCH_RUNS_DIR = Path(REPO_ROOT).parent / ".sorry-branch-runs"


def _git(args, cwd=None):
    return subprocess.run(["git"] + args, cwd=str(cwd or REPO_ROOT),
                          capture_output=True, text=True, timeout=120)


def _current_branch():
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    return r.stdout.strip() or "?"


def _list_branches():
    local = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"]).stdout.split()
    remote = _git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/"]).stdout.split()
    cur = _current_branch()
    ordered = []
    for b in (cur, "master", "dev"):        # surface the important ones first
        if b in local and b not in ordered:
            ordered.append(b)
    for b in local:
        if b not in ordered:
            ordered.append(b)
    return {"all": local, "remote": remote, "current": cur, "ordered": ordered}


def _prepare_worktree(ref):
    """Return the cwd to run from for branch `ref`.

    Empty ref or the current branch → run in place (REPO_ROOT). Any other branch
    → a dedicated worktree checked out to that branch (refreshed to origin's tip
    if it's a pushed branch), with the git-ignored .env copied in. Returns the
    path to run `run_this.py` from.
    """
    info = _list_branches()
    if not ref or ref == info["current"]:
        return str(REPO_ROOT)
    if ref not in info["all"]:
        raise ValueError(f"unknown branch: {ref}")

    safe = ref.replace("/", "__")
    wt = BRANCH_RUNS_DIR / safe
    BRANCH_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _git(["fetch", "--all", "--quiet"])

    if not wt.exists():
        r = _git(["worktree", "add", "--force", str(wt), ref])
        if r.returncode != 0:
            raise RuntimeError(f"worktree add failed: {r.stderr.strip()}")
    else:
        _git(["checkout", "--force", ref], cwd=str(wt))

    if f"origin/{ref}" in info["remote"]:          # get the latest pushed tip
        _git(["reset", "--hard", f"origin/{ref}"], cwd=str(wt))

    env = REPO_ROOT / ".env"                        # git-ignored, but runs need it
    if env.exists():
        try:
            shutil.copy(env, wt / ".env")
        except Exception:
            pass
    return str(wt)


def _adb_devices():
    """Best-effort list of connected devices (nice-to-have status).  Never raises."""
    adb = os.environ.get("SAT_ADB") or shutil.which("adb")
    if not adb:
        return None
    try:
        out = subprocess.run(
            [adb, "devices"], capture_output=True, text=True, timeout=5
        ).stdout
        devices = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if line and "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
    except Exception:
        return None


def _list_builds():
    """APKs in the build folder, newest first: [{name, size_mb, mtime}]."""
    out = []
    try:
        for p in sorted(APK_FOLDER.glob("*.apk"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            st = p.stat()
            out.append({"name": p.name,
                        "size_mb": round(st.st_size / (1024 * 1024), 1),
                        "mtime": int(st.st_mtime)})
    except Exception:
        pass
    return out


def _device_label(adb, serial):
    """Human name for a device serial via adb props; falls back to the serial."""
    def prop(p):
        try:
            return subprocess.run([adb, "-s", serial, "shell", "getprop", p],
                                  capture_output=True, text=True, timeout=6).stdout.strip()
        except Exception:
            return ""
    brand = prop("ro.product.brand") or prop("ro.product.manufacturer")
    model = prop("ro.product.model")
    name = " ".join(x for x in [brand.title() if brand else "", model] if x).strip()
    return name or serial


def _list_devices_named():
    """Connected devices with human names: [{serial, name}]. Never raises."""
    adb = os.environ.get("SAT_ADB") or shutil.which("adb")
    serials = _adb_devices() or []
    if not adb:
        return [{"serial": s, "name": s} for s in serials]
    return [{"serial": s, "name": _device_label(adb, s)} for s in serials]


def _kill_proc_tree(proc):
    """Stop the run and its ENTIRE process group IMMEDIATELY via SIGKILL.

    The run launches in its own session (start_new_session=True), so the whole
    tree (run_this.py + any adb children) shares one process group. SIGKILL
    can't be caught or ignored and needs no grace period, so the run stops at
    once — no waiting.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            proc.kill()
    except Exception:
        pass


def _watch(proc, run_id, log_file):
    """Wait for the run to finish, flip state back to Free, and record the result."""
    rc = proc.wait()
    log_file.flush()
    log_file.close()
    with _lock:
        was_stopped = STATE["stopped"] and STATE["run_id"] == run_id
    status = "stopped" if was_stopped else ("passed" if rc == 0 else "failed")
    _write_meta(run_id, status=status, ended=time.time(), returncode=rc)
    freed_agent = None
    with _lock:
        if STATE["run_id"] == run_id:
            STATE["running"] = False
            STATE["returncode"] = rc
            STATE["ended"] = time.time()
            STATE["proc"] = None
            freed_agent = STATE.get("agent_id")
            STATE["agent_id"] = None
    # If this was a remote-device run, mark that bridge free again.
    if freed_agent:
        with _agents_lock:
            a = AGENTS.get(freed_agent)
            if a:
                a["status"] = "idle"
                a["run_id"] = None


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "projects": PROJECTS,
            "run_types": RUN_TYPES,
            "tests": _load_test_names(),   # fresh each page load — no restart needed
        },
    )


@app.get("/status")
def status():
    with _lock:
        proc = STATE["proc"]
        # Self-heal: if STATE says running but the process is gone or has
        # already exited, reconcile so the UI can never stay stuck on Busy.
        if STATE["running"] and (proc is None or proc.poll() is not None):
            STATE["running"] = False
            STATE["proc"] = None
            if STATE["ended"] is None:
                STATE["ended"] = time.time()
        s = {k: STATE[k] for k in
             ("running", "run_id", "label", "started", "ended", "returncode", "stopped")}
    s["device"] = "Busy" if s["running"] else "Free"
    s["devices_connected"] = _adb_devices()
    s["report_available"] = (REPO_ROOT / "automation_report.html").exists()
    return JSONResponse(s)


@app.get("/history")
def history():
    return JSONResponse({"runs": _list_history(HISTORY_LIMIT)})


@app.get("/branches")
def branches():
    b = _list_branches()
    return JSONResponse({"branches": b["ordered"], "current": b["current"]})


@app.get("/tests")
def tests():
    """Re-read the test registry and return the current test names.  Backs the
    ⟳ Refresh button so newly-added feature tests appear without a server
    restart.  Also refreshes the module-level TESTS cache."""
    global TESTS
    TESTS = _load_test_names()
    return JSONResponse({"tests": TESTS})


@app.get("/log", response_class=PlainTextResponse)
def log(run_id: str = "", offset: int = 0):
    """Return log text from `offset` onward.

    With no run_id → the live/current run's log. With a run_id → that past run's
    log from disk (for history viewing). Efficient tailing via the offset.
    """
    if run_id:
        if not _SAFE_ID.match(run_id):
            return PlainTextResponse("", headers={"X-Offset": "0"})
        path = RUNS_DIR / f"run_{run_id}.log"
    else:
        with _lock:
            path = Path(STATE["log_path"]) if STATE["log_path"] else None

    if not path or not path.exists():
        return PlainTextResponse("", headers={"X-Offset": str(offset)})

    data = path.read_bytes()
    chunk = data[offset:]
    return PlainTextResponse(
        chunk.decode("utf-8", "replace"),
        headers={"X-Offset": str(len(data))},
    )


@app.post("/run")
def run(
    project: str = Form("Sorry! World"),
    mode: str = Form("type"),          # "type" or "test"
    run_type: str = Form("complete"),
    test: str = Form(""),
    slack: str = Form("off"),          # checkbox → "on" when ticked
    report: str = Form("off"),
    screenshots: str = Form("off"),    # capture a screenshot per step
    ref: str = Form(""),               # git branch to run (blank = current)
    agent: str = Form(""),             # bridge id → run the scripts on ITS device
    build: str = Form(""),             # APK filename to install/run (blank = latest)
    device: str = Form(""),            # device serial to run on (local runs)
):
    if project not in _RUNNABLE:
        return JSONResponse(
            {"ok": False,
             "error": f"'{project}' isn't configured to run on this server yet."},
            status_code=400,
        )

    # Remote-device run: the scripts still run HERE on the server, but drive a
    # device plugged into the selected bridge laptop (env injected below).
    remote = None
    if agent:
        with _agents_lock:
            a = AGENTS.get(agent)
            if a is None:
                return JSONResponse({"ok": False, "error": "Unknown device — is the bridge still connected?"}, status_code=404)
            if a.get("status") == "busy":
                return JSONResponse({"ok": False, "error": "That device is busy with a run."}, status_code=409)
            devs = a.get("devices") or []
            remote = {"agent_id": agent, "name": a.get("name", agent), "ip": a.get("ip"),
                      "adb_port": a.get("adb_port") or 5038, "appium_url": a.get("appium_url"),
                      "serial": devs[0] if devs else None}
        if not remote["ip"] or not remote["serial"]:
            return JSONResponse({"ok": False, "error": "Bridge has no device ready (plug in + enable USB debugging)."}, status_code=400)
        if not remote.get("appium_url"):
            return JSONResponse({"ok": False, "error": f"Appium isn't running on {remote['name']} yet — finish the one-command setup on that laptop (it installs + starts Appium), then click Run here again."}, status_code=400)

    with _lock:
        if STATE["running"]:
            return JSONResponse(
                {"ok": False, "error": "Device busy — a run is already in progress."},
                status_code=409,
            )

    # Prepare the selected branch's worktree OUTSIDE the lock (git fetch/checkout
    # can be slow, and we must not block /status polls).
    try:
        run_cwd = _prepare_worktree(ref)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"branch prep failed: {e}"},
                            status_code=400)
    ref_tag = "" if run_cwd == str(REPO_ROOT) else f" @{ref}"

    with _lock:
        if STATE["running"]:
            return JSONResponse(
                {"ok": False, "error": "Device busy — a run is already in progress."},
                status_code=409,
            )

        # Build the exact non-interactive command run_this.py understands.
        cmd = [PYTHON, "-u", "run_this.py"]
        if mode == "test" and test:
            cmd += ["--test", test]
            label = f"{project}: {test}{ref_tag}"
            display = test                       # dropdown shows the test name
        else:
            rt = run_type if run_type in RUN_TYPES else "complete"
            cmd += ["--run-type", rt]
            label = f"{project}: {rt}{ref_tag}"
            display = rt.capitalize()            # dropdown shows the run type
        cmd += ["--slack", "on" if slack == "on" else "off"]
        cmd += ["--report", "on" if report == "on" else "off"]
        cmd += ["--screenshots", "on" if screenshots == "on" else "off"]
        if remote:
            label += f"  →  {remote['name']}"

        run_id = time.strftime("%Y%m%d_%H%M%S")
        log_path = RUNS_DIR / f"run_{run_id}.log"
        log_file = open(log_path, "wb")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"   # stream logs promptly
        if remote:
            # Point adb + Appium at the bridge laptop's device
            # (utils/env_config.apply_remote_adb reads these at run_this import).
            env["SAT_ADB_HOST"] = remote["ip"]
            env["SAT_ADB_PORT"] = str(remote["adb_port"])
            env["SAT_DEVICE_ID"] = remote["serial"]
            if remote["appium_url"]:
                env["SAT_APPIUM_URL"] = remote["appium_url"]

        # Selected build (install/run this exact APK on whatever device is used).
        if build:
            apk = APK_FOLDER / os.path.basename(build)
            if apk.exists():
                env["SAT_APK"] = str(apk)
        # Selected device for a LOCAL run (bridge runs get their device above).
        if device and not remote:
            env["SAT_DEVICE_ID"] = device

        proc = subprocess.Popen(
            cmd,
            cwd=run_cwd,               # the selected branch's worktree (or REPO_ROOT)
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,   # own process group → Stop can kill the tree
        )

        STATE.update(
            running=True, run_id=run_id, label=label, started=time.time(),
            ended=None, returncode=None, log_path=str(log_path), proc=proc,
            stopped=False, agent_id=(remote["agent_id"] if remote else None),
        )
        if remote:
            with _agents_lock:
                ra = AGENTS.get(remote["agent_id"])
                if ra:
                    ra["status"] = "busy"
                    ra["run_id"] = run_id

    _write_meta(run_id, project=project, label=label, display=display,
                started=time.time(), status="running", returncode=None, ended=None)
    _prune()
    threading.Thread(target=_watch, args=(proc, run_id, log_file), daemon=True).start()
    return JSONResponse({"ok": True, "run_id": run_id, "label": label, "cmd": " ".join(cmd)})


@app.post("/stop")
def stop():
    """Stop the active run — SIGKILL the process group if it's alive, and ALWAYS
    clear the running state so the UI unsticks even if the process already
    exited but STATE was left stale."""
    with _lock:
        proc = STATE["proc"]
        was_active = STATE["running"] or proc is not None
        if was_active:
            STATE["stopped"] = True
    if not was_active:
        return JSONResponse({"ok": False, "error": "No run in progress."}, status_code=400)

    # Kill the whole process group if the process is still alive.
    if proc is not None and proc.poll() is None:
        try:
            _kill_proc_tree(proc)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Always flip to Free — even if the process was already gone (stale state).
    freed_agent = None
    with _lock:
        STATE["running"] = False
        STATE["proc"] = None
        if STATE["ended"] is None:
            STATE["ended"] = time.time()
        freed_agent = STATE.get("agent_id")
        STATE["agent_id"] = None
    if freed_agent:
        with _agents_lock:
            a = AGENTS.get(freed_agent)
            if a:
                a["status"] = "idle"
                a["run_id"] = None
    return JSONResponse({"ok": True})


@app.get("/builds")
def builds_list():
    """Available builds (APKs) in the build folder, newest first."""
    return JSONResponse({"builds": _list_builds()})


@app.post("/builds/refresh")
def builds_refresh():
    """Fetch new builds from Slack into the build folder, then return the list.
    Reuses run_this.py --check-builds so the Slack logic stays in one place."""
    ok, err = True, ""
    try:
        r = subprocess.run([PYTHON, "-u", "run_this.py", "--check-builds"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            ok, err = False, (r.stderr or r.stdout or "check failed").strip()[-300:]
    except Exception as e:
        ok, err = False, str(e)
    return JSONResponse({"ok": ok, "error": err, "builds": _list_builds()})


@app.get("/devices")
def devices_list():
    """Connected (server-local) devices with human-readable names."""
    return JSONResponse({"devices": _list_devices_named()})


@app.get("/reports")
def reports_list():
    """Past reports (dynamic-named, non-overwriting), newest first."""
    d = REPO_ROOT / "reports"
    out = []
    if d.exists():
        for p in sorted(d.glob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({"name": p.name, "mtime": int(p.stat().st_mtime)})
    return JSONResponse({"reports": out})


@app.get("/report")
def report(name: str = ""):
    if name:
        # Serve a specific past report by filename (no path traversal).
        safe = os.path.basename(name)
        p = REPO_ROOT / "reports" / safe
        if p.suffix == ".html" and p.exists():
            return FileResponse(str(p), media_type="text/html", filename=safe)
        return PlainTextResponse("Report not found.", status_code=404)
    path = REPO_ROOT / "automation_report.html"
    if not path.exists():
        return PlainTextResponse("No report available yet.", status_code=404)
    return FileResponse(str(path), media_type="text/html", filename="automation_report.html")


@app.get("/screenshots.zip")
def screenshots_zip():
    """Bundle every per-step screenshot embedded in the latest HTML report into a
    zip. Screenshots live inline in the report (as data URIs), so this extracts
    them on demand — no separate on-disk copies to keep in sync."""
    path = REPO_ROOT / "automation_report.html"
    if not path.exists():
        return PlainTextResponse("No report yet — run with the 📸 Screenshots toggle on.",
                                 status_code=404)
    html = path.read_text(encoding="utf-8", errors="ignore")
    shots = re.findall(
        r'<img class="step-shot" data-name="([^"]+)" src="data:image/([^;]+);base64,([^"]+)"',
        html,
    )
    if not shots:
        return PlainTextResponse(
            "The latest report has no screenshots. Re-run with the 📸 Screenshots toggle on.",
            status_code=404,
        )
    buf = io.BytesIO()
    seen = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, ext, b64 in shots:
            ext = "jpg" if ext.lower() in ("jpeg", "jpg") else ext.lower()
            seen[name] = seen.get(name, 0) + 1
            fn = f"{name}.{ext}" if seen[name] == 1 else f"{name}_{seen[name]}.{ext}"
            try:
                z.writestr(fn, base64.b64decode(b64))
            except Exception:
                pass
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="screenshots.zip"'},
    )


@app.get("/bridge.py")
def bridge_script():
    """Serve the self-contained laptop bridge so onboarding is one line:
       curl -s http://<server>:8000/bridge.py -o bridge.py
       SAT_SERVER=http://<server>:8000 python3 bridge.py
    (The bridge only exposes the device + registers — the test scripts stay here.)"""
    p = REPO_ROOT / "bridge.py"
    if not p.exists():
        return PlainTextResponse("bridge.py not found on server", status_code=404)
    return FileResponse(str(p), media_type="text/x-python", filename="bridge.py")


# ── One-command onboarding ─────────────────────────────────────────────────────
# The server hands the laptop a ready-to-run installer with SAT_SERVER already
# filled in (the origin the client used to reach us, so it's reachable back).
# It only sets up the thin device bridge — the test scripts + AltTester license
# stay here and never touch the laptop.
_INSTALL_SH = r'''#!/usr/bin/env bash
# Automation Runner — device bridge installer (macOS / Linux).
set -e
SERVER="__SERVER__"
echo "== Automation Runner — device bridge setup =="
echo "   server: $SERVER"

if ! command -v python3 >/dev/null 2>&1; then
  echo "X  python3 not found. Install Python 3, then re-run this command."
  exit 1
fi

if ! command -v adb >/dev/null 2>&1; then
  echo ".. adb (Android platform-tools) not found."
  if command -v brew >/dev/null 2>&1; then
    echo ".. installing android-platform-tools via Homebrew..."
    brew install android-platform-tools
  else
    echo "X  Install Android platform-tools, then re-run:"
    echo "     macOS:  brew install android-platform-tools"
    echo "     Linux:  sudo apt-get install -y android-tools-adb"
    exit 1
  fi
fi

# Appium — required for OS-level actions + IAP. UiAutomator2 must run next to the
# device, so it lives on THIS laptop. Installed once; skipped if already present.
if ! command -v appium >/dev/null 2>&1; then
  echo ".. appium not found."
  if ! command -v node >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      echo ".. installing Node.js via Homebrew (one-time)..."
      brew install node
    else
      echo "X  Node.js not found. Install it (https://nodejs.org) or Homebrew, then re-run."
      exit 1
    fi
  fi
  echo ".. installing Appium (npm i -g appium) — one-time, ~1-2 min..."
  npm i -g appium
fi
if ! appium driver list --installed 2>/dev/null | grep -q uiautomator2; then
  echo ".. installing Appium uiautomator2 driver (one-time)..."
  appium driver install uiautomator2 || true
fi

BRIDGE="$(mktemp -d)/bridge.py"
echo ".. downloading bridge..."
curl -fsSL "$SERVER/bridge.py" -o "$BRIDGE"
echo "OK starting bridge — leave this window open (Ctrl+C to stop)."
echo "   On the device tap 'Allow USB debugging'. On macOS click 'Allow' if the firewall prompts."
exec env SAT_SERVER="$SERVER" python3 "$BRIDGE"
'''

_INSTALL_PS1 = r'''# Automation Runner - device bridge installer (Windows PowerShell). Best-effort.
$ErrorActionPreference = "Stop"
$Server = "__SERVER__"
Write-Host "== Automation Runner - device bridge setup =="
Write-Host "   server: $Server"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) { Write-Host "X  Python 3 not found - install from python.org, then re-run."; exit 1 }
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
  Write-Host "X  adb not found - install Android platform-tools + add to PATH, then re-run."; exit 1
}
$Bridge = Join-Path $env:TEMP "sat_bridge.py"
Write-Host ".. downloading bridge..."
Invoke-WebRequest "$Server/bridge.py" -OutFile $Bridge -UseBasicParsing
$env:SAT_SERVER = $Server
Write-Host "OK starting bridge - leave this window open (Ctrl+C to stop)."
& $py.Source $Bridge
'''


def _server_base(request: Request) -> str:
    """Origin the client used to reach us — reachable back from that same client."""
    return str(request.base_url).rstrip("/")


@app.get("/install.sh")
def install_sh(request: Request):
    return PlainTextResponse(_INSTALL_SH.replace("__SERVER__", _server_base(request)),
                             media_type="text/x-shellscript")


@app.get("/install.ps1")
def install_ps1(request: Request):
    return PlainTextResponse(_INSTALL_PS1.replace("__SERVER__", _server_base(request)),
                             media_type="text/plain")


@app.get("/runinfo")
def runinfo(run_id: str = ""):
    """Status of any run (local or agent) read from its metadata file. Lets the
    console detect completion of an AGENT run (which isn't in local STATE)."""
    if not run_id or not _SAFE_ID.match(run_id):
        return JSONResponse({"status": "unknown", "running": False})
    p = _meta_path(run_id)
    if not p.exists():
        return JSONResponse({"status": "unknown", "running": False})
    try:
        m = json.loads(p.read_text())
    except Exception:
        m = {}
    st = m.get("status", "unknown")
    return JSONResponse({"status": st, "running": st == "running",
                         "returncode": m.get("returncode"), "label": m.get("label")})


# ─────────────────────────────────────────────────────────────────────────────
# Remote agent control-plane
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/agents")
def agents():
    now = time.time()
    with _agents_lock:
        out = []
        for aid, a in AGENTS.items():
            online = (now - a.get("last_seen", 0)) < AGENT_OFFLINE_SEC
            out.append({
                "agent_id": aid,
                "name": a.get("name", aid),
                "devices": a.get("devices", []),
                "status": (a.get("status", "idle") if online else "offline"),
                "run_id": a.get("run_id"),
                "kind": a.get("kind", "executor"),
                "ip": a.get("ip"),
            })
    return JSONResponse({"agents": out})


@app.post("/agent/register")
async def agent_register(req: Request):
    body = await req.json()
    aid = body.get("agent_id")
    if not aid:
        return JSONResponse({"ok": False, "error": "agent_id required"}, status_code=400)
    with _agents_lock:
        AGENTS[aid] = {
            "name": body.get("name", aid),
            "devices": body.get("devices", []),
            "last_seen": time.time(),
            "status": "idle",     # fresh registration → idle
            "run_id": None,
            # Phase-2 "bridge" agents: the server RUNS the scripts against this
            # laptop's device (rather than the laptop running them). These fields
            # tell the server how to reach the device + Appium.
            "kind": body.get("kind", "executor"),
            "ip": body.get("ip"),
            "adb_port": body.get("adb_port"),
            "appium_url": body.get("appium_url"),
        }
        AGENT_JOBS.setdefault(aid, [])
    logging.info(
        f"🔌 agent registered: {aid} ({body.get('name')}) kind={body.get('kind','executor')} "
        f"ip={body.get('ip')} devices={body.get('devices')}"
    )
    return JSONResponse({"ok": True})


@app.get("/agent/poll")
def agent_poll(agent_id: str):
    """Heartbeat + claim the next queued job (or none)."""
    with _agents_lock:
        a = AGENTS.get(agent_id)
        if a is None:
            return JSONResponse({"job": None, "known": False})
        a["last_seen"] = time.time()
        jobs = AGENT_JOBS.get(agent_id, [])
        job = jobs.pop(0) if jobs else None
        if job:
            a["status"] = "busy"
            a["run_id"] = job["run_id"]
    return JSONResponse({"job": job, "known": True})


@app.post("/agent/log")
async def agent_log(req: Request):
    body = await req.json()
    run_id = body.get("run_id", "")
    text = body.get("text", "")
    aid = body.get("agent_id")
    # Any log post (even an empty heartbeat) keeps the agent marked online.
    if aid:
        with _agents_lock:
            a = AGENTS.get(aid)
            if a is not None:
                a["last_seen"] = time.time()
    if run_id and _SAFE_ID.match(run_id) and text:
        try:
            with open(RUNS_DIR / f"run_{run_id}.log", "a") as f:
                f.write(text)
        except Exception:
            pass
    return JSONResponse({"ok": True})


@app.post("/agent/result")
async def agent_result(req: Request):
    body = await req.json()
    run_id = body.get("run_id", "")
    aid = body.get("agent_id")
    status = body.get("status", "failed")
    rc = body.get("returncode")
    if run_id and _SAFE_ID.match(run_id):
        _write_meta(run_id, status=status, returncode=rc, ended=time.time())
    with _agents_lock:
        a = AGENTS.get(aid)
        if a is not None:
            a["status"] = "idle"
            a["run_id"] = None
    logging.info(f"🏁 agent {aid} finished run {run_id} → {status}")
    return JSONResponse({"ok": True})


@app.post("/dispatch")
def dispatch(
    agent_id: str = Form(...),
    project: str = Form("Sorry! World"),
    mode: str = Form("type"),
    run_type: str = Form("complete"),
    test: str = Form(""),
    slack: str = Form("off"),
    report: str = Form("off"),
):
    """Queue a run for a remote agent to execute on its own device."""
    if project not in _RUNNABLE:
        return JSONResponse(
            {"ok": False, "error": f"'{project}' isn't configured to run yet."},
            status_code=400,
        )
    with _agents_lock:
        a = AGENTS.get(agent_id)
        if a is None:
            return JSONResponse({"ok": False, "error": "unknown agent"}, status_code=404)
        if a.get("status") == "busy":
            return JSONResponse({"ok": False, "error": "agent is busy"}, status_code=409)
        aname = a.get("name", agent_id)

    if mode == "test" and test:
        display = test
        label = f"{aname}: {test}"
    else:
        run_type = run_type if run_type in RUN_TYPES else "complete"
        display = run_type.capitalize()
        label = f"{aname}: {run_type}"
        test = ""

    run_id = time.strftime("%Y%m%d_%H%M%S")
    job = {"run_id": run_id, "mode": mode, "run_type": run_type, "test": test,
           "slack": slack, "report": report, "project": project}

    with _agents_lock:
        AGENT_JOBS.setdefault(agent_id, []).append(job)
        AGENTS[agent_id]["status"] = "busy"
        AGENTS[agent_id]["run_id"] = run_id

    # create the log file + metadata now so the console + history work immediately
    try:
        open(RUNS_DIR / f"run_{run_id}.log", "wb").close()
    except Exception:
        pass
    _write_meta(run_id, project=project, label=label, display=display,
                started=time.time(), status="running", returncode=None, ended=None,
                agent=aname)
    _prune()
    logging.info(f"📤 dispatched run {run_id} → agent {agent_id} ({label})")
    return JSONResponse({"ok": True, "run_id": run_id, "label": label})
