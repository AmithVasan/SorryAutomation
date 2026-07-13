"""
google_play_helper.py
─────────────────────
Centralised Google Play IAP purchase helpers.

Every script that triggers a Google Play purchase should call these
functions so timeouts, UiAutomator2 crash-recovery, and "safe waiting
after buy tap" behaviour are consistent across the entire suite.

Public API
──────────
    handle_google_play_purchase(driver, timeout=90)
        → (success: bool, driver)

    handle_purchase_failure(unity_driver)
        → "success" | "retry" | "skip"

        Call this AFTER reconnect_alttester() in every IAP test to
        detect and dismiss the in-game Purchase Failed popup.

        Return values
        ─────────────
        "success"  No failure popup found — purchase went through.
        "retry"    Popup found AND Google Play console had opened.
                   Caller should retry the purchase once (re-tap
                   the in-game buy button + handle_google_play_purchase).
        "skip"     Popup found but console never opened — payment
                   service not running.  Caller should skip and
                   continue to the next step.

    close_extra_google_play_popups(driver, timeout=20)
        → (bool, driver)

    reconnect_appium_no_launch(old_driver)
        → driver | None

    reconnect_alttester(unity_driver=None)
        → AltDriver

    UIA2_CRASH_SIGNAL  (str constant)

Adding support for a new item
─────────────────────────────
1. Call handle_google_play_purchase(driver) after tapping the in-game
   buy button.
2. Call reconnect_alttester() once the game is back in the foreground.
3. Call handle_purchase_failure(unity_driver) to detect / dismiss any
   failure popup and decide whether to retry or skip.
"""

import time
import logging
import subprocess

from alttester import AltDriver
from appium import webdriver as appium_webdriver
from appium.options.android import UiAutomator2Options

from utils.state_manager import state
from config import ADB_PATH

# -----------------------------------------------------------------------
# Game constants  (same values used in test_03_shop / test_05_season_pass)
# -----------------------------------------------------------------------
_PACKAGE_NAME  = "com.gameberry.sorry.card.board.game"
_ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"
_ALT_PORT      = 13000
_APP_NAME      = "sorry"

# -----------------------------------------------------------------------
# UiAutomator2 crash detection string
# -----------------------------------------------------------------------
UIA2_CRASH_SIGNAL = "instrumentation process is not running"

# A UiAutomator2 session can die in more ways than an instrumentation crash.
# The most common in this suite is the SERVER killing an idle session after
# newCommandTimeout — which surfaces as "invalid session id" / "session ...
# terminated", NOT the crash signal above.  Treat all of these as "the
# session is dead → reconnect".
_SESSION_DEAD_SIGNALS = (
    UIA2_CRASH_SIGNAL,
    "invalid session id",
    "session is either terminated or not started",
    "a session is either terminated",
    "was terminated due to",
    "delete session",
    "session not created",
)


