import time
import logging

START_TIME = None


def pytest_sessionstart(session):
    global START_TIME
    START_TIME = time.time()
    logging.info("🚀 TEST SESSION STARTED")


def pytest_sessionfinish(session, exitstatus):
    total = time.time() - START_TIME

    mins = int(total // 60)
    secs = int(total % 60)

    logging.info("🏁 TEST SESSION FINISHED")
    logging.info(f"⏱️ TOTAL EXECUTION TIME: {mins}m {secs}s")