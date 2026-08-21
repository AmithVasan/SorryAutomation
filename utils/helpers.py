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


# -----------------------------------------------------------------------
# REWARDS FROM DATA
# Reads the rewards a screen is showing straight from the game's reward
# components (BaseRewardItem.GetRewardAmount() / GetRewardTypeId()) via
# AltTester — instead of scraping the UI amount text (which is formatted
# like "1.2K" and depends on element paths). Same technique as
# get_wallet_from_data(). Never raises — returns [] on any failure.
# -----------------------------------------------------------------------

# Game RewardType enum → readable name (from BaseRewardItem's RewardType).
REWARD_TYPES = {
    0: "None", 1: "Gold", 2: "Pip", 3: "Gem", 4: "Shield", 5: "Attack",
    6: "SeasonBonusPass", 7: "SeasonPoints", 8: "PipnSlidePoints",
    9: "PipPursuitPoints", 10: "XP", 11: "FeatureUnlock", 12: "Trophy",
    13: "LeaguePoints", 15: "CosmeticPawn", 16: "CardPack",
    17: "BumpToSpinRoyalPass", 18: "BumpToSpinAmmo", 19: "EOCPointsReward",
    20: "Frame", 21: "Steal", 22: "PuzzleEventAmmo", 23: "DuelPoints",
    24: "GeneralPawn", 25: "CosmeticLootbox", 26: "FortuneIslandAmmo",
    27: "CoOpEventAmmo", 28: "PiggyBank",
}


_reward_diag_logged = False   # one-shot diagnostic guard (per process)


def _reward_call(obj, method, assembly, comp_name):
    """Call one BaseRewardItem getter on a reward-item object. Returns int or None."""
    try:
        return int(obj.call_component_method(comp_name, method, assembly, [], []))
    except Exception:
        return None


def _reward_component_pairs(item, component, assembly):
    """Candidate (component, assembly) pairs to call the getter with — discovered
    from the tile's own components first (so a differently-named or differently-
    housed reward class still works), then the sensible defaults."""
    pairs = []
    try:
        for c in (item.get_all_components() or []):
            cn = c.get("componentName") if isinstance(c, dict) else getattr(c, "componentName", None)
            an = c.get("assemblyName") if isinstance(c, dict) else getattr(c, "assemblyName", None)
            if cn and "Reward" in cn.split(".")[-1]:
                asm = an or assembly
                for nm in (cn, cn.split(".")[-1]):   # full (namespaced) first, then short
                    if (nm, asm) not in pairs:
                        pairs.append((nm, asm))
    except Exception:
        pass
    for p in [(component, assembly), ("BaseRewardItem", assembly)]:
        if p not in pairs:
            pairs.append(p)
    return pairs


def get_rewards_from_data(unity_driver, component="SpriteRewardItem",
                          assembly="Assembly-CSharp", name_hint="RewardItem",
                          container=None):
    """Return the rewards currently shown, read from the game's data layer:

        [{"type": "Gold", "type_id": 1, "amount": 1000}, ...]

    When `container` (a screen's root path) is given, the search is SCOPED to
    reward tiles under it, so tiles on background/other panels aren't picked up.
    Otherwise it searches globally (by component, else by GameObject name
    containing `name_hint`). The tile component is namespaced (e.g.
    `Scripts.SpriteRewardItem`), so both the namespaced and short names are
    tried for the find and the getter call. Reads via
    BaseRewardItem.GetRewardAmount()/GetRewardTypeId(). Never raises → [].
    """
    global _reward_diag_logged

    items = []
    if container:
        # Scoped to this screen only. `@component` needs the name AltTester sees;
        # try the namespaced form (Scripts.*) and the short form.
        for comp in ("Scripts." + component, component):
            try:
                items = unity_driver.find_objects(
                    By.PATH, f"{container}//*[@component={comp}]") or []
            except Exception:
                items = []
            if items:
                break
    else:
        try:
            items = unity_driver.find_objects(By.COMPONENT, component) or []
        except Exception:
            items = []
        if not items:                               # component name may differ from GameObject name
            try:
                items = unity_driver.find_objects_which_contain(By.NAME, name_hint) or []
            except Exception:
                items = []
    if not items:
        logging.info("🎁 Rewards (Data): — (no reward tiles found)")
        return []

    pairs = _reward_component_pairs(items[0], component, assembly)

    def _read(obj, method):
        for cn, an in pairs:
            v = _reward_call(obj, method, an, cn)
            if v is not None:
                return v
        return None

    out = []
    for it in items:
        amount = _read(it, "GetRewardAmount")
        type_id = _read(it, "GetRewardTypeId")
        if amount is None and type_id is None:
            continue
        out.append({
            "type": REWARD_TYPES.get(type_id, str(type_id)),
            "type_id": type_id,
            "amount": amount,
        })

    # One-shot diagnostic: tiles found but nothing read → capture the actual error
    # from the getter call. A 'MethodNotFoundException' here means the build with
    # GetRewardAmount/GetRewardTypeId isn't on the device yet.
    if not out and not _reward_diag_logged:
        _reward_diag_logged = True
        try:
            comps = [(c.get("componentName") if isinstance(c, dict) else str(c))
                     for c in (items[0].get_all_components() or [])]
        except Exception:
            comps = ["<get_all_components failed>"]
        err = "?"
        try:
            items[0].call_component_method(pairs[0][0], "GetRewardAmount",
                                           pairs[0][1], [], [])
            err = "(call succeeded but value unreadable)"
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:300]}"
        logging.warning(
            f"⚠️ [rewards] found {len(items)} tile(s) but couldn't read amount/type. "
            f"Components: {comps}. Tried {pairs}. GetRewardAmount() → {err}"
        )

    logging.info(
        "🎁 Rewards (Data): "
        + (", ".join(f"{r['type']}={r['amount']}" for r in out) if out else "—")
    )
    return out


def get_device_id(unity_driver):
    """Read the game's device id via DeviceManager.GetDeviceId() (Unity) — the
    stable 1:1 id used to key accounts (sorry_accounts.accounts.deviceID). Tries
    a static call first, then an instance method on a DeviceManager component,
    across the likely class-name / assembly variants. Returns the id or None."""
    classes = ("DeviceManager", "Scripts.DeviceManager")
    assemblies = ("Assembly-CSharp", "Scripts")

    def _ok(v):
        return v is not None and str(v).strip() not in ("", "0", "null", "None")

    # static
    for cls in classes:
        for asm in assemblies:
            try:
                r = unity_driver.call_static_method(cls, "GetDeviceId", asm, [], [])
                if _ok(r):
                    return str(r).strip()
            except Exception:
                pass
    # instance (component / singleton)
    for cls in classes:
        try:
            obj = unity_driver.find_object(By.COMPONENT, cls)
        except Exception:
            obj = None
        if not obj:
            continue
        for asm in assemblies:
            try:
                r = obj.call_component_method(cls, "GetDeviceId", asm, [], [])
                if _ok(r):
                    return str(r).strip()
            except Exception:
                pass
    return None


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
