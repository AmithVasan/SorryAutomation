import time
import logging

from alttester import By

from utils.popup_handler import (
    wait_for_safe,
    safe_tap,
    handle_one_popup,
    clear_all_popups,
)

from utils.helpers import (
    parse_amount,
    get_wallet_from_data,
)

from utils.paths import (
    LUCKY_CARDS_ICON,
    LUCKY_CARDS_COUNTER,
    FTUE_MODAL,
    LUCKY_CARD_TOUCH_AREA,
    SEND_GET_CARDS_DRAWER,
    DRAWER_CLOSE,
    LUCKY_CARDS_CLOSE,
    HOME_GOLD_TEXT,
    HOME_GEMS_TEXT,
)


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def get_wallet_values(unity_driver):
    """
    Returns (gold_ui, gems_ui, wallet_data) where wallet_data is a dict
    with keys "gold", "gems", "pips" fetched from UserManager in-memory.
    """
    gold_el = wait_for_safe(
        unity_driver,
        By.PATH,
        HOME_GOLD_TEXT,
        10
    )

    gems_el = wait_for_safe(
        unity_driver,
        By.PATH,
        HOME_GEMS_TEXT,
        10
    )

    gold = parse_amount(
        gold_el.get_text()
    ) if gold_el else 0

    gems = parse_amount(
        gems_el.get_text()
    ) if gems_el else 0

    wallet_data = get_wallet_from_data(unity_driver)

    return gold, gems, wallet_data


# ---------------------------------------------------
# OPEN LUCKY CARDS
# ---------------------------------------------------

def open_lucky_cards(unity_driver):

    logging.info("🃏 Opening Lucky Cards")

    clear_all_popups(unity_driver)

    icon = wait_for_safe(
        unity_driver,
        By.PATH,
        LUCKY_CARDS_ICON,
        15
    )

    if not icon:
        raise Exception("❌ Lucky Cards icon not found")

    safe_tap(unity_driver, icon)

    time.sleep(3)

    clear_all_popups(unity_driver)

    logging.info("✅ Lucky Cards opened")


# ---------------------------------------------------
# HANDLE FTUE
# ---------------------------------------------------

def handle_ftue(unity_driver):

    ftue = wait_for_safe(
        unity_driver,
        By.PATH,
        FTUE_MODAL,
        5
    )

    if not ftue:
        return

    logging.info("🎓 FTUE detected")

    try:

        # ONLY HANDLE DRAWER
        # DO NOT TAP CARD HERE

        drawer = wait_for_safe(
            unity_driver,
            By.PATH,
            SEND_GET_CARDS_DRAWER,
            5
        )

        if drawer:

            logging.info(
                "📦 Closing FTUE drawer"
            )

            safe_tap(unity_driver, drawer)

            time.sleep(2)

        drawer_close = wait_for_safe(
            unity_driver,
            By.PATH,
            DRAWER_CLOSE,
            5
        )

        if drawer_close:

            safe_tap(
                unity_driver,
                drawer_close
            )

            time.sleep(1)

        logging.info("✅ FTUE handled")

    except Exception as e:

        logging.warning(
            f"⚠️ FTUE handling failed: {e}"
        )


# ---------------------------------------------------
# GET AVAILABLE CARDS
# ---------------------------------------------------

def get_available_cards(unity_driver):

    counter = wait_for_safe(
        unity_driver,
        By.PATH,
        LUCKY_CARDS_COUNTER,
        10
    )

    if not counter:
        return 0

    try:
        return int(counter.get_text().strip())

    except Exception:
        return 0


# ---------------------------------------------------
# TAP SINGLE CARD
# ---------------------------------------------------

def tap_single_card(unity_driver, card_number):

    logging.info(
        f"🃏 Tapping card {card_number}"
    )

    touch_area = wait_for_safe(
        unity_driver,
        By.PATH,
        LUCKY_CARD_TOUCH_AREA,
        10
    )

    if not touch_area:
        raise Exception(
            "❌ Card touch area not found"
        )

    safe_tap(unity_driver, touch_area)

    time.sleep(2)

    # HANDLE REWARD POPUPS
    popup_end = time.time() + 8

    while time.time() < popup_end:

        handled = handle_one_popup(
            unity_driver
        )

        if not handled:
            break

        time.sleep(1)

    logging.info(
        f"✅ Card {card_number} completed"
    )


# ---------------------------------------------------
# CLOSE LUCKY CARDS
# ---------------------------------------------------

def close_lucky_cards(unity_driver):

    logging.info(
        "❌ Closing Lucky Cards"
    )

    close_btn = wait_for_safe(
        unity_driver,
        By.PATH,
        LUCKY_CARDS_CLOSE,
        15
    )

    if not close_btn:
        raise Exception(
            "❌ Lucky Cards close button not found"
        )

    safe_tap(unity_driver, close_btn)

    time.sleep(3)

    clear_all_popups(unity_driver)

    logging.info(
        "✅ Lucky Cards closed"
    )


# ---------------------------------------------------
# MAIN TEST
# ---------------------------------------------------

