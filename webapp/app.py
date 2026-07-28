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
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
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
    with _lock:
        if STATE["run_id"] == run_id:
            STATE["running"] = False
            STATE["returncode"] = rc
            STATE["ended"] = time.time()
            STATE["proc"] = None


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
    ref: str = Form(""),               # git branch to run (blank = current)
):
    if project not in _RUNNABLE:
        return JSONResponse(
            {"ok": False,
             "error": f"'{project}' isn't configured to run on this server yet."},
            status_code=400,
        )

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

        run_id = time.strftime("%Y%m%d_%H%M%S")
        log_path = RUNS_DIR / f"run_{run_id}.log"
        log_file = open(log_path, "wb")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"   # stream logs promptly

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
            stopped=False,
        )

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
    with _lock:
        STATE["running"] = False
        STATE["proc"] = None
        if STATE["ended"] is None:
            STATE["ended"] = time.time()
    return JSONResponse({"ok": True})


@app.get("/report")
def report():
    path = REPO_ROOT / "automation_report.html"
    if not path.exists():
        return PlainTextResponse("No report available yet.", status_code=404)
    return FileResponse(str(path), media_type="text/html", filename="automation_report.html")


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
        }
        AGENT_JOBS.setdefault(aid, [])
    logging.info(f"🔌 agent registered: {aid} ({body.get('name')}) devices={body.get('devices')}")
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
