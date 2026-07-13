"""
event_tracker.py
────────────────
Lightweight, zero-dependency tracker for anything that happens during a
test run (handlers fired, packs purchased, popups surfaced, etc.).

Usage
-----
    from utils.event_tracker import record, record_popup, get_all, reset

    # Record a handled event
    record("FTUE",  "Album FTUE",       "PASS")
    record("Shop",  "'4,000' Gold Pack", "FAIL")
    record("Popups","Daily Login",       "PASS")

    # Record a surfaced popup (derives name from Unity path, deduped)
    record_popup("/Canvas/ModalLayer/LeagueModal(Clone)/...")

    # At start of each run
    reset()

    # In the report generator
    all_events = get_all()   # OrderedDict  {section → [{"name","status","detail"}]}

Thread safety
─────────────
Each thread keeps its own isolated sections dict (threading.local).
In parallel mode call merge_into(shared_dict, lock) before the thread
exits to fold its events into the combined report.
"""

import re
import threading
from collections import OrderedDict

# -----------------------------------------------------------------------
# Thread-local store
# -----------------------------------------------------------------------
_local = threading.local()


def _sections() -> OrderedDict:
    """Return this thread's event-sections dict, creating it on first access."""
    if not hasattr(_local, "sections"):
        _local.sections = OrderedDict()
    return _local.sections


# -----------------------------------------------------------------------
# Friendly names for POPUP_PRIORITY paths
# Add / update as needed — unknown paths are auto-derived from class name
# -----------------------------------------------------------------------
POPUP_NAME_OVERRIDES: dict = {
    "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/rootMain/continueButton/buttonPrimaryCTA_Stroked":
        "League Reward",
    "/Canvas/ModalLayer/LeaderBoardModal(Clone)/header/SorryButtonType-Misc/touchArea":
        "Leaderboard",
    "/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/closeCTA/touchArea":
        "Season Pass Purchase",
    "/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea":
        "Connect to Facebook",
    "/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea":
        "Endless Sale",
    "/Canvas/ModalLayer/DuelEventMainModal(Clone)/rootMain/closeCTA/touchArea":
        "Duel Event",
    "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea":
        "League",
    "/Canvas/ModalLayer/FortuneIslandStartPopup(Clone)/rootMain/crossButton/touchArea":
        "Fortune Island",
    "/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)/rootMain/CrossButton/touchArea":
        "LiveOps Race",
    "/Canvas/ModalLayer/PuzzleEventStartPopup(Clone)/rootMain/crossButton/touchArea":
        "Puzzle Event",
    "/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg":
        "Duel Event Info",
    "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg":
        "League Info",
    "/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/header/Close Button/touchArea":
        "Piggy Bank",
    "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/Okay Button/TouchArea":
        "Season Pass Purchase Confirmed",
    "/Canvas/ModalLayer/LeaderboardInfoModal(Clone)/container/bg":
        "Leaderboard Info",
    "/Canvas/ModalLayer/fortuneislandinfoModal(Clone)/Darkbg":
        "Treasure Island Info",
    "/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)/root/close/SorryButtonType-close/touchArea":
        "BumpToSpin Info",
    "/Canvas/ModalLayer/CoOpEventInfoScreen(Clone)/bg":
        "Beach Buddies Info",
}


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------
def _path_to_name(path: str) -> str:
    """
    Derive a human-readable modal name from a Unity hierarchy path.
    Checks POPUP_NAME_OVERRIDES first; falls back to CamelCase parsing.
    """
    if path in POPUP_NAME_OVERRIDES:
        return POPUP_NAME_OVERRIDES[path]

    parts = path.strip("/").split("/")
    for i, part in enumerate(parts):
        if part == "ModalLayer" and i + 1 < len(parts):
            name = parts[i + 1].replace("(Clone)", "").strip()
            # Strip common suffix words so we get "League" not "LeagueModal"
            for suffix in ("StartPopup", "InfoModal", "MainModal",
                           "Modal", "Screen", "Popup"):
                if name.endswith(suffix) and len(name) > len(suffix):
                    name = name[: -len(suffix)].strip()
                    break
            # CamelCase → space-separated words
            name = re.sub(r"([A-Z])", r" \1", name).strip()
            return name

    return path   # last-resort: return raw path


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------
def record(
    section: str,
    name: str,
    status: str = "PASS",
    detail: str = "",
    dedup: bool = False,
) -> None:
    """
    Record one handled event.

    Parameters
    ----------
    section : str
        Category label shown as the card header in the report
        (e.g. "FTUE", "Shop", "Popups", "Popups Surfaced").
    name : str
        Human-readable item name (e.g. "Album FTUE", "'4,000' Gold Pack").
    status : str
        "PASS" (✅) | "FAIL" (❌) | "SKIP" (➖)
    detail : str
        Optional extra info shown in smaller text next to the name.
    dedup : bool
        If True the entry is silently ignored when the same name already
        exists in this section (useful for Popups Surfaced).
    """
    s = _sections()
    if section not in s:
        s[section] = []

    if dedup:
        for ev in s[section]:
            if ev["name"] == name:
                return

    s[section].append({
        "name":   name,
        "status": status,
        "detail": detail,
    })


def record_popup(path: str, status: str = "PASS") -> None:
    """
    Convenience wrapper for POPUP_PRIORITY closures.
    Derives a friendly name from the Unity path and deduplicates.
    """
    record("Popups Surfaced", _path_to_name(path), status=status, dedup=True)


def get_all() -> dict:
    """Return a plain dict copy of all recorded sections → events."""
    return dict(_sections())


def reset() -> None:
    """Clear all events for this thread — call once at the start of each run."""
    _sections().clear()


def merge_into(target: dict, lock: threading.Lock = None) -> None:
    """
    Merge this thread's events into `target` (a shared dict).

    Used in parallel mode: each device worker calls this before exiting
    so all per-device events are folded into a single combined report.

    Parameters
    ----------
    target : dict   {section → [event, ...]}  shared across threads
    lock   : threading.Lock  held during the merge to prevent races
    """
    _lock = lock if lock is not None else threading.Lock()
    with _lock:
        for section, events in _sections().items():
            if section not in target:
                target[section] = []
            target[section].extend(events)
