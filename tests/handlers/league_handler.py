import time
import logging
from alttester import By


# -------------------------------
# SAFE WAIT
# -------------------------------
def wait_for_safe(unity, path, timeout=2):
    try:
        return unity.wait_for_object(By.PATH, path, timeout=timeout)
    except:
        return None


# -------------------------------
# DETECTION
# -------------------------------
def is_present(unity_driver, driver):
    return (
        wait_for_safe(unity_driver, "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg", 1)
        or wait_for_safe(unity_driver, "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/darkBG", 1)
    )


# -------------------------------
# HANDLER
# -------------------------------
def handle(unity_driver, driver):
    logging.info("🏆 League flow detected → Handling")

    end = time.time() + 20

    while time.time() < end:

        handled_any = False

        # -------------------------------
        # LEAGUE REWARD
        # -------------------------------
        reward_screen = wait_for_safe(
            unity_driver,
            "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/darkBG",
            1
        )

        if reward_screen:
            collect_btn = wait_for_safe(
                unity_driver,
                "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/rootMain/continueButton/buttonPrimaryCTA_Stroked/text",
                2
            )

            if collect_btn:
                collect_btn.tap()
                logging.info("🎁 League reward collected")
                time.sleep(3)
                handled_any = True
                continue

        # -------------------------------
        # LEAGUE INFO / FTUE
        # -------------------------------
        info_screen = wait_for_safe(
            unity_driver,
            "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg",
            1
        )

        if info_screen:
            logging.info("ℹ️ League FTUE/info detected")

            # Try close button first
            close_btn = wait_for_safe(
                unity_driver,
                "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea",
                2
            )

            if close_btn:
                close_btn.tap()
                logging.info("❌ League screen closed via button")
                time.sleep(2)
                handled_any = True
                continue

            # Fallback: tap anywhere (center)
            try:
                logging.info("🖱️ Tapping center to close League screen")
                unity_driver.tap(0.5, 0.5)  # normalized screen tap
                time.sleep(2)
                handled_any = True
                continue
            except:
                pass

        # -------------------------------
        # EXIT
        # -------------------------------
        if not handled_any:
            logging.info("✅ League flow handled completely")
            return

    logging.info("⚠️ League handler timeout exit")