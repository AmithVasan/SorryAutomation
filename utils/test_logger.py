import time
import logging

from utils.screenshots import capture, screenshots_enabled


class TestStepCollector(logging.Handler):
    """Collects each logged step of a test. When screenshots are enabled
    (SAT_SCREENSHOTS=1) and an Appium `driver` is supplied, it also captures
    a screenshot per step and attaches it to that step, so the HTML report can
    show every step of every feature — with no changes to the tests themselves.

    Capturing is throttled (min_interval) so a burst of log lines for one screen
    doesn't take many identical shots, and capped (max_shots) to bound run time
    and report size. A step with a shot is stored as a dict the report already
    understands; a step without one stays a plain string.
    """

    def __init__(self, driver=None, min_interval=0.3, max_shots=200):
        super().__init__()
        self.steps = []
        self.driver = driver
        self.capture_shots = screenshots_enabled() and driver is not None
        self.min_interval = min_interval
        self.max_shots = max_shots
        self._last_shot = 0.0
        self._shot_count = 0

    def emit(self, record):

        msg = record.getMessage()

        # Ignore noisy infra logs
        ignored = [
            "Websocket connected",
            "[wait_for_safe]",
        ]

        if any(x in msg for x in ignored):
            return

        shot = None
        if self.capture_shots and self._shot_count < self.max_shots:
            now = time.time()
            if now - self._last_shot >= self.min_interval:
                shot = capture(self.driver)
                if shot:
                    self._last_shot = now
                    self._shot_count += 1

        if shot:
            self.steps.append({"step": msg, "screenshot": shot})
        else:
            self.steps.append(msg)
