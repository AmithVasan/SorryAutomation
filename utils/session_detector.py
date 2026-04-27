import logging
import time
from alttester import By

from utils.popup_handler import clear_all_popups, wait_for_safe
from utils.state_manager import state


LOGIN_PATH = "/Canvas/midUiLayer/loginScreen"
HOME_BUTTON = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon"
DAILY_LOGIN = "/Canvas/ModalLayer/DailyLoginModal(Clone)/rootMain/claimButton"
FTUE_SKIP = "/Canvas/FTUE-InGame/container/scaleAdjuster/skipButton/TouchArea"


def detect_session_state(unity_driver, driver):
    logging.info("🧠 SESSION START")

    # ---------------- CLEAN UI ----------------
    for _ in range(3):
        clear_all_popups(unity_driver)
        time.sleep(0.5)

    # ---------------- LOGIN ----------------
    login = wait_for_safe(unity_driver, By.PATH, LOGIN_PATH, 3)

    if login:
        logging.info("🔐 Login screen → Guest login")

        guest = wait_for_safe(
            unity_driver,
            By.PATH,
            "/Canvas/midUiLayer/loginScreen/buttonsParent/guestCTA/TouchArea",
            5
        )

        if guest:
            guest.tap()
            time.sleep(4)

        clear_all_popups(unity_driver)
    else:
        logging.info("✅ Already logged in")

    # ---------------- FTUE ----------------
    for _ in range(10):
        ftue = wait_for_safe(unity_driver, By.PATH, FTUE_SKIP, 1)
        if not ftue:
            break

        logging.info("🎓 FTUE skip")
        ftue.tap()
        time.sleep(1)

    clear_all_popups(unity_driver)

    # ---------------- DAILY LOGIN ----------------
    for _ in range(5):
        daily = wait_for_safe(unity_driver, By.PATH, DAILY_LOGIN, 2)
        if not daily:
            break

        logging.info("🎁 Daily login collected")
        daily.tap()
        time.sleep(2)
        clear_all_popups(unity_driver)

    # ---------------- HOME ----------------
    home = None
    for _ in range(5):
        clear_all_popups(unity_driver)
        home = wait_for_safe(unity_driver, By.PATH, HOME_BUTTON, 3)
        if home:
            break
        time.sleep(1)

    if not home:
        raise Exception("❌ HOME not reachable")

    logging.info("🏠 HOME READY")
    return True