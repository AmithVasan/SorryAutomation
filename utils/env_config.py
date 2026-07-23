"""
utils/env_config.py — auto-detect toolchain paths so the suite runs on ANY
laptop with ZERO manual configuration.

Resolution order for each tool (first hit wins):
  1. Explicit env var (e.g. SAT_ADB / ADB_PATH) — lets anyone override.
  2. Auto-detect: PATH, then ANDROID_HOME / ANDROID_SDK_ROOT, then the standard
     Android SDK install location for the current OS (macOS / Linux / Windows).
  3. Legacy fallback — the original hard-coded path — so the machine this was
     first built on keeps working exactly as before, even if detection finds
     nothing.

Everything here is additive. On the original Mac, step 2 or 3 resolves to the
same paths as before, so nothing changes. To REVERT completely: delete this
file and restore the hard-coded constants in config.py / run_this.py /
tests/test_09_classicmode.py / tests/test_10_fire&icemode.py.
"""

import os
import shutil
from pathlib import Path

HOME = Path.home()

# ── Legacy fallbacks (original Mac values) — last resort only ───────────────
_LEGACY_ADB        = "/Users/amithvasan/Library/Android/sdk/platform-tools/adb"
_LEGACY_APPIUM     = "/usr/local/bin/appium"
_LEGACY_EMULATOR   = "/Users/amithvasan/Library/Android/sdk/emulator/emulator"
_LEGACY_APK_FOLDER = "/Users/amithvasan/Downloads/Testing Build"


def _sdk_roots():
    """Candidate Android SDK root dirs that actually exist, most-specific first."""
    roots = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v))
    roots += [
        HOME / "Library" / "Android" / "sdk",          # macOS
        HOME / "Android" / "Sdk",                       # Linux
        HOME / "AppData" / "Local" / "Android" / "Sdk", # Windows
    ]
    return [r for r in roots if r.exists()]


def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None


def _env(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def detect_adb():
    # SDK location is preferred over PATH so a machine with both an SDK adb and
    # a separate PATH adb (e.g. Homebrew) keeps using its SDK adb — avoids an
    # adb-server version mismatch with tools that use the SDK copy.
    return (
        _env("SAT_ADB", "ADB_PATH")
        or _first_existing([r / "platform-tools" / "adb" for r in _sdk_roots()])
        or shutil.which("adb")
        or _LEGACY_ADB
    )


def detect_appium():
    return (
        _env("SAT_APPIUM", "APPIUM_PATH")
        or shutil.which("appium")
        or _first_existing([
            Path("/usr/local/bin/appium"),      # macOS (Intel) / npm global
            Path("/opt/homebrew/bin/appium"),   # macOS (Apple silicon)
            Path("/usr/bin/appium"),            # Linux
        ])
        or _LEGACY_APPIUM
    )


def detect_emulator():
    return (
        _env("SAT_EMULATOR", "EMULATOR_PATH")
        or _first_existing([r / "emulator" / "emulator" for r in _sdk_roots()])
        or _LEGACY_EMULATOR
    )


def detect_apk_folder():
    """Where builds are downloaded / picked from.

    Order: explicit env → the original Mac folder if it exists (keeps the first
    machine unchanged) → a repo-relative ``builds/`` dir (auto-created) so every
    other laptop gets a working folder with zero input.
    """
    env = _env("SAT_APK_FOLDER", "APK_FOLDER")
    if env:
        Path(env).mkdir(parents=True, exist_ok=True)
        return env

    if Path(_LEGACY_APK_FOLDER).exists():
        return _LEGACY_APK_FOLDER

    repo_root = Path(__file__).resolve().parent.parent
    builds = repo_root / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    return str(builds)
