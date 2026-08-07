"""
utils/alttester_appname.py — set an app's AltTester app-name at RUNTIME.

Parallel runs share ONE AltTester Desktop, so each concurrent game must register
under a distinct app-name (the license covers 2 concurrent). Builds all default
to "sorry"; this renames a running app to a unique name via AltTester's own
in-app dialog, so no per-build change is needed:

    connect as "sorry"  →  tap the AltTester Icon (reveals the hidden dialog)
    →  set AppNameInputField  →  tap RestartButton (app re-registers)
    →  reconnect the driver under the new name

Validated on-device (Samsung Galaxy S23 FE, Android 16): sorry → sorry2, with the
game staying on its current scene (Restart re-does only the AltTester connection).

To avoid two runs colliding on the default "sorry" during setup, callers must
serialize the launch→rename window (see the cross-process lock in run_this).
"""
import time
import logging

from alttester import AltDriver, By

_ICON    = "/AltTesterPrefab/AltDialog/Icon"
_FIELD   = "/AltTesterPrefab/AltDialog/Dialog/InfoArea/AppNameInputField"
_RESTART = "/AltTesterPrefab/AltDialog/Dialog/RestartButton"


def rename_alttester_app(current_driver, target_name,
                         host="127.0.0.1", port=13000,
                         settle=15, attempts=6):
    """Rename the connected app's AltTester app-name to `target_name` and return a
    fresh AltDriver connected under it. `current_driver` (connected under the old
    name) is stopped. Raises RuntimeError if the reconnect never succeeds."""
    logging.info(f"🔤 Renaming AltTester app-name → '{target_name}'…")
    try:
        current_driver.find_object(By.PATH, _ICON).tap()      # reveal the dialog
        time.sleep(1.2)
        current_driver.find_object(By.PATH, _FIELD).set_text(target_name)
        time.sleep(0.5)
        try:
            current_driver.find_object(By.PATH, _RESTART).tap()   # re-register
        except Exception:
            pass   # the tap tears down this very connection — expected
    finally:
        try:
            current_driver.stop()
        except Exception:
            pass

    time.sleep(settle)   # let the app reconnect to the Desktop under the new name

    last = None
    for i in range(attempts):
        try:
            d = AltDriver(host=host, port=port, app_name=target_name)
            d.get_current_scene()   # probe: real command, not just a socket
            logging.info(f"✅ AltTester app-name is now '{target_name}'")
            return d
        except Exception as e:
            last = e
            time.sleep(3)
    raise RuntimeError(f"AltTester rename to '{target_name}' failed after "
                       f"{attempts} attempts: {last}")
