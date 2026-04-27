import time
import logging

from tests import test_01_guest_login.test_guest_login
from utils.state_manager import state


class ExecutionEngine:

    def __init__(self, unity_driver, appium_driver):
        self.unity = unity_driver
        self.driver = appium_driver
        self.start_time = None

    def start_timer(self):
        self.start_time = time.time()

    def end_timer(self):
        return round(time.time() - self.start_time, 2)

    def run_all(self):
        logging.info("🚀 EXECUTION ENGINE STARTED")
        self.start_timer()

        try:
            # -------------------------------
            # MAIN FLOW
            # -------------------------------
            test_01_guest_login(self.unity, self.driver)

            # -------------------------------
            # FINAL REPORT
            # -------------------------------
            duration = self.end_timer()

            logging.info("\n======================================")
            logging.info("⏱️ EXECUTION SUMMARY")
            logging.info("======================================")
            logging.info(f"⏳ Total Execution Time: {duration} seconds")

            state.print_summary()

            logging.info("======================================\n")

        except Exception as e:
            logging.error(f"❌ Execution failed: {e}")