def _is_session_dead(exc):
    """True if the exception means the Appium/UiAutomator2 session is gone
    and must be reconnected (covers idle-timeout kills, not just crashes)."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _SESSION_DEAD_SIGNALS)


def _appium_alive(driver):
    """Lightweight server round-trip; returns False if the session is dead."""
    if driver is None:
        return False
    try:
        _ = driver.current_package     # cheap call that hits the UIA2 server
        return True
    except Exception:
        return False


def _ensure_appium_session(driver):
    """
    Guarantee a live UiAutomator2 session before the purchase flow starts.

    Long AltTester-only tests (e.g. Happy Flow in the smoke suite) leave the
    Appium session idle for minutes.  Even with a high newCommandTimeout the
    session can still be gone by the time a purchase begins, so we revive it
    here up front.  When the session is already alive (e.g. the individual
    shop run) this is a no-op and the working flow is unchanged.
    """
    if _appium_alive(driver):
        return driver
    logging.warning(
        "⚠️ [GP] Appium session not alive at purchase start — reconnecting..."
    )
    new_d = reconnect_appium_no_launch(driver)
    if new_d and _appium_alive(new_d):
        logging.info("✅ [GP] Appium session revived before purchase")
        return new_d
    logging.error("❌ [GP] Could not revive Appium session before purchase")
    return new_d or driver

# -----------------------------------------------------------------------
# PURCHASE FAILURE POPUP PATHS  (Unity / AltTester side)
# -----------------------------------------------------------------------
_FAIL_SCREEN = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/darkBG"
_FAIL_OKAY   = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/ButtonLayer/Okay Button/TouchArea"
_FAIL_CLOSE  = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/closeButton/touchArea"

# Path registered in popup_handler POPUP_PRIORITY — temporarily ignored
# while handle_purchase_failure inspects the popup itself.
_FAIL_POPUP_HANDLER_PATH = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/Okay Button/TouchArea"


# -----------------------------------------------------------------------
# INTERNAL ALT-TESTER WAIT HELPER
# -----------------------------------------------------------------------
def _wait_alt(unity_driver, path, timeout=5):
    """Short wait_for_object wrapper — returns object or None."""
    try:
        from alttester import By
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


# -----------------------------------------------------------------------
# APPIUM / UiAutomator2 QUERY HELPERS
# (Everything Google-Play related is driven through Appium's UiAutomator2
#  server.  On this game's payment sheet an OS-level `uiautomator dump`
#  returns an EMPTY hierarchy — the sheet is a surface it cannot serialize
#  — yet the UiAutomator2 accessibility API CAN enumerate and click those
#  same nodes.  So Buy detection, popup dismissal and return-to-game are
#  all done via Appium, never ADB UI dumps.)
# -----------------------------------------------------------------------

# UiSelector strings that mean "the GP payment sheet is still on screen".
_GP_SHEET_MARKERS = ["Buy", "1-tap buy", "Purchase", "Subscribe", "Order", "Confirm"]

# Post-purchase popup buttons that are SAFE to tap to close a confirmation /
# upsell dialog.  Deliberately EXCLUDES Cancel / No thanks / Buy / Purchase —
# tapping those could abort an in-flight purchase or trigger a second buy.
_GP_CONFIRM_LABELS = [
    "Got it", "Got It", "GOT IT",
    "Done", "DONE",
    "OK", "Ok", "Okay", "OKAY",
    "Continue", "CONTINUE",
    "Close", "CLOSE",
    "Dismiss", "DISMISS",
    "Great", "Great!",
    "Not now", "Not Now", "NOT NOW",
]

# Case-insensitive words that, when they are the WHOLE button label, mean a
# safe post-purchase dismiss button.  Used as a fallback when the exact-case
# labels above miss (e.g. "Got it!" / " Continue ").  Kept strict — a label
# is only matched if, once trimmed, it EQUALS or STARTS WITH one of these,
# so "Cancel"/"Buy"/"Subscribe" can never match.
_GP_CONFIRM_WORDS = [
    "got it", "done", "okay", "ok", "continue",
    "close", "dismiss", "great", "not now",
]

# Resource-ids for Google Play's positive / continue button on the
# post-purchase confirmation sheet.  Only used once the payment sheet
# content (Buy / ToS) has cleared, so it can't re-trigger a Buy.
_GP_CONFIRM_IDS = [
    "com.android.vending:id/positive_button",
    "com.android.vending:id/continue_button",
    "com.android.vending:id/continue_button_with_details",
]


def _appium_scan_post_buy(driver):
    """
    Appium scan of the screen after Buy has been tapped.

    Queried via XPATH, NOT the `android uiautomator` UiSelector engine.
    On this game's Google Play sheet the UiSelector engine returns nothing
    (it's why Buy itself is only ever tapped via the XPath `//*[@text="Buy"]`
    fallback), whereas XPath attribute queries DO enumerate the sheet's
    nodes.  So every query here — diagnostics, sheet detection and popup
    dismissal — uses XPath to stay consistent with what actually works.

    Returns (dismiss_el, dismiss_label, sheet_present, crashed, clickables)
      dismiss_el    : an element for a SAFE popup-dismiss button, or None.
      dismiss_label : that button's text / resource-id (for logging), or None.
      sheet_present : True if the GP payment sheet CONTENT (Buy button /
                      ToS "By tapping 'Buy'…" text) is still on screen.
      crashed       : True if UiAutomator2 crashed during the scan — the
                      caller should reconnect the Appium session.
      clickables    : list of every clickable element's text / resource-id
                      (diagnostics — reveals unknown popup buttons so they
                      can be added to _GP_CONFIRM_LABELS).
    """
    def _xp(xpath):
        """find_elements → list (never raises NoSuchElement); re-raises
        only on a genuine UiAutomator2 crash so the caller can recover."""
        try:
            return driver.find_elements("xpath", xpath)
        except Exception as exc:
            if _is_session_dead(exc):
                raise
            return []

    def _text_of(el):
        try:
            return (el.text or "").strip()
        except Exception:
            return ""

    try:
        # ── Diagnostics: every clickable element on screen ─────────────
        # Also feeds the case-insensitive fallback matcher below.
        clickables    = []
        clickable_els = _xp('//*[@clickable="true"]')
        for el in clickable_els[:25]:
            label = _text_of(el)
            if not label:
                try:
                    rid = el.get_attribute("resource-id") or ""
                except Exception:
                    rid = ""
                label = rid.split("/")[-1] if rid else ""
            if label:
                clickables.append(label)

        # ── Is the payment sheet still on screen? (content-based) ──────
        sheet_present = False
        for marker in _GP_SHEET_MARKERS:
            if _xp(f'//*[@text="{marker}"]'):
                sheet_present = True
                break
        if not sheet_present and _xp('//*[contains(@text, "By tapping")]'):
            sheet_present = True

        # ── Safe dismiss button? ───────────────────────────────────────
        dismiss_el, dismiss_label = None, None

        # 1. Exact-text match (fastest, most precise).
        for label in _GP_CONFIRM_LABELS:
            els = _xp(f'//*[@text="{label}"]')
            if els:
                dismiss_el, dismiss_label = els[0], label
                break

        # 2. Case-insensitive fallback over the actual clickable buttons —
        #    catches variants like "Got it!" or padded "  Continue ".
        if dismiss_el is None:
            for el in clickable_els[:25]:
                txt = _text_of(el).lower()
                if not txt:
                    continue
                if any(txt == w or txt.startswith(w) for w in _GP_CONFIRM_WORDS):
                    dismiss_el, dismiss_label = el, _text_of(el)
                    break

        # 3. Resource-id match for GP's positive/continue button — ONLY
        #    once the payment sheet content has cleared, so it can't
        #    accidentally re-tap the sheet's own Buy button.
        if dismiss_el is None and not sheet_present:
            for rid in _GP_CONFIRM_IDS:
                els = _xp(f'//*[@resource-id="{rid}"]')
                if els:
                    dismiss_el, dismiss_label = els[0], rid
                    break

        return (dismiss_el, dismiss_label, sheet_present, False, clickables)

    except Exception as exc:
        if _is_session_dead(exc):
            return (None, None, False, True, [])
        logging.debug(f"[GP] post-buy scan error: {exc}")
        return (None, None, False, False, [])


def _wait_purchase_complete(driver, min_settle=8, grace=8, max_window=35):
    """
    Called ONCE the Buy button has been tapped.

        tap Buy  →  let the purchase PROCESS (≥min_settle s)
                 →  close any post-purchase popup (e.g. "Got it")
                 →  return to the game

    All screen inspection is via XPath (see _appium_scan_post_buy) — the
    `android uiautomator` UiSelector engine returns nothing on this game's
    GP sheet, so a popup would be INVISIBLE to it.  Closing the popup is
    what lets the purchase settle cleanly; leaving it open can make Google
    Play cancel the transaction and the game then shows "Purchase Failed".

    Timing model
    ────────────
    • min_settle — always let the purchase process at least this long
      before handing control back, so reconnect_alttester()'s `am start`
      can't interrupt an in-flight transaction.
    • grace — the "Got it" / confirmation popup appears a few seconds
      AFTER the payment-sheet content (Buy / ToS) vanishes.  So once the
      screen goes clear we keep watching for `grace` more seconds; if a
      popup shows up in that window it's closed and the grace timer
      restarts.  Only after the screen stays clear for the full grace
      window do we return.
    • max_window — hard cap on the whole wait.

    The game verifies the ACTUAL purchase via AltTester afterwards, so this
    always returns (True, driver).  driver may be a fresh session if
    UiAutomator2 crashed and was reconnected.
    """
    logging.info("⏳ [GP] Buy tapped — letting the purchase process...")
    state.set("last_gp_console_opened", True)

    start          = time.time()
    dismissed_any  = False
    uia2_restarted = False
    cleared_at     = None    # when the screen last went clear (no sheet/popup)

    while time.time() - start < max_window:
        dismiss_el, dismiss_label, sheet_present, crashed, clickables = (
            _appium_scan_post_buy(driver)
        )

        if clickables:
            logging.info(f"🔍 [GP] Post-buy clickables: {clickables[:20]}")

        # ── UiAutomator2 crashed → restart the session and retry ───────
        if crashed and not uia2_restarted:
            logging.warning(
                "⚠️ [GP] UiAutomator2 crashed during post-buy scan → restarting"
            )
            new_d = reconnect_appium_no_launch(driver)
            if new_d:
                driver         = new_d
                uia2_restarted = True
            time.sleep(2)
            continue

        # ── A post-purchase popup is up → close it ─────────────────────
        if dismiss_el is not None:
            try:
                dismiss_el.click()
                logging.info(f"   🔘 [GP] Post-purchase popup closed → {dismiss_label}")
                dismissed_any = True
            except Exception as exc:
                if _is_session_dead(exc) and not uia2_restarted:
                    new_d = reconnect_appium_no_launch(driver)
                    if new_d:
                        driver         = new_d
                        uia2_restarted = True
                else:
                    logging.debug(f"[GP] popup click failed: {exc}")
            cleared_at = None          # restart the grace watch
            time.sleep(2)              # let it dismiss / a chained popup appear
            continue

        # ── Nothing to close right now — track the "clear" grace window ─
        if sheet_present:
            cleared_at = None          # sheet still processing
        elif cleared_at is None:
            cleared_at = time.time()   # screen just went clear — start grace

        elapsed = time.time() - start
        clear_for = (time.time() - cleared_at) if cleared_at is not None else 0

        # Return only after the minimum settle AND the screen has stayed
        # clear (no sheet, no popup) for the full grace window — giving a
        # late "Got it" popup time to appear and be closed first.
        if elapsed >= min_settle and cleared_at is not None and clear_for >= grace:
            break

        time.sleep(1.5)

    if not dismissed_any:
        logging.info("   ℹ️ [GP] No post-purchase popup to close")

    logging.info("✅ [GP] Purchase processed — returning to game for confirmation")
    return True, driver


# -----------------------------------------------------------------------
# APPIUM SESSION RESTART
# -----------------------------------------------------------------------
def reconnect_appium_no_launch(old_driver):
    """
    Create a fresh UiAutomator2 session without launching any app.

    Google Play's payment sheet can kill UiAutomator2; a new session
    spins up a fresh server that can inspect the current screen without
    disturbing the on-screen Google Play dialog.

    Returns the new driver, or None on failure.
    """
    device_id = state.get("device_id")

    if not device_id:
        logging.warning(
            "⚠️ [GP] device_id not in state — cannot restart UiAutomator2"
        )
        return old_driver

    try:
        old_driver.quit()
    except Exception:
        pass

    try:
        options = UiAutomator2Options()
        options.set_capability("platformName",      "Android")
        options.set_capability("automationName",    "UiAutomator2")
        options.set_capability("deviceName",        device_id)
        options.set_capability("noReset",           True)
        options.set_capability("newCommandTimeout", 3600)
        # No appPackage / appActivity → don't launch anything, just attach

        new_driver = appium_webdriver.Remote(
            "http://127.0.0.1:4723", options=options
        )
        logging.info("✅ [GP] Appium session restarted (no-launch)")
        return new_driver

    except Exception as e:
        logging.error(f"❌ [GP] Appium restart failed: {e}")
        return None


# -----------------------------------------------------------------------
# EXTRA GOOGLE PLAY POPUP CLEANER
# -----------------------------------------------------------------------
def close_extra_google_play_popups(driver, timeout=20):
    """
    Safety-net cleaner for any residual Google Play dialogs after a
    purchase.  Driven entirely through Appium/UiAutomator2 — the GP
    bottom-sheet and its popups are invisible to an OS-level `uiautomator
    dump` but fully reachable through the UiAutomator2 accessibility API.

    IMPORTANT: call this AFTER handle_google_play_purchase returns — never
    during the buy flow.  Only SAFE dismiss labels (_GP_CONFIRM_LABELS)
    are tapped, so an in-flight purchase is never cancelled (no Cancel /
    No thanks).

    Returns (True, driver) once no GP popup / sheet content remains.
    driver may be a fresh session if UiAutomator2 crashed and reconnected.
    """
    logging.info("🧹 [GP] Cleaning extra Google Play popups...")

    end            = time.time() + timeout
    uia2_restarted = False

    while time.time() < end:
        dismiss_el, dismiss_label, sheet_present, crashed, clickables = (
            _appium_scan_post_buy(driver)
        )

        if clickables:
            logging.info(f"🔍 [GP] Cleanup clickables: {clickables[:20]}")

        # ── UiAutomator2 crashed → restart the session and retry ───────
        if crashed and not uia2_restarted:
            logging.warning(
                "⚠️ [GP] UiAutomator2 crashed during cleanup → restarting"
            )
            new_d = reconnect_appium_no_launch(driver)
            if new_d:
                driver         = new_d
                uia2_restarted = True
            time.sleep(1.5)
            continue

        # ── A GP popup is up → close it ────────────────────────────────
        if dismiss_el is not None:
            try:
                dismiss_el.click()
                logging.info(f"   🔘 [GP] Popup closed → {dismiss_label}")
            except Exception as exc:
                if _is_session_dead(exc) and not uia2_restarted:
                    new_d = reconnect_appium_no_launch(driver)
                    if new_d:
                        driver         = new_d
                        uia2_restarted = True
                else:
                    logging.debug(f"[GP] cleanup click failed: {exc}")
            time.sleep(1.5)
            continue

        # No dismiss button + no GP sheet content → we're clear.
        if not sheet_present:
            logging.info("✅ [GP] No residual Google Play popups")
            return True, driver

        time.sleep(1)

    logging.warning("⚠️ [GP] Popup cleanup window elapsed")
    return False, driver


# -----------------------------------------------------------------------
# GOOGLE PLAY PURCHASE HANDLER
# -----------------------------------------------------------------------
def handle_google_play_purchase(driver, timeout=90):
    """
    Tap the Buy button on the Google Play payment sheet and wait for
    the purchase to complete.

    Design notes
    ────────────
    • Once Buy is tapped (`buy_tapped = True`) the function dismisses
      safe post-purchase confirmation screens ("Got it", "Done", "OK",
      etc.) so Google Play returns to the game automatically.
      It never presses Cancel / No thanks / Back mid-flow.
    • A settle wait lets the GP sheet FULLY open before the first Appium
      query — querying a half-open sheet can wedge UiAutomator2 and hang
      the whole flow.
    • UiAutomator2 crash recovery is handled inline via
      reconnect_appium_no_launch (up to 3×) so the returned driver may be
      a new session.
    • Logs every visible clickable element each iteration while Buy is not
      yet found, so an unmatched Buy label is always in the logs.

    Parameters
    ──────────
    driver  : Appium WebDriver
    timeout : seconds to wait (default 90 — IAP subscriptions need time)

    Returns
    ───────
    (success: bool, driver)
      success → True if the game returned to foreground after buy
      driver  → may be a new UiAutomator2 session on crash-recovery
    """
    logging.info("💳 [GP] Handling Google Play purchase...")

    # A preceding AltTester-only test (e.g. Happy Flow) may have left the
    # Appium session idle long enough to be killed.  Revive it BEFORE the
    # settle wait so the first Buy query hits a live session.  No-op when the
    # session is already alive, so the individual shop run is unaffected.
    driver = _ensure_appium_session(driver)

    buy_ids = [
        "com.android.vending:id/buy_button",
        "com.android.vending:id/positive_button",
        "com.android.vending:id/continue_button",
        "com.android.vending:id/submit_button",
        "com.android.vending:id/payment_button",
        "com.android.vending:id/continue_button_with_details",
    ]

    # Exact-match texts (primary — these were working before).
    buy_texts_exact = [
        "Buy", "1-tap buy", "Purchase", "Subscribe",
        "Order", "Confirm", "Place order",
    ]

    # Contains-match keywords (fallback only — used when exact match finds nothing).
    # Kept intentionally narrow to avoid matching non-button labels like
    # "Payment method" (Pay), "Your order" (Order), "Confirmation" (Confirm).
    buy_texts_contains = [
        "Buy", "Pay", "Purchase", "Subscribe",
    ]

    # Post-purchase confirmation buttons are handled inside
    # _wait_purchase_complete via the module-level _GP_CONFIRM_LABELS.

    end            = time.time() + timeout
    buy_tapped     = False
    reconnects     = 0
    MAX_RECONNECTS = 3

    # Unified, ordered list of (locator-strategy, selector) candidates for
    # the Buy button.  Most reliable first: UiAutomator2 text/resource-id,
    # then plain resource-ids, then XPath exact/contains text.
    buy_candidates = (
        [("android uiautomator", s) for s in [
            'new UiSelector().text("Buy").clickable(true)',
            'new UiSelector().text("Buy")',
            'new UiSelector().text("1-tap buy").clickable(true)',
            'new UiSelector().text("1-tap buy")',
            'new UiSelector().resourceId("com.android.vending:id/buy_button")',
            'new UiSelector().resourceId("com.android.vending:id/positive_button")',
            'new UiSelector().textContains("Buy").clickable(true)',
        ]]
        + [("id", bid) for bid in buy_ids]
        + [("xpath", f'//*[@text="{t}"]') for t in buy_texts_exact]
        + [("xpath", f'//*[contains(@text, "{t}")]') for t in buy_texts_contains]
    )

    # ── Phase 1: let the Google Play payment sheet FULLY open ────────────
    # CRITICAL — this wait is load-bearing, NOT padding.  Querying the GP
    # sheet while it is still opening WEDGES the UiAutomator2 server: the
    # very first find call then blocks for the ENTIRE timeout and the
    # purchase fails with ~90 s of total log silence, then "Purchase flow
    # timed out".  This happens with BOTH find_element() and find_elements()
    # — it is the sheet's rendering/animation state that wedges the server,
    # not the query variant.  A 3 s wait was measured to still hang (worst
    # on the slow, high-value ₹9999 sheet); 15 s reliably works.  So we do
    # NOT touch UiAutomator2 until the sheet has had time to fully render.
    logging.info("⏳ [GP] Waiting for Google Play payment sheet to load...")
    settle_deadline = min(end, time.time() + 15)
    while time.time() < settle_deadline:
        time.sleep(1)
    logging.info("🔎 [GP] Sheet should be open — locating Buy button...")

    # ── helper: reconnect UiAutomator2 after a crash ─────────────────────
    def _recover(exc):
        """Return True if the exception meant the session died and we
        recovered from it (covers idle-timeout kills, not just crashes)."""
        nonlocal driver, reconnects
        if _is_session_dead(exc) and reconnects < MAX_RECONNECTS:
            logging.warning("⚠️ [GP] UiAutomator2 crashed → restarting session")
            new_d = reconnect_appium_no_launch(driver)
            if new_d:
                driver      = new_d
                reconnects += 1
                logging.info(f"🔄 [GP] UiAutomator2 restarted ({reconnects}/{MAX_RECONNECTS})")
                time.sleep(3)
            return True
        return False

    while time.time() < end:

        # ── Buy already tapped → close any post-purchase popup + return ─
        # _wait_purchase_complete scans (via Appium) for a Google Play
        # confirmation/upsell popup, closes it, and hands back to the game.
        # The game verifies the ACTUAL purchase via AltTester afterwards.
        if buy_tapped:
            return _wait_purchase_complete(driver)

        # ── Try every Buy-button locator until one clicks ──────────────
        for by, sel in buy_candidates:
            try:
                els = driver.find_elements(by, sel)   # [] instead of raising
                if els:
                    els[0].click()
                    buy_tapped = True
                    logging.info(f"   ✅ [GP] Buy button tapped → {sel}")
                    time.sleep(3)
                    break
            except Exception as exc:
                if _recover(exc):
                    break          # session changed — restart the candidate loop
                logging.debug(f"[GP] buy locator error ({sel}): {exc}")

        if buy_tapped:
            continue

        # ── Diagnostics: what CAN Appium see right now? ────────────────
        # Queried via XPath (the strategy that actually works on this GP
        # sheet).  Logged every iteration so we're never blind again — if
        # Buy isn't found, its actual label / resource-id will be here.
        try:
            els    = driver.find_elements("xpath", '//*[@clickable="true"]')
            labels = []
            for e in els[:25]:
                try:
                    lbl = (e.text or "").strip()
                    if not lbl:
                        rid = e.get_attribute("resource-id") or ""
                        lbl = rid.split("/")[-1] if rid else ""
                except Exception:
                    lbl = ""
                if lbl:
                    labels.append(lbl)
            logging.info(f"🔍 [GP] Buy not found yet — visible: {labels[:20]}")
        except Exception as exc:
            _recover(exc)

        time.sleep(2)

    logging.warning("⚠️ [GP] Purchase flow timed out")
    state.set("last_gp_console_opened", buy_tapped)
    return False, driver


# -----------------------------------------------------------------------
# PURCHASE FAILURE HANDLER
# -----------------------------------------------------------------------
def handle_purchase_failure(unity_driver):
    """
    Check for the in-game Purchase Failed popup after returning from
    Google Play.  Call this once after reconnect_alttester() in every
    IAP test — it is a no-op when the purchase succeeded.

    Logic
    ─────
    1. Temporarily suppress popup_handler's auto-dismiss for this modal
       so we can inspect it ourselves.
    2. Check for the failure screen (darkBG) with a 5 s window.
    3. If found:
         a. Tap Okay button; fall back to Close button if Okay not found.
         b. If Google Play console DID open  → "retry"
            (purchase processing error — caller should retry once)
         c. If Google Play console DID NOT open → "skip"
            (payment service down / console never launched)
    4. If not found → "success"

    Returns
    ───────
    "success" | "retry" | "skip"
    """
    import utils.popup_handler as _ph

    # Suppress popup_handler's auto-dismiss while we inspect the popup
    _ph.ignore_popup(_FAIL_POPUP_HANDLER_PATH)

    try:
        screen = _wait_alt(unity_driver, _FAIL_SCREEN, timeout=5)

        if not screen:
            return "success"

        logging.warning("💳 [GP] Purchase Failed popup detected")

        # ── Dismiss: Okay first, Close as fallback ─────────────────────
        dismissed = False

        okay = _wait_alt(unity_driver, _FAIL_OKAY, timeout=3)
        if okay:
            try:
                okay.tap()
                dismissed = True
                logging.info("   🔘 [GP] Tapped Okay on Purchase Failed popup")
            except Exception:
                pass

        if not dismissed:
            close = _wait_alt(unity_driver, _FAIL_CLOSE, timeout=3)
            if close:
                try:
                    close.tap()
                    dismissed = True
                    logging.info("   🔘 [GP] Tapped Close on Purchase Failed popup (Okay not found)")
                except Exception:
                    pass

        if not dismissed:
            logging.warning("   ⚠️ [GP] Could not dismiss Purchase Failed popup — neither Okay nor Close found")

        time.sleep(1)

        # ── Decide outcome based on whether console ever opened ────────
        console_opened = state.get("last_gp_console_opened", False)

        if console_opened:
            logging.warning(
                "💳 [GP] Purchase failed — Google Play console opened but "
                "purchase did not complete. Caller should retry once."
            )
            return "retry"
        else:
            logging.warning(
                "💳 [GP] Purchase failed — payment service not running or "
                "Google Play console did not open. Skipping."
            )
            return "skip"

    finally:
        # Always re-enable popup_handler's auto-dismiss
        _ph.unignore_popup(_FAIL_POPUP_HANDLER_PATH)


# -----------------------------------------------------------------------
# ALTTESTER RECONNECT
# -----------------------------------------------------------------------
def reconnect_alttester(unity_driver=None):
    """
    Close the existing AltDriver (if any), bring the game back to the
    foreground (Google Play may have pushed it behind), then reconnect
    to AltTester Desktop.

    Returns the new AltDriver.  Raises RuntimeError if all attempts fail.
    """
    if unity_driver:
        try:
            unity_driver.stop()
            time.sleep(0.5)
        except Exception:
            pass

    # Bring game back to foreground via ADB
    device_id = state.get("device_id")
    if device_id:
        try:
            subprocess.run(
                [ADB_PATH, "-s", device_id, "shell", "am", "start",
                 "-n", f"{_PACKAGE_NAME}/{_ACTIVITY_NAME}"],
                check=False, timeout=10
            )
            logging.info("📲 [GP] Game brought to foreground")
            time.sleep(5)
        except Exception as e:
            logging.warning(
                f"⚠️ [GP] Could not bring game to foreground: {e}"
            )
    else:
        logging.warning(
            "⚠️ [GP] device_id not in state — skipping foreground restore"
        )
        time.sleep(5)

    for attempt in range(10):
        try:
            driver = AltDriver(
                host="127.0.0.1", port=_ALT_PORT, app_name=_APP_NAME
            )
            logging.info(f"✅ [GP] AltTester reconnected (attempt {attempt + 1})")
            return driver
        except Exception as e:
            logging.warning(
                f"⚠️ [GP] Reconnect attempt {attempt + 1} failed: {e}"
            )
            time.sleep(2)

    raise RuntimeError("❌ [GP] AltTester reconnect failed after all attempts")
