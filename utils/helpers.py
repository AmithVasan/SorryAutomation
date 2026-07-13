import time
import logging
from alttester import By

from utils.popup_handler import wait_for_safe
from utils.state_manager import state
from utils.paths import (
    PROFILE_BUTTON, PROFILE_CLOSE, PROFILE_NAME, PROFILE_COUNTRY,
    PROFILE_ID, PROFILE_LEVEL, PROFILE_XP, PROFILE_PAWN,
    HOME_GOLD_TEXT, HOME_GEMS_TEXT, HOME_HAMMER_TEXT,
)


def safe_text(obj):
    if not obj:
        return None
    try:
        txt = obj.get_component_property(
            "TMPro.TextMeshProUGUI",
            "text",
            "Unity.TextMeshPro"
        )
        return txt if txt not in (None, "", "N/A") else None
    except Exception:
        return None


def fast_text(unity_driver, path, timeout=2):
    try:
        obj = unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
        return safe_text(obj)
    except Exception:
        return None


def parse_amount(text):
    if not text:
        return 0
    try:
        text = text.strip().upper().replace(",", "").replace(" ", "")
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        for suffix, mult in multipliers.items():
            if text.endswith(suffix):
                return int(float(text[:-1]) * mult)
        return int(float(text))
    except Exception:
        return 0


def get_wallet_from_data(unity_driver):
    """
    Fetch gold, gems, and pips directly from the Unity UserManager class
    via AltTester method calls (in-memory Data source).

    Tries call_static_method first (works when UserManager exposes true
    static helpers).  Falls back to find_object + call_component_method
    in case the Unity methods are instance-level on the MonoBehaviour.

    Returns a dict: {"gold": int|None, "gems": int|None, "pips": int|None}
    """
    def _call(method_name):
        # Attempt 1 — static method (fastest path)
        try:
            result = unity_driver.call_static_method(
                "UserManager", method_name, "Assembly-CSharp", [], []
            )
            return int(result)
        except Exception:
            pass
        # Attempt 2 — instance method on MonoBehaviour component
        try:
            obj = unity_driver.find_object(By.COMPONENT, "UserManager")
            result = obj.call_component_method(
                "UserManager", method_name, "Assembly-CSharp", [], []
            )
            return int(result)
        except Exception:
            return None

    gold = _call("GetGold")
    gems = _call("GetGems")
    pips = _call("GetPips")

    logging.info(
        f"💾 Wallet (Data) → "
        f"Gold: {gold}  Gems: {gems}  Pips: {pips}"
    )
    return {"gold": gold, "gems": gems, "pips": pips}


def get_user_snapshot(unity_driver):
    logging.info("📸 Capturing user snapshot...")

    profile = wait_for_safe(unity_driver, By.PATH, PROFILE_BUTTON, 5)
    if not profile:
        raise Exception("❌ Profile button not found")

    profile.tap()
    time.sleep(1)

    player_name   = fast_text(unity_driver, PROFILE_NAME)
    country       = fast_text(unity_driver, PROFILE_COUNTRY)
    player_id     = fast_text(unity_driver, PROFILE_ID)

    if player_id:
        player_id = player_id.replace("PLAYER ID:", "").strip()

    level         = fast_text(unity_driver, PROFILE_LEVEL)
    xp            = fast_text(unity_driver, PROFILE_XP)
    equipped_pawn = fast_text(unity_driver, PROFILE_PAWN)

    close = wait_for_safe(unity_driver, By.PATH, PROFILE_CLOSE, 3)
    if close:
        close.tap()

    time.sleep(0.5)

    gold   = parse_amount(fast_text(unity_driver, HOME_GOLD_TEXT))
    gems   = parse_amount(fast_text(unity_driver, HOME_GEMS_TEXT))
    hammer = parse_amount(fast_text(unity_driver, HOME_HAMMER_TEXT))

    state.set_user_info("player_name", player_name)
    state.set_user_info("country", country)
    state.set_user_info("player_id", player_id)
    state.set_user_info("level", int(level) if level and level.isdigit() else level)
    state.set_user_info("xp", xp)
    state.set_user_info("gold", gold)
    state.set_user_info("gems", gems)
    state.set_user_info("hammer", hammer)
    state.set_user_info("equipped_pawn", equipped_pawn)

    # Data source (UserManager in-memory values)
    wallet_data = get_wallet_from_data(unity_driver)

    logging.info("📊 User Snapshot:")
    logging.info(f"   👤 Name    : {player_name}")
    logging.info(f"   🌍 Country : {country}")
    logging.info(f"   🆔 ID      : {player_id}")
    logging.info(f"   ⭐ Level   : {level}")
    logging.info(f"   📈 XP      : {xp}")
    logging.info(f"   🪙 Gold    : {gold:<12} (Data: {wallet_data.get('gold')})")
    logging.info(f"   💎 Gems    : {gems:<12} (Data: {wallet_data.get('gems')})")
    logging.info(f"   🔨 Hammer  : {hammer}")
    logging.info(f"   🎭 Pawn    : {equipped_pawn}")
