"""
utils/device_names.py — human-friendly device names for the GUI & reports.

Turns an adb serial into a recognizable marketing name (e.g. "Samsung Galaxy
S23 FE", "Nothing Phone (1)") instead of a serial (RZCXA1RQ30B) or a model code
(SM-S711B), which users can't map to their own phone.

Priority (never raises; falls back gracefully):
  1. an OEM marketing-name property, if the device sets one
  2. model → marketing-name lookup from Google's public device list
     (bundled as device_models.json) — exact, then a same-brand prefix match so
     regional model variants (SM-S711B vs SM-S711U) still resolve
  3. brand + model
  4. the raw serial
"""
import os
import json
import subprocess

_MAP = None
_MAP_PATH = os.path.join(os.path.dirname(__file__), "device_models.json")

_MARKETNAME_PROPS = (
    "ro.product.marketname",
    "ro.vendor.product.marketname",
    "ro.product.vendor.marketname",
    "ro.product.odm.marketname",
    "ro.config.marketing_name",
)


def _load_map():
    global _MAP
    if _MAP is None:
        try:
            with open(_MAP_PATH) as f:
                _MAP = json.load(f)
        except Exception:
            _MAP = {}
    return _MAP


def _brandize(brand, name):
    brand = (brand or "").strip()
    name = (name or "").strip()
    if not name:
        return ""
    if brand and not name.lower().startswith(brand.lower()):
        return f"{brand.title()} {name}"
    return name


def _lookup_model(model):
    """Exact model match, else the marketing name of the longest same-prefix
    model (>= 6 shared chars) so regional variants resolve. None if no match."""
    if not model:
        return None
    mp = _load_map()
    key = model.upper()
    if key in mp:
        return mp[key]
    best, best_len = None, 5
    for k, v in mp.items():
        n = 0
        for a, b in zip(key, k):
            if a == b:
                n += 1
            else:
                break
        if n > best_len:
            best_len, best = n, v
    return best


def _all_props(serial, adb_path):
    """All getprop values in one adb call: {key: value}. Empty on failure."""
    try:
        out = subprocess.run([adb_path, "-s", serial, "shell", "getprop"],
                             capture_output=True, text=True, timeout=8).stdout
        d = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("[") and "]: [" in line:
                k, v = line[1:].split("]: [", 1)
                d[k] = v.rstrip("]")
        return d
    except Exception:
        return {}


def pretty_name(serial, adb_path):
    """Human-readable marketing name for a device serial. Never raises."""
    if not adb_path:
        return serial
    props = _all_props(serial, adb_path)
    if not props:
        return serial
    brand = props.get("ro.product.brand") or props.get("ro.product.manufacturer") or ""
    for p in _MARKETNAME_PROPS:
        v = (props.get(p) or "").strip()
        if v and v.lower() != "unknown":
            return _brandize(brand, v)
    model = props.get("ro.product.model", "")
    mk = _lookup_model(model)
    if mk:
        return mk
    return _brandize(brand, model) or serial
