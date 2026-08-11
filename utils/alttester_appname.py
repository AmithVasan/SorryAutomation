"""
utils/alttester_appname.py — set an app's AltTester app-name at RUNTIME.

Parallel runs share ONE AltTester Desktop, so each concurrent game must register
under a distinct app-name (the license covers 2 concurrent). Builds all default
to "sorry"; this renames a running app to a unique name via AltTester's own
in-app dialog, so no per-build change is needed:

    connect as "sorry"  →  tap the AltTester Icon (reveals the hidden dialog)
    →  set AppNameInputField  →  read the Restart button's screen position
    →  DISCONNECT the driver  →  adb-tap Restart  →  reconnect under the new name

Why disconnect + adb-tap (not just tap Restart via the driver): if an AltDriver
client is still connected when Restart fires, its session breaks mid-command and
the AltTester server holds the stale registration for ~70s, so the app doesn't
become drivable again for ~70s. With NO client connected (tap Restart via raw
adb coordinates instead), the app re-registers in ~0.5s — matching what you see
doing it by hand in the AltTester Desktop. Measured on-device: ~73s → ~0.4s.
"""
import time
import logging
import subprocess

from alttester import AltDriver, By

_ICON    = "/AltTesterPrefab/AltDialog/Icon"
_FIELD   = "/AltTesterPrefab/AltDialog/Dialog/InfoArea/AppNameInputField"
_RESTART = "/AltTesterPrefab/AltDialog/Dialog/RestartButton"


def _screen_height(adb_path, device_id):
    """Device screen height in px (for the Unity→adb y-flip). None if unknown."""
    try:
        out = subprocess.run([adb_path, "-s", device_id, "shell", "wm", "size"],
                             capture_output=True, text=True, timeout=15).stdout
        # "Physical size: 1080x2340"
        return int(out.strip().split(":")[-1].strip().split("x")[1])
    except Exception:
        return None


def rename_alttester_app(current_driver, target_name, device_id=None, adb_path=None,
                         host="127.0.0.1", port=13000, settle=1.5, attempts=10):
    """Rename the connected app's AltTester app-name to `target_name` and return a
    fresh AltDriver connected under it. `current_driver` (connected under the old
    name) is stopped. Raises RuntimeError if the reconnect never succeeds.

    When device_id + adb_path are given, the Restart is tapped via adb with the
    driver disconnected (fast ~1s reconnect). Without them it falls back to the
    driver-tap path (correct, but ~70s to reconnect)."""
    logging.info(f"🔤 Renaming AltTester app-name → '{target_name}'…")

    # Reveal the dialog + set the new name.
    current_driver.find_object(By.PATH, _ICON).tap()
    time.sleep(1.0)
    current_driver.find_object(By.PATH, _FIELD).set_text(target_name)
    time.sleep(0.4)

    use_adb = bool(device_id and adb_path)
    btn_xy = None
    if use_adb:
        try:
            btn = current_driver.find_object(By.PATH, _RESTART)
            H = _screen_height(adb_path, device_id)
            # AltTester screen coords are Unity (bottom-left origin); adb input tap
            # is top-left, so flip y when we know the screen height.
            btn_xy = (int(btn.x), (H - int(btn.y)) if H else int(btn.y))
        except Exception as e:
            logging.warning(f"couldn't read Restart button coords ({e}); using driver-tap fallback")
            use_adb = False

    if use_adb:
        # Disconnect FIRST so no client is attached when Restart fires, then tap
        # Restart with raw adb → the app re-registers in ~1s instead of ~70s.
        try:
            current_driver.stop()
        except Exception:
            pass
        try:
            subprocess.run([adb_path, "-s", device_id, "shell", "input", "tap",
                            str(btn_xy[0]), str(btn_xy[1])], capture_output=True, timeout=15)
        except Exception as e:
            logging.warning(f"adb Restart tap failed: {e}")
    else:
        # Fallback: tap Restart via the driver (breaks this connection → slow reconnect).
        try:
            current_driver.find_object(By.PATH, _RESTART).tap()
        except Exception:
            pass
        try:
            current_driver.stop()
        except Exception:
            pass

    time.sleep(settle)   # app reconnects to the Desktop under the new name

    last = None
    for i in range(attempts):
        try:
            d = AltDriver(host=host, port=port, app_name=target_name)
            d.get_current_scene()   # probe: real command, not just a socket
            logging.info(f"✅ AltTester app-name is now '{target_name}'")
            return d
        except Exception as e:
            last = e
            time.sleep(1)
    raise RuntimeError(f"AltTester rename to '{target_name}' failed after "
                       f"{attempts} attempts: {last}")
