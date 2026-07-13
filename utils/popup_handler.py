import time
import logging
import threading
from alttester import By
import utils.event_tracker as event_tracker

# -----------------------------------------------------------------------
# Thread-local storage for mutable popup state
# Each device worker thread gets its own IGNORED_POPUPS set and its own
# HANDLER_ACTIVE flag so they cannot interfere with each other.
# -----------------------------------------------------------------------
_ph_local = threading.local()


def _get_ignored() -> set:
    if not hasattr(_ph_local, "ignored"):
        _ph_local.ignored = set()
    return _ph_local.ignored


def _is_handler_active() -> bool:
    return getattr(_ph_local, "handler_active", False)


def _set_handler_active(val: bool) -> None:
    _ph_local.handler_active = val

# IMPORTANT: lazy import to avoid circular dependency
def _get_handlers():
    from tests.handlers.handlers_registry import HANDLERS
    return HANDLERS


# -----------------------------------------------------------------------
# INFO-SCREEN CLOSE
# -----------------------------------------------------------------------
# Info screens (Leagues Info, TI Info, BumpToSpin Info, etc.) have multiple
# stacked overlay layers.  Tapping a specific path like /bg or /Darkbg
# lands on the wrong layer — Unity's EventSystem never receives the event
# and the screen stays open.
#
# The fix: find the topmost rendered object at screen centre
# (find_object_at_coordinates returns it ranked by Unity render order),
# then tap that.  This is exactly what a real finger does.
#
# INFO_SCREEN_PATHS lists every path that needs this treatment.
# Add new paths here; no other code needs to change.
# -----------------------------------------------------------------------

# Paths whose modals require topmost-layer coordinate tap to close.
# Populated from INFO_SCREENS in paths.py plus extra entries below.
def _build_info_screen_paths():
    try:
        from utils.paths import INFO_SCREENS
        paths = {path for _, path in INFO_SCREENS}
    except Exception:
        paths = set()
    # Extra info screens present in POPUP_PRIORITY but not in INFO_SCREENS
    paths.add("/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg")
    return paths

INFO_SCREEN_PATHS = _build_info_screen_paths()


def close_info_screen(unity_driver):
    """
    Dismiss any tap-to-close info/overlay screen by tapping the topmost
    rendered layer at screen centre.

    Works universally for all info screens regardless of their internal
    hierarchy — mirrors exactly what a real finger touch does.

    Three attempts in priority order:
      1. find_object_at_coordinates → tap topmost element (EventSystem raycast)
      2. unity_driver.tap(coords)   → raw coordinate input simulation
      3. direct coordinate tap via begin_touch / end_touch (deepest level)
    """
    cx, cy = 540, 1200          # centre of 1080×2400 screen
    coords = {"x": cx, "y": cy}

    # ── Attempt 1: topmost object via EventSystem raycast ─────────────
    try:
        obj = unity_driver.find_object_at_coordinates(coords)
        if obj:
            obj.tap()
            time.sleep(1)
            return True
    except Exception:
        pass

    # ── Attempt 2: raw coordinate tap (AltTester input simulation) ────
    try:
        unity_driver.tap(coords)
        time.sleep(1)
        return True
    except Exception:
        pass

    # ── Attempt 3: begin_touch / end_touch (lower-level touch event) ──
    try:
        touch_id = unity_driver.begin_touch(coords)
        unity_driver.end_touch(touch_id)
        time.sleep(1)
        return True
    except Exception as e:
        logging.warning(f"[close_info_screen] All three tap methods failed: {e}")
        return False


# ---------------------------------------------------
# IGNORE CONTROL
# ---------------------------------------------------

def ignore_popup(path):
    _get_ignored().add(path)
    logging.info(f"[PopupHandler] Ignoring popup → {path}")


def unignore_popup(path):
    ignored = _get_ignored()
    if path in ignored:
        ignored.remove(path)
        logging.info(f"[PopupHandler] Re-enabled popup → {path}")


def clear_ignored_popups():
    _get_ignored().clear()
    logging.info("[PopupHandler] Cleared ignored popup list")


POPUP_PRIORITY = [
    # CRITICAL
    [
        "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/Okay Button/TouchArea",
        "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/rootMain/continueButton/buttonPrimaryCTA_Stroked",
        "/Canvas/ModalLayer/LeaderBoardModal(Clone)/header/SorryButtonType-Misc/touchArea",
        "/Canvas/ModalLayer/EdlpGold02(Clone)/rootMain/content/crossButton/touchArea",
    ],

    # HIGH
    [
        "/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/closeCTA/touchArea",
        "/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea",
        "/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea",
        # Piggy Bank — test_06_piggy_bank ignores this during purchase;
        # auto-closed here on any incidental appearance outside the test.
        "/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/header/Close Button/touchArea",
        "/Canvas/ModalLayer/EdlpGold01(Clone)/rootMain/content/crossButton/touchArea",
        "/Canvas/ModalLayer/WelcomePackModal(Clone)/rootMain/SorryButtonType-Misc/touchArea",
    ],

    # MEDIUM
    [
        "/Canvas/ModalLayer/DuelEventMainModal(Clone)/rootMain/closeCTA/touchArea",
        "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea",
        "/Canvas/ModalLayer/FortuneIslandStartPopup(Clone)/rootMain/crossButton/touchArea",
    ],

    # LOW  (tap-once-to-close info overlays — extensible, add paths here)
    [
        "/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)/rootMain/CrossButton/touchArea",
        "/Canvas/ModalLayer/PuzzleEventStartPopup(Clone)/rootMain/crossButton/touchArea",
        "/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg",
        "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg",
        "/Canvas/ModalLayer/LeaderboardInfoModal(Clone)/container/bg",
        "/Canvas/ModalLayer/fortuneislandinfoModal(Clone)/Darkbg",
        "/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)/root/close/SorryButtonType-close/touchArea",
        "/Canvas/ModalLayer/CoOpEventInfoScreen(Clone)/bg",
    ],
]


