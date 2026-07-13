import time
import logging
from alttester import By

from utils.state_manager import state
from utils.mongo_helper import get_user_from_db
import utils.event_tracker as event_tracker



# -------------------------------
# HOME HUD PATHS
# -------------------------------
HOME_GOLD = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text"
HOME_GEMS = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text"


# -------------------------------
# DAILY REWARD TABLE (Day 1-7)
# -------------------------------
DAILY_REWARDS = {
    1: {"gold": 500,  "gems": 0,  "cosmetic": None},
    2: {"gold": 700,  "gems": 0,  "cosmetic": None},
    3: {"gold": 400,  "gems": 0,  "cosmetic": None},
    4: {"gold": 600,  "gems": 0,  "cosmetic": None},
    5: {"gold": 900,  "gems": 0,  "cosmetic": None},
    6: {"gold": 1000, "gems": 0,  "cosmetic": None},
    7: {"gold": 2000, "gems": 10, "cosmetic": "Cowboy Pawn"},
}

# GiftBox rewards by index (0-based from claimableloginstreakrewards array)
GIFTBOX_REWARDS = {
    0: {"gold": 3000,  "gems": 0,  "cosmetic": None},
    1: {"gold": 6000,  "gems": 0,  "cosmetic": None},
    2: {"gold": 8000,  "gems": 20, "cosmetic": None},
    3: {"gold": 12000, "gems": 10, "cosmetic": "Astronaut Pawn"},
}


# -------------------------------
# SAFE WAIT
# -------------------------------
def wait_for_safe(unity_driver, path, timeout=2):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except Exception:
        return None


# -------------------------------
# FAST TEXT
# -------------------------------
def fast_text(unity_driver, path, timeout=2):
    try:
        obj = unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
        if not obj:
            return None
        txt = obj.get_component_property(
            "TMPro.TextMeshProUGUI", "text", "Unity.TextMeshPro"
        )
        return txt if txt not in (None, "", "N/A") else None
    except Exception:
        return None


# -------------------------------
# PARSE AMOUNT
# -------------------------------
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


# -------------------------------
# DB FETCH
# -------------------------------
def get_daily_info_from_db(player_id):
    """
    Returns:
      - login_streak (int) → which day reward (1-7)
      - giftbox_claimable (list) → claimable streak rewards
      - gold_db (int)
      - gems_db (int)
    """
    try:
        user = get_user_from_db(player_id)
        if not user:
            return None, [], 0, 0

        daily = user.get("dlyLgn", {})
        login_streak = daily.get("lgnStrk", 0)
        giftbox_claimable = (
            daily
            .get("lgnRcData", {})
            .get("claimableloginstreakrewards", [])
        ) or []

        wallet = user.get("wallet", {})
        gold_db = wallet.get("gold", 0)
        gems_db = wallet.get("gems", 0)

        return login_streak, giftbox_claimable, gold_db, gems_db

    except Exception as e:
        logging.warning(f"⚠️ Could not fetch daily info from DB: {e}")
        return None, [], 0, 0


def get_wallet_from_db_after(player_id):
    """Fetch wallet after claiming — for post-claim comparison."""
    try:
        user = get_user_from_db(player_id)
        if not user:
            return 0, 0
        wallet = user.get("wallet", {})
        return wallet.get("gold", 0), wallet.get("gems", 0)
    except Exception as e:
        logging.warning(f"⚠️ Could not fetch wallet from DB: {e}")
        return 0, 0


# -------------------------------
# DETECTION
# -------------------------------
def is_present(unity_driver, driver=None):
    return wait_for_safe(
        unity_driver,
        "/Canvas/ModalLayer/DailyLoginModal(Clone)/rootMain/claimButton",
        8
    )


