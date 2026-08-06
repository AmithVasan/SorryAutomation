"""
utils/screenshots.py — per-step screenshot capture for the HTML report.

Screenshots are captured via the Appium driver (full device screen, so they
work for Unity game screens AND OS-level surfaces like Google Play / permission
dialogs) and embedded into the report as small JPEG thumbnails, so the report
stays a single portable file. Capturing is gated by SAT_SCREENSHOTS=1 (the
webapp "Screenshots" toggle / `--screenshots on`) because it slows a run.

This module never raises — a screenshot failure must never fail a test.
"""
import io
import os
import base64
import logging

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


def capture(driver, width: int = 480, quality: int = 60):
    """Return a thumbnail data URI of the current screen, or None. Never raises."""
    if driver is None:
        return None
    try:
        png = driver.get_screenshot_as_png()
    except Exception as e:
        logging.debug(f"[screenshot] capture failed: {e}")
        return None
    if not png:
        return None
    try:
        return _thumb_data_uri(png, width, quality)
    except Exception as e:
        logging.debug(f"[screenshot] encode failed: {e}")
        return None
