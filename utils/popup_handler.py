import time
import logging
from alttester import By

# -------------------------------
# 🎯 PRIORITY POPUPS (TOP → BOTTOM)
# -------------------------------
POPUP_PRIORITY = [
    # 🔴 CRITICAL
    [
        "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea",
        "/Canvas/ModalLayer/LeagueRewardClaimScreen(Clone)/rootMain/continueButton/buttonPrimaryCTA_Stroked",
        "/Canvas/ModalLayer/LeaderBoardModal(Clone)/header/SorryButtonType-Misc/touchArea",
        "/Canvas/ModalLayer/BuildFTUEModal(Clone)/skipGrp/closeCTA/TouchArea",
    ],

    # 🟠 HIGH
    [
        "/Canvas/ModalLayer/DailyLoginModal(Clone)/rootMain/claimButton",
        "/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/closeCTA/touchArea",
        "/Canvas/ModalLayer/ConnectToFacebookModal(Clone)/rootMain/closeButton/touchArea",
        "/Canvas/FTUE-InGame/container/scaleAdjuster/skipButton/TouchArea",
    ],

    # 🟡 MEDIUM
    [
        "/Canvas/ModalLayer/DuelEventMainModal(Clone)/rootMain/closeCTA/touchArea",
        "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea",
        "/Canvas/ModalLayer/CardCollectionNewAlbumPopup(Clone)/closeBtn/touchArea",
        "/Canvas/ModalLayer/FortuneIslandStartPopup(Clone)/rootMain/crossButton/touchArea",
    ],

    # 🟢 LOW
    [
        "/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)/rootMain/CrossButton/touchArea",
        "/Canvas/ModalLayer/PuzzleEventStartPopup(Clone)/rootMain/crossButton/touchArea",
        "/Canvas/ModalLayer/LeaderBoardModal(Clone)/header/SorryButtonType-Misc/touchArea",
        "/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg",
        "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg",
    ]
]


# -------------------------------
# 🔥 HANDLE ONE POPUP (FAST SCAN)
# -------------------------------
def handle_one_popup(unity_driver):
    for group in POPUP_PRIORITY:
        for path in group:
            try:
                obj = unity_driver.wait_for_object(By.PATH, path, timeout=0.15)
                if obj:
                    obj.tap()
                    logging.info(f"[PopupHandler] Closed → {path}")
                    time.sleep(0.2)
                    return True
            except:
                pass
    return False


# -------------------------------
# 🔁 CLEAR ALL POPUPS (OPTIMIZED)
# -------------------------------
def clear_all_popups(unity_driver, timeout=5):
    end = time.time() + timeout

    while time.time() < end:
        if not handle_one_popup(unity_driver):
            return True

        time.sleep(0.1)

    logging.warning("[PopupHandler] Timeout clearing popups")
    return False


# -------------------------------
# 🔍 SAFE WAIT (OPTIMIZED)
# -------------------------------
def wait_for_safe(unity_driver, by, value, timeout=6):
    end = time.time() + timeout
    last_popup_check = 0

    while time.time() < end:

        # 🔥 check popups only occasionally (NOT every loop)
        if time.time() - last_popup_check > 0.5:
            clear_all_popups(unity_driver)
            last_popup_check = time.time()

        try:
            obj = unity_driver.wait_for_object(by, value, timeout=0.5)
            if obj:
                return obj
        except:
            pass

        time.sleep(0.1)

    logging.warning(f"[wait_for_safe] Not found → {value}")
    return None


# -------------------------------
# 🎯 SAFE TAP
# -------------------------------
def safe_tap(unity_driver, obj):
    if not obj:
        raise Exception("❌ Cannot tap → object is None")

    clear_all_popups(unity_driver)

    try:
        obj.tap()
        time.sleep(0.2)
    except Exception as e:
        logging.error(f"[safe_tap] Failed: {e}")
        raise


# -------------------------------
# 🎯 FIND + TAP
# -------------------------------
def safe_find_and_tap(unity_driver, by, value, timeout=6):
    obj = wait_for_safe(unity_driver, by, value, timeout)

    if not obj:
        raise Exception(f"❌ Element not found: {value}")

    safe_tap(unity_driver, obj)
    return obj


# -------------------------------
# 🔍 UI BLOCK CHECK
# -------------------------------
def is_ui_blocked(unity_driver):
    for group in POPUP_PRIORITY:
        for path in group:
            try:
                obj = unity_driver.wait_for_object(By.PATH, path, timeout=0.15)
                if obj:
                    return True
            except:
                pass
    return False