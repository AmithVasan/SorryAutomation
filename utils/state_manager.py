import threading
import logging


_DEFAULT_USER_INFO = {
    "player_id":     None,
    "player_name":   None,
    "name":          None,
    "country":       None,
    "gold":          None,
    "gems":          None,
    "hammer":        None,
    "level":         None,
    "xp":            None,
    "equipped_pawn": None,
}


class StateManager:
    """
    Thread-local state store.

    Each thread (= each device worker in parallel mode) gets its own
    completely isolated copy of every key, user_info field, and reward
    list.  No cross-thread bleed, no locks needed.

    In single-device mode the main thread is the only thread, so
    behaviour is identical to the old global-variable approach.
    """

    def __init__(self):
        self._local = threading.local()

    # ── bootstrap ─────────────────────────────────────────────────────────

    def _init(self):
        """Initialise per-thread storage on first access."""
        if not hasattr(self._local, "_ready"):
            self._local._ready    = True
            self._local._store    = {}
            self._local.rewards   = []
            self._local.user_info = dict(_DEFAULT_USER_INFO)

    # ── rewards ───────────────────────────────────────────────────────────

    @property
    def rewards(self):
        self._init()
        return self._local.rewards

    def add_reward(self, source, reward_type, amount):
        self.rewards.append({"source": source, "type": reward_type, "amount": amount})

    # ── user_info ─────────────────────────────────────────────────────────

    @property
    def user_info(self):
        self._init()
        return self._local.user_info

    def set_user_info(self, key, value):
        if key in self.user_info:
            self.user_info[key] = value
        else:
            logging.warning(f"⚠️ Unknown user_info key: {key}")

    def get_user_info(self, key, default=None):
        value = self.user_info.get(key, default)
        if value == "None":
            return default
        return value

    def get_all_user_info(self):
        return self.user_info.copy()

    # ── generic key-value store ───────────────────────────────────────────

    def set(self, key, value):
        self._init()
        self._local._store[key] = value

    def get(self, key, default=None):
        self._init()
        return self._local._store.get(key, default)


state = StateManager()
