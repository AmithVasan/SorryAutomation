import time
import logging
from alttester import By, AltDriver

from utils.state_manager import state
from utils.mongo_helper import get_user_wallet
from utils.popup_handler import wait_for_safe, safe_tap, clear_all_popups


# -------------------------------
# GUARD
# -------------------------------
def check_preconditions():
    if not state.user_info.get("player_id"):
        raise Exception("❌ player_id missing — did test_01 run successfully?")


# -------------------------------
# PATHS
# -------------------------------
SHOP_BUTTON = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Shop/ShopIcon"
HOME_BUTTON = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon"

# Shop HUD wallet paths
GOLD_TEXT = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/coinBar/text"
GEMS_TEXT = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/gemBar/text"

# Home HUD wallet paths
HOME_GOLD_TEXT = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text"
HOME_GEMS_TEXT = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text"

# Purchase popup paths
PURCHASE_POPUP = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/darkBG"
PURCHASE_FAIL  = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/mask/failed/icon"
PURCHASE_OK    = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/Okay Button/TouchArea"


# -------------------------------
# GOLD PACKS
# -------------------------------
GOLD_PACKS = [
    ("Gold 4000",  "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)/baseContent/popular/mask/glow_1"),
    ("Gold 12.5K", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)[1]/baseContent/popular/mask/glow_1"),
    ("Gold 42K",   "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)[2]/baseContent/popular/mask/glow_1"),
    ("Gold 90K",   "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)[3]/baseContent/popular/mask/glow_1"),
    ("Gold 250K",  "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)[4]/baseContent/popular/mask/glow_1"),
    ("Gold 500K",  "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/bg/cardContent/ShopCard(Clone)[5]/baseContent/popular/mask/glow_1"),
]


