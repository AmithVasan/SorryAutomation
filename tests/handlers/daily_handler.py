import time
import logging
from alttester import By


# -------------------------------
# SAFE WAIT
# -------------------------------
def wait_for_safe(unity_driver, path, timeout=2):
    try:
        return unity_driver.wait_for_object(By.PATH, path, timeout=timeout)
    except:
        return None


# -------------------------------
# DETECTION
# -------------------------------
def is_present(unity_driver, driver):
    return wait_for_safe(
        unity_driver,
        "/Canvas/ModalLayer/DailyLoginModal(Clone)/darkbg",
        2
    )


# -------------------------------
# HANDLER
# -------------------------------
def handle(unity_driver, driver):
    logging.info("🎁 Daily Login detected → Handling flow")

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
            logging.info("✅ Cosmetic equipped")
            time.sleep(2)
        else:
            later_btn = wait_for_safe(
                unity_driver,
                "/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/continueButton/Later_Button/TouchArea",
                3
            )

            if later_btn:
                later_btn.tap()
                logging.info("⏭️ Cosmetic skipped (Later)")
                time.sleep(2)

    logging.info("✅ Daily Login flow completed")