# ---------------------------------------------------
# FAST CLEAR
# ---------------------------------------------------

def fast_clear_popups(unity_driver):

    for group in POPUP_PRIORITY[:2]:

        for path in group:

            if path in _get_ignored():
                continue

            try:
                obj = unity_driver.find_object(By.PATH, path)

                if obj:
                    obj.tap()

                    logging.info(
                        f"[FastPopup] Closed → {path}"
                    )

                    return True

            except:
                pass

    return False


# ---------------------------------------------------
# RUN HANDLERS
# ---------------------------------------------------

def run_handlers(unity_driver, driver=None):

    if _is_handler_active():
        return False

    _set_handler_active(True)

    try:

        for handler in _get_handlers():

            try:
                if handler.is_present(unity_driver, driver):

                    logging.info(
                        f"[Handler] {handler.__name__} detected"
                    )

                    handler.handle(unity_driver, driver)

                    return True

            except Exception as e:

                logging.warning(
                    f"[Handler Error] {handler.__name__}: {e}"
                )

    finally:
        _set_handler_active(False)

    return False


# ---------------------------------------------------
# HANDLE ONE POPUP
# ---------------------------------------------------

def handle_one_popup(unity_driver, driver=None):

    # if run_handlers(unity_driver, driver):
    #     return True

    for group in POPUP_PRIORITY:

        for path in group:

            # IMPORTANT
            if path in _get_ignored():
                continue

            try:

                obj = unity_driver.wait_for_object(
                    By.PATH,
                    path,
                    timeout=0.05
                )

                if obj:

                    if path in INFO_SCREEN_PATHS:
                        # Info screens have stacked overlay layers — tap the
                        # topmost rendered element at screen centre instead of
                        # the found path, which may be below the active layer.
                        close_info_screen(unity_driver)
                    else:
                        obj.tap()

                    logging.info(
                        f"[PopupHandler] Closed → {path}"
                    )

                    time.sleep(0.2)

                    # Track surfaced popup (deduped — first occurrence only)
                    try:
                        event_tracker.record_popup(path)
                    except Exception:
                        pass

                    return True

            except:
                pass

    return False


# ---------------------------------------------------
# CLEAR POPUPS
# ---------------------------------------------------

def clear_all_popups(unity_driver, driver=None, timeout=5):

    end = time.time() + timeout

    while time.time() < end:

        if not handle_one_popup(unity_driver, driver):
            return True

        time.sleep(0.1)

    logging.warning(
        "[PopupHandler] Timeout clearing popups"
    )

    return False


# ---------------------------------------------------
# SAFE WAIT
# ---------------------------------------------------

def wait_for_safe(
    unity_driver,
    by,
    value,
    timeout=6,
    driver=None
):

    end = time.time() + timeout

    # Start the clock from now so popup recovery fires 3 s after the first
    # failed find, not immediately on the very first iteration.
    # (last_recovery = 0 caused handle_one_popup to run on the first loop
    # pass for every call, adding seconds of scan time even for short waits.)
    last_recovery = time.time()

    while time.time() < end:

        try:

            obj = unity_driver.find_object(by, value)

            if obj:
                return obj

        except:
            pass

        # popup recovery every 3 sec
        if time.time() - last_recovery > 3.0:

            handle_one_popup(unity_driver, driver)

            last_recovery = time.time()

        else:
            time.sleep(0.05)

    logging.warning(
        f"[wait_for_safe] Not found → {value}"
    )

    return None


# ---------------------------------------------------
# SAFE TAP
# ---------------------------------------------------

def safe_tap(unity_driver, obj, driver=None):

    if not obj:
        raise Exception(
            "❌ Cannot tap → object is None"
        )

    try:

        obj.tap()

        time.sleep(0.1)

    except Exception as e:

        logging.warning(
            f"[safe_tap] Retrying after popup clear: {e}"
        )

        handle_one_popup(unity_driver, driver)

        try:

            obj.tap()

            time.sleep(0.1)

        except Exception as e2:

            logging.error(
                f"[safe_tap] Failed: {e2}"
            )

            raise


# ---------------------------------------------------
# FIND + TAP
# ---------------------------------------------------

def safe_find_and_tap(
    unity_driver,
    by,
    value,
    timeout=6
):

    obj = wait_for_safe(
        unity_driver,
        by,
        value,
        timeout
    )

    if not obj:
        raise Exception(
            f"❌ Element not found: {value}"
        )

    safe_tap(unity_driver, obj)

    return obj


# ---------------------------------------------------
# UI BLOCK CHECK
# ---------------------------------------------------

def is_ui_blocked(unity_driver):

    for group in POPUP_PRIORITY:

        for path in group:

            if path in _get_ignored():
                continue

            try:

                obj = unity_driver.wait_for_object(
                    By.PATH,
                    path,
                    timeout=0.05
                )

                if obj:
                    return True

            except:
                pass

    return False