# -------------------------------
# GEM PACKS
# -------------------------------
GEM_PACKS = [
    ("50 Gems",   "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)/baseContent/popular/mask/glow_1"),
    ("155 Gems",  "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)[1]/baseContent/popular/mask/glow_1"),
    ("540 Gems",  "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)[2]/baseContent/popular/mask/glow_1"),
    ("1100 Gems", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)[3]/baseContent/popular/mask/glow_1"),
    ("3000 Gems", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)[4]/baseContent/popular/mask/glow_1"),
    ("6000 Gems", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/bg/cardContent/ShopCard(Clone)[5]/baseContent/popular/mask/glow_1"),
]


# -------------------------------
# HELPERS
# -------------------------------
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


def fast_text(unity, path, timeout=1):
    try:
        obj = unity.wait_for_object(By.PATH, path, timeout=timeout)
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


def get_wallet_snapshot(unity, gold_path, gems_path):
    gold = parse_amount(fast_text(unity, gold_path))
    gems = parse_amount(fast_text(unity, gems_path))
    return gold, gems


# -------------------------------
# 🔥 NEW: GOOGLE PLAY POPUP CLEANER
# -------------------------------
def close_extra_google_play_popups(driver, timeout=15):
    logging.info("🧹 Checking for extra Google Play popups...")

    end = time.time() + timeout

    while time.time() < end:
        handled = False

        texts = ["OK", "Ok", "Continue", "Yes", "Got it", "Cancel", "No thanks"]

        for text in texts:
            try:
                btn = driver.find_element("xpath", f'//*[@text="{text}"]')
                if btn:
                    btn.click()
                    logging.info(f"✅ Auto-handled popup → {text}")
                    handled = True
                    time.sleep(1)
                    break
            except Exception:
                continue

        if handled:
            continue

        try:
            driver.back()
            logging.info("↩️ Pressed back to close popup")
            time.sleep(1)
        except Exception:
            pass

        try:
            driver.find_element("xpath", '//*[@text="Buy"]')
        except Exception:
            logging.info("✅ Back in game — popup cleared")
            return True

    logging.warning("⚠️ Could not fully clear Google Play popups")
    return False


# -------------------------------
# GOOGLE PLAY PURCHASE
# -------------------------------
def handle_google_play_purchase(driver):
    logging.info("🛒 Waiting for Google Play Buy button...")

    buy_ids = [
        "com.android.vending:id/buy_button",
        "com.android.vending:id/positive_button",
        "com.android.vending:id/continue_button",
    ]

    end = time.time() + 15
    buy_tapped = False

    while time.time() < end:
        for btn_id in buy_ids:
            try:
                btn = driver.find_element("id", btn_id)
                if btn:
                    btn.click()
                    logging.info(f"✅ Buy tapped → {btn_id}")
                    buy_tapped = True
                    break
            except Exception:
                continue

        if buy_tapped:
            break

        try:
            btn = driver.find_element("xpath", '//*[@text="Buy"]')
            if btn:
                btn.click()
                logging.info("✅ Buy tapped → xpath text=Buy")
                buy_tapped = True
                break
        except Exception:
            pass

        time.sleep(0.5)

    if not buy_tapped:
        logging.warning("⚠️ Buy button not found")
        return False

    # 🔥 NEW: HANDLE EXTRA POPUPS IMMEDIATELY
    close_extra_google_play_popups(driver)

    logging.info("⏳ Waiting for payment to process...")

    end = time.time() + 20
    while time.time() < end:
        try:
            got_it = driver.find_element("xpath", '//*[@text="Got it"]')
            if got_it:
                got_it.click()
                logging.info("✅ Got it tapped — payment confirmed")
                return True
        except Exception:
            pass

        try:
            success = driver.find_element("xpath", '//*[@text="Payment successful"]')
            if success:
                logging.info("✅ Payment successful detected")
                time.sleep(1)
                return True
        except Exception:
            pass

        try:
            driver.find_element("xpath", '//*[@text="Buy"]')
        except Exception:
            logging.info("✅ Google Play closed — back in game")
            return True

        time.sleep(0.5)

    # 🔥 NEW: FINAL CLEANUP
    close_extra_google_play_popups(driver)

    logging.warning("⚠️ Payment confirmation not detected")
    return False


# -------------------------------
# RECONNECT
# -------------------------------
def reconnect_alttester(unity_driver=None):
    logging.info("🔌 Reconnecting AltTester...")

    if unity_driver is not None:
        try:
            unity_driver.stop()
            logging.info("🔌 Old AltTester driver closed")
            time.sleep(0.5)
        except Exception as e:
            logging.warning(f"⚠️ Could not close old driver: {e}")

    for i in range(10):
        try:
            driver = AltDriver(host="127.0.0.1", port=13000, app_name="sorry")
            logging.info("✅ Reconnected AltTester")
            return driver
        except Exception as e:
            logging.warning(f"⚠️ Reconnect attempt {i + 1} failed: {e}")
            time.sleep(3)

    raise Exception("❌ AltTester reconnect failed")


# -------------------------------
# PURCHASE POPUP
# -------------------------------
def handle_purchase_popup(unity):
    """Poll for Unity purchase popup."""
    end = time.time() + 15
    while time.time() < end:
        try:
            popup = unity.wait_for_object(By.PATH, PURCHASE_POPUP, timeout=1)
            if popup:
                break
        except Exception:
            time.sleep(0.5)
    else:
        logging.warning("⚠️ Purchase popup never appeared")
        return False

    fail = fast_text(unity, PURCHASE_FAIL, timeout=1)

    if fail:
        logging.warning("❌ Purchase FAILED")
    else:
        logging.info("✅ Purchase SUCCESS")

    try:
        ok = unity.wait_for_object(By.PATH, PURCHASE_OK, timeout=3)
        if ok:
            ok.tap()
            time.sleep(0.5)
    except Exception:
        pass

    return not bool(fail)


# -------------------------------
# SCROLL
# -------------------------------
def scroll_shop(unity):
    try:
        unity.swipe(500, 1500, 500, 500, duration=500)
        time.sleep(0.5)
    except Exception as e:
        logging.warning(f"⚠️ Scroll failed: {e}")


# -------------------------------
# MAIN TEST
# -------------------------------
def test_shop_purchase(unity_driver, driver):
    logging.info("🛒 Starting Shop Purchase Test")

    # GUARD
    check_preconditions()

    # STEP 1: OPEN SHOP
    time.sleep(2)
    shop_btn = wait_for_safe(unity_driver, By.PATH, SHOP_BUTTON, 15)
    if not shop_btn:
        raise Exception("❌ Shop button not found")

    safe_tap(unity_driver, shop_btn)
    time.sleep(2)
    clear_all_popups(unity_driver)

    # STEP 2: PURCHASE ALL PACKS
    all_packs = GOLD_PACKS + GEM_PACKS

    for name, path in all_packs:
        logging.info(f"💰 Purchasing → {name}")

        before_gold, before_gems = get_wallet_snapshot(unity_driver, GOLD_TEXT, GEMS_TEXT)
        logging.info(f"   Before → 🪙 {before_gold} | 💎 {before_gems}")

        # Find pack button with scroll fallback
        obj = wait_for_safe(unity_driver, By.PATH, path, 2)
        if not obj:
            scroll_shop(unity_driver)
            obj = wait_for_safe(unity_driver, By.PATH, path, 2)

        if not obj:
            logging.error(f"❌ Could not find {name} — skipping")
            continue

        safe_tap(unity_driver, obj)

        # Wait for Google Play sheet to appear
        time.sleep(3)

        # Tap Buy + handle Got it via Appium
        handle_google_play_purchase(driver)

        # Wait for game to process purchase
        time.sleep(3)

        # Reconnect AltTester
        unity_driver = reconnect_alttester(unity_driver)

        # Handle Unity purchase popup
        success = handle_purchase_popup(unity_driver)
        
        # Wait for HUD to update after purchase
        time.sleep(2)

        after_gold, after_gems = get_wallet_snapshot(unity_driver, GOLD_TEXT, GEMS_TEXT)

        if success:
            logging.info(f"🟢 {name} | 🪙 {before_gold} → {after_gold} | 💎 {before_gems} → {after_gems}")
        else:
            logging.warning(f"🔴 {name} FAILED | 🪙 {before_gold} → {after_gold} | 💎 {before_gems} → {after_gems}")

        time.sleep(1)

    # STEP 3: NAVIGATE BACK TO HOME
    logging.info("🏠 Navigating back to home...")
    home_btn = wait_for_safe(unity_driver, By.PATH, HOME_BUTTON, 10)

    if home_btn:
        safe_tap(unity_driver, home_btn)
        time.sleep(1)
        clear_all_popups(unity_driver)
    else:
        logging.warning("⚠️ Home button not found")

    # STEP 4: READ FINAL WALLET FROM HOME HUD
    gold_ui, gems_ui = get_wallet_snapshot(unity_driver, HOME_GOLD_TEXT, HOME_GEMS_TEXT)

    state.set_user_info("gold", gold_ui)
    state.set_user_info("gems", gems_ui)

    logging.info("🏠 Final Wallet:")
    logging.info(f"   🪙 Gold : {gold_ui}")
    logging.info(f"   💎 Gems : {gems_ui}")

    # STEP 5: COMPARE WITH DB
    try:
        player_id = state.user_info.get("player_id")

        if not player_id:
            logging.warning("⚠️ No player_id in state — skipping DB check")
            return unity_driver

        wallet_db = get_user_wallet(player_id)

        logging.info("📊 FINAL COMPARISON (UI vs DB)")
        logging.info(f"   🪙 Gold → UI: {gold_ui} | DB: {wallet_db.get('gold')}")
        logging.info(f"   💎 Gems → UI: {gems_ui} | DB: {wallet_db.get('gems')}")

    except Exception as e:
        logging.warning(f"⚠️ DB check skipped: {e}")

    return unity_driver