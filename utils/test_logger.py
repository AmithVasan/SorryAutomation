import logging


class TestStepCollector(logging.Handler):

    def __init__(self):
        super().__init__()
        self.steps = []

    def emit(self, record):

        msg = record.getMessage()

        # Ignore noisy infra logs
        ignored = [
            "Websocket connected",
            "[wait_for_safe]",
        ]

        if any(x in msg for x in ignored):
            return

        self.steps.append(msg)