def test_lucky_cards(unity_driver, driver, run_type=None):

    start_time = time.time()

    steps = []

    def add_step(message, status="INFO"):

        steps.append({
            "timestamp": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "status": status,
            "step": message
        })

        logging.info(message)

    try:

        add_step(
            "🃏 Starting Lucky Cards Test",
            "PASS"
        )

        clear_all_popups(unity_driver)

        # ---------------------------------------------------
        # BEFORE WALLET
        # ---------------------------------------------------

        old_gold, old_gems, old_wallet_data = get_wallet_values(
            unity_driver
        )

        add_step(
            f"ℹ️ Old Gold:  UI={old_gold}  Data={old_wallet_data.get('gold')}"
        )

        add_step(
            f"ℹ️ Old Gems:  UI={old_gems}  Data={old_wallet_data.get('gems')}"
        )

        # ---------------------------------------------------
        # OPEN LUCKY CARDS
        # ---------------------------------------------------

        open_lucky_cards(unity_driver)

        # HANDLE FTUE
        handle_ftue(unity_driver)

        # ---------------------------------------------------
        # AVAILABLE CARDS
        # ---------------------------------------------------

        available_cards = get_available_cards(
            unity_driver
        )

        add_step(
            f"ℹ️ Available Lucky Cards: "
            f"{available_cards}"
        )

        if available_cards <= 0:

            raise Exception(
                "❌ No Lucky Cards available"
            )

        # ALWAYS TRY 3
        cards_to_tap = min(
            3,
            available_cards
        )

        add_step(
            f"ℹ️ Will tap "
            f"{cards_to_tap} card(s)"
        )

        # ---------------------------------------------------
        # TAP CARDS
        # ---------------------------------------------------

        successful_taps = 0

        for i in range(cards_to_tap):

            try:

                tap_single_card(
                    unity_driver,
                    i + 1
                )

                successful_taps += 1

                # WAIT FOR NEXT CARD
                retry_end = (
                    time.time() + 10
                )

                while (
                    time.time() < retry_end
                ):

                    touch_area = wait_for_safe(
                        unity_driver,
                        By.PATH,
                        LUCKY_CARD_TOUCH_AREA,
                        2
                    )

                    if touch_area:
                        break

                    time.sleep(1)

                time.sleep(2)

            except Exception as e:

                logging.warning(
                    f"⚠️ Card {i + 1} failed: {e}"
                )

        add_step(
            f"✅ Successfully tapped "
            f"{successful_taps} card(s)",
            "PASS"
        )

        # ---------------------------------------------------
        # WAIT FOR REWARD ANIMATIONS
        # ---------------------------------------------------

        time.sleep(3)

        # ---------------------------------------------------
        # CLOSE MODAL
        # ---------------------------------------------------

        close_lucky_cards(unity_driver)

        # ---------------------------------------------------
        # FINAL WALLET
        # ---------------------------------------------------

        new_gold, new_gems, new_wallet_data = get_wallet_values(
            unity_driver
        )

        add_step(
            f"ℹ️ New Gold:  UI={new_gold}  Data={new_wallet_data.get('gold')}"
        )

        add_step(
            f"ℹ️ New Gems:  UI={new_gems}  Data={new_wallet_data.get('gems')}"
        )

        gold_earned = new_gold - old_gold
        gems_earned = new_gems - old_gems

        data_gold_earned = (
            (new_wallet_data.get("gold") - old_wallet_data.get("gold"))
            if (new_wallet_data.get("gold") is not None and old_wallet_data.get("gold") is not None)
            else "N/A"
        )
        data_gems_earned = (
            (new_wallet_data.get("gems") - old_wallet_data.get("gems"))
            if (new_wallet_data.get("gems") is not None and old_wallet_data.get("gems") is not None)
            else "N/A"
        )

        logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logging.info("🃏 Lucky Cards Wallet Comparison (UI vs Data)")
        logging.info(
            f"   🟡 Gold  → UI earned: {gold_earned:<10} | Data earned: {data_gold_earned}"
        )
        logging.info(
            f"   💎 Gems  → UI earned: {gems_earned:<10} | Data earned: {data_gems_earned}"
        )
        logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        add_step(
            f"✅ Gold Earned: "
            f"UI={gold_earned}  Data={data_gold_earned}"
        )

        add_step(
            f"✅ Gems Earned: "
            f"UI={gems_earned}  Data={data_gems_earned}"
        )

        add_step(
            "✅ Lucky Cards Test Completed",
            "PASS"
        )

        return {
            "name": "Lucky Cards",
            "status": "PASS",
            "duration": round(
                time.time() - start_time,
                2
            ),
            "steps": steps,
            "unity_driver": unity_driver
        }

    except Exception as e:

        add_step(
            f"❌ Test failed: {str(e)}",
            "FAIL"
        )

        return {
            "name": "Lucky Cards",
            "status": "FAIL",
            "duration": round(
                time.time() - start_time,
                2
            ),
            "steps": steps,
            "unity_driver": unity_driver
        }