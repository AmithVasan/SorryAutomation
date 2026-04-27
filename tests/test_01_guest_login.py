import time
import logging
import subprocess

from alttester import By, AltDriver
from utils.mongo_helper import boost_player_level
from utils.state_manager import state
from utils.popup_handler import wait_for_safe, safe_tap, clear_all_popups, handle_one_popup
from utils.device_helpers import handle_permissions
from utils.driver_manager import get_local_ip
from config import ADB_PATH

PACKAGE_NAME = "com.gameberry.sorry.card.board.game"
ACTIVITY_NAME = "com.unity3d.player.SorryUnityPlayerActivity"
ALTTESTER_PORT = 13000
APP_NAME = "sorry"


# -------------------------------
# RESTART + RECONNECT
# -------------------------------
def restart_and_reconnect(driver, unity_driver):
    device_id = driver.capabilities.get("udid") or driver.capabilities.get("deviceName")

    logging.info(f"🔄 Restarting game on {device_id}...")

    subprocess.run([ADB_PATH, "-s", device_id, "shell", "am", "force-stop", PACKAGE_NAME])
    time.sleep(2)

    subprocess.run([
        ADB_PATH, "-s", device_id, "shell", "am", "start",
        "-n", f"{PACKAGE_NAME}/{ACTIVITY_NAME}"
    ])

    logging.info("🚀 Game relaunched")
    time.sleep(5)

    try:
        ip = get_local_ip()

        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", "500", "1350"])
        time.sleep(0.5)

        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "123"])
        time.sleep(0.2)

        for _ in range(25):
            subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "67"])

        subprocess.run([
            ADB_PATH, "-s", device_id,
            "shell", "input", "text", ip.replace(".", "\\.")
        ])

        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "keyevent", "66"])
        time.sleep(1)
        subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", "534", "1519"])

        logging.info("✅ Restart tapped")

    except Exception as e:
        logging.warning(f"⚠️ AltTester popup skip: {e}")

    time.sleep(6)

    try:
        unity_driver.stop()
        logging.info("🔌 Old AltTester driver closed")
        time.sleep(1)
    except Exception as e:
        logging.warning(f"⚠️ Could not close old driver: {e}")

    for i in range(5):
        try:
            unity_driver = AltDriver(host="127.0.0.1", port=ALTTESTER_PORT, app_name=APP_NAME)
            logging.info("✅ AltTester reconnected")
            return unity_driver
        except Exception as e:
            logging.warning(f"⚠️ Reconnect attempt {i + 1} failed: {e}")
            time.sleep(2)

    raise Exception("❌ AltTester reconnect failed")


# -------------------------------
# FAST TEXT READ (no popup clearing)
# -------------------------------
def fast_text(unity_driver, path, timeout=2):
    """
    Direct element read — no popup clearing overhead.
    Use only when UI is stable (inside modals, HUD reads).
    """
    try:
        obj = unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
        if not obj:
            return None
        txt = obj.get_component_property(
            "TMPro.TextMeshProUGUI",
            "text",
            "Unity.TextMeshPro"
        )
        return txt if txt not in (None, "", "N/A") else None
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


