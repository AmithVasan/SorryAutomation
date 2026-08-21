"""
utils/screenshots.py — per-step screenshot capture for the HTML report.

Screenshots are captured via the Appium driver (full device screen, so they
work for Unity game screens AND OS-level surfaces like Google Play / permission
dialogs) and embedded into the report as small JPEG thumbnails, so the report
stays a single portable file. Capturing is gated by SAT_SCREENSHOTS=1 (the
webapp "Screenshots" toggle / `--screenshots on`) because it slows a run.

This module never raises — a screenshot failure must never fail a test — and,
just as important, never *hangs* one: a capture is run under a hard timeout and,
after repeated timeouts (e.g. a slow/flaky remote or bridge Appium whose HTTP
client has no read timeout), capture disables itself for the rest of the run so a
report-only feature can't stall the whole suite.
"""
import io
import os
import base64
import logging
import threading

try:
    from PIL import Image
    _PIL_OK = True
    try:
        _RESAMPLE = Image.Resampling.LANCZOS
    except AttributeError:          # Pillow < 9.1
        _RESAMPLE = Image.LANCZOS
except Exception:                   # Pillow absent → fall back to raw PNG
    _PIL_OK = False


def screenshots_enabled() -> bool:
    return os.environ.get("SAT_SCREENSHOTS", "0") == "1"


def _thumb_data_uri(png_bytes: bytes, width: int, quality: int) -> str:
    """Downscale PNG bytes → small JPEG data URI. Falls back to the raw PNG."""
    if _PIL_OK:
        try:
            im = Image.open(io.BytesIO(png_bytes))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if im.width > width:
                h = max(1, int(im.height * width / im.width))
                im = im.resize((width, h), _RESAMPLE)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
        except Exception as e:
            logging.debug(f"[screenshot] thumbnail failed, embedding raw PNG: {e}")
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


# --- hang protection ---------------------------------------------------------
# The Appium client has no read timeout, so a single get_screenshot_as_png() can
# block for minutes over a slow/remote (bridge) connection. Because capture() is
# called from inside the logging handler on every step, one hung call freezes the
# whole run. We therefore run each capture in a worker thread with a hard timeout,
# and trip a circuit breaker after a few timeouts so we stop trying.
_CAPTURE_TIMEOUT = float(os.environ.get("SAT_SCREENSHOT_TIMEOUT", "8"))
_MAX_TIMEOUTS = int(os.environ.get("SAT_SCREENSHOT_MAX_TIMEOUTS", "2"))
_timeouts = 0
_disabled = False


def _grab_png(driver, box):
    try:
        box["png"] = driver.get_screenshot_as_png()
    except Exception as e:                       # pragma: no cover - infra
        box["err"] = e


def capture(driver, width: int = 480, quality: int = 60):
    """Return a thumbnail data URI of the current screen, or None.

    Never raises and never blocks longer than `_CAPTURE_TIMEOUT` seconds. After
    `_MAX_TIMEOUTS` timeouts it disables itself for the rest of the process."""
    global _timeouts, _disabled
    if driver is None or _disabled:
        return None

    box: dict = {}
    worker = threading.Thread(target=_grab_png, args=(driver, box), daemon=True)
    worker.start()
    worker.join(_CAPTURE_TIMEOUT)

    if worker.is_alive():
        # The screenshot call is stuck (no read timeout on the Appium client).
        # Abandon it (the daemon thread dies with the process) and count it.
        _timeouts += 1
        logging.debug(f"[screenshot] capture timed out after {_CAPTURE_TIMEOUT}s")
        if _timeouts >= _MAX_TIMEOUTS and not _disabled:
            _disabled = True
            logging.warning(
                "⚠️ [screenshot] disabling per-step screenshots for this run — "
                "repeated capture timeouts (slow/remote Appium). The run continues "
                "normally; only report screenshots are skipped."
            )
        return None

    if box.get("err") is not None:
        logging.debug(f"[screenshot] capture failed: {box['err']}")
        return None
    png = box.get("png")
    if not png:
        return None
    try:
        return _thumb_data_uri(png, width, quality)
    except Exception as e:
        logging.debug(f"[screenshot] encode failed: {e}")
        return None