# -------------------------------
# HANDLER
# -------------------------------
def handle(unity_driver, driver=None):
    logging.info("🎁 Daily Login detected → Handling flow")

    player_id = state.user_info.get("player_id")
    if not player_id:
        logging.warning("⚠️ player_id missing → skipping DB validation")
        player_id = None

    # ─── PRE-CLAIM DB SNAPSHOT ───────────────────────────────
    if player_id:
        login_streak, giftbox_claimable, gold_db_before, gems_db_before = \
            get_daily_info_from_db(player_id)
    else:
        login_streak = 1
        giftbox_claimable = []
        gold_db_before = 0
        gems_db_before = 0

    # Determine active day (streak cycles 1-7)
    active_day = ((login_streak or 1) % 7) or 7
    daily_expected = DAILY_REWARDS.get(active_day, {})

    # Determine which giftbox is claimable (if any)
    giftbox_count = len(giftbox_claimable)
    giftbox_expected = GIFTBOX_REWARDS.get(giftbox_count - 1) if giftbox_count > 0 else None

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"   📅 Login Streak  : {login_streak} → Day {active_day}")
    logging.info(f"   🎁 Expected Daily: +{daily_expected.get('gold', 0)} gold | +{daily_expected.get('gems', 0)} gems" +
                 (f" | {daily_expected.get('cosmetic')}" if daily_expected.get('cosmetic') else ""))
    if giftbox_expected:
        logging.info(f"   📦 GiftBox Due   : +{giftbox_expected.get('gold', 0)} gold | +{giftbox_expected.get('gems', 0)} gems" +
                     (f" | {giftbox_expected.get('cosmetic')}" if giftbox_expected.get('cosmetic') else ""))
    else:
        logging.info(f"   📦 GiftBox Due   : None")

    # Total expected
    total_expected_gold = daily_expected.get("gold", 0) + (giftbox_expected.get("gold", 0) if giftbox_expected else 0)
    total_expected_gems = daily_expected.get("gems", 0) + (giftbox_expected.get("gems", 0) if giftbox_expected else 0)
    total_expected_cosmetic = daily_expected.get("cosmetic") or (giftbox_expected.get("cosmetic") if giftbox_expected else None)

    logging.info(f"   ✅ Total Expected : +{total_expected_gold} gold | +{total_expected_gems} gems" +
                 (f" | {total_expected_cosmetic}" if total_expected_cosmetic else ""))
    logging.info(f"   💰 DB Before     : 🪙 {gold_db_before} | 💎 {gems_db_before}")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Pre-claim — use fresh DB values after restart/boost
    gold_before_int = gold_db_before or 0
    gems_before_int = gems_db_before or 0
    
    gold_before_raw = str(gold_before_int)
    gems_before_raw = str(gems_before_int)

    # -------------------------------
    # STEP 1: CLAIM DAILY
    # -------------------------------
    claim_btn = wait_for_safe(
        unity_driver,
        "/Canvas/ModalLayer/DailyLoginModal(Clone)/rootMain/claimButton",
        5
    )

    if claim_btn:
        claim_btn.tap()
        logging.info("✅ Daily reward claimed")
        time.sleep(2)
    else:
        logging.warning("⚠️ Claim button not found — skipping daily handler")
        return False

    # -------------------------------
    # STEP 2: GIFT BOX (STREAK)
    # -------------------------------
    gift_btn = wait_for_safe(
        unity_driver,
        "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/collectCTA/TouchArea",
        5
    )

    if gift_btn:
        gift_btn.tap()
        logging.info("🎁 GiftBox reward collected")
        time.sleep(2)
    else:
        logging.info("ℹ️ No GiftBox reward today")

    # -------------------------------
    # STEP 3: COSMETIC REWARD
    # -------------------------------
    cosmetic_screen = wait_for_safe(
        unity_driver,
        "/Canvas/ModalLayer/PawnRewardsModal(Clone)/darkBG",
        5
    )

    if cosmetic_screen:
        logging.info("🎨 Cosmetic reward detected")

        equip_btn = wait_for_safe(
            unity_driver,
            "/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/rewardsSection/rewardContainer/PawnRewardCard(Clone)/root/Equip Button/TouchArea",
            3
        )

        if equip_btn:
            equip_btn.tap()
            logging.info(f"✅ Cosmetic equipped → {total_expected_cosmetic or 'Unknown'}")
            time.sleep(2)
        else:
            later_btn = wait_for_safe(
                unity_driver,
                "/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/continueButton/Later_Button/TouchArea",
                3
            )
            if later_btn:
                later_btn.tap()
                logging.info(f"⏭️ Cosmetic skipped (Later) → {total_expected_cosmetic or 'Unknown'}")
                time.sleep(2)
    else:
        logging.info("ℹ️ No Cosmetic reward today")

    # -------------------------------
    # STEP 4: POST-CLAIM UI SNAPSHOT
    # -------------------------------
    time.sleep(2)

    gold_after_raw = fast_text(unity_driver, HOME_GOLD, timeout=3) or "0"
    gems_after_raw = fast_text(unity_driver, HOME_GEMS, timeout=3) or "0"
    gold_after_int = parse_amount(gold_after_raw)
    gems_after_int = parse_amount(gems_after_raw)

    ui_gold_diff = gold_after_int - gold_before_int
    ui_gems_diff = gems_after_int - gems_before_int

    # Update state
    state.set_user_info("gold", gold_after_int)
    state.set_user_info("gems", gems_after_int)

    # Track in rewards
    if total_expected_gold > 0:
        state.add_reward(source="Daily Login", reward_type="Gold", amount=total_expected_gold)
    if total_expected_gems > 0:
        state.add_reward(source="Daily Login", reward_type="Gems", amount=total_expected_gems)
    if total_expected_cosmetic:
        state.add_reward(source="Daily Login", reward_type="Cosmetic", amount=total_expected_cosmetic)



    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info("🎁 Daily Login Summary")
    logging.info(f"   📅 Day       : {active_day}")
    logging.info(f"   🟡 Gold     : +{total_expected_gold}")
    logging.info(f"   💎 Gems     : +{total_expected_gems}")

    if total_expected_cosmetic:
        logging.info(f"   🎨 Cosmetic : {total_expected_cosmetic}")
    
    logging.info(f"   🪙 Current Gold : {gold_after_int}")
    logging.info(f"   💎 Current Gems : {gems_after_int}")
    
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    event_tracker.record("Popups", "Daily Login", "PASS")
    logging.info("✅ Daily Login flow completed")

    return True