# -------------------------------
# SNAPSHOT
# -------------------------------
def get_user_snapshot(unity_driver):
    logging.info("📸 Capturing user snapshot...")

    # Open profile modal
    profile = wait_for_safe(
        unity_driver,
        By.PATH,
        "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/profileSection/profileIcon/ProfileButton",
        5
    )

    if not profile:
        raise Exception("❌ Profile button not found")

    profile.tap()
    time.sleep(1)

    # Read all profile fields using fast_text (no popup clearing)
    player_name = fast_text(unity_driver,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/Content/topSection/section-Name/playerName"
    )

    country = fast_text(unity_driver,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/Content/topSection/section-Country/TextStyle_subText_medium_bold/countryNameText"
    )

    player_id = fast_text(unity_driver,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/Content/topSection/TextStyle_bodyText_large_bold/playerIDText"
    )

    if player_id:
        player_id = player_id.replace("PLAYER ID:", "").strip()

    level = fast_text(unity_driver,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/Content/midSection/container/progressBar/xpStar/TextStyle_Notifs/level"
    )

    xp = fast_text(unity_driver,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/Content/midSection/container/progressBar/Progressbar/TextStyle_Notifs/xpProgress"
    )

    # Close profile modal
    close = wait_for_safe(
        unity_driver,
        By.PATH,
        "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/bgMain/SorryButtonType-Misc/touchArea",
        3
    )

    if close:
        close.tap()

    time.sleep(0.5)

    # Read HUD wallet (fast — always visible on home)
    gold   = parse_amount(fast_text(unity_driver,
        "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text"
    ))

    gems   = parse_amount(fast_text(unity_driver,
        "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text"
    ))

    hammer = parse_amount(fast_text(unity_driver,
        "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/hammerBar/text"
    ))

    # Save to state
    state.set_user_info("player_name", player_name)
    state.set_user_info("country", country)
    state.set_user_info("player_id", player_id)
    state.set_user_info("level", int(level) if level and level.isdigit() else level)
    state.set_user_info("xp", xp)
    state.set_user_info("gold", gold)
    state.set_user_info("gems", gems)
    state.set_user_info("hammer", hammer)

    # Log line by line
    logging.info("📊 User Snapshot:")
    logging.info(f"   👤 Name    : {player_name}")
    logging.info(f"   🌍 Country : {country}")
    logging.info(f"   🆔 ID      : {player_id}")
    logging.info(f"   ⭐ Level   : {level}")
    logging.info(f"   📈 XP      : {xp}")
    logging.info(f"   🪙 Gold    : {gold}")
    logging.info(f"   💎 Gems    : {gems}")
    logging.info(f"   🔨 Hammer  : {hammer}")


# -------------------------------
# NAVIGATION
# -------------------------------
def reach_home(unity_driver, driver):
    end = time.time() + 60

    while time.time() < end:
        handle_permissions(driver)
        handle_one_popup(unity_driver)

        home = wait_for_safe(
            unity_driver,
            By.PATH,
            "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon",
            2
        )

        if home:
            home.tap()
            return True

        time.sleep(0.5)

    raise Exception("❌ Failed to reach home")


# -------------------------------
# MAIN TEST
# -------------------------------
def test_guest_login(unity_driver, driver):
    logging.info("🚀 Guest Login Test")

    # -------------------------------
    # LOGIN (if needed)
    # -------------------------------
    login = wait_for_safe(unity_driver, By.PATH, "/Canvas/midUiLayer/loginScreen", 5)

    if login:
        logging.info("🔐 Login screen found → tapping Guest")
        guest = wait_for_safe(
            unity_driver,
            By.PATH,
            "/Canvas/midUiLayer/loginScreen/buttonsParent/guestCTA/TouchArea",
            5
        )

        if not guest:
            raise Exception("❌ Guest button not found")

        guest.tap()
        time.sleep(1)
    else:
        logging.info("⚡ Already logged in → skipping login screen")

    # -------------------------------
    # REACH HOME + SNAPSHOT
    # -------------------------------
    reach_home(unity_driver, driver)
    get_user_snapshot(unity_driver)

    player_id = state.user_info.get("player_id")

    # Safe level parsing
    try:
        current_level = int(state.user_info.get("level", 0))
    except Exception:
        current_level = 0

    if not player_id:
        raise Exception("❌ Player ID missing")

    # -------------------------------
    # CONDITIONAL BOOST + RESTART
    # -------------------------------
    boosted = False
    if current_level >= 50:
        logging.info("⚡ Account is already boosted → skipping DB update & restart")
    else:
        logging.info(f"🚀 Current level {current_level} → boosting to 50")

        boost_player_level(player_id)

        unity_driver = restart_and_reconnect(driver, unity_driver)

        # After restart → reach home again
        reach_home(unity_driver, driver)

    # -------------------------------
    # FINAL SNAPSHOT (validation)
    # -------------------------------
    if boosted:
        get_user_snapshot(unity_driver)

    logging.info("✅ Guest Login Test Completed")
    return unity_driver