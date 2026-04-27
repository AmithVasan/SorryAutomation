import logging


class StateManager:
    def __init__(self):
        self.rewards = []
        self.user_info = {
            "player_id": None,
            "player_name": None,
            "name": None,
            "country": None,
            "gold": None,
            "gems": None,
            "hammer": None,
            "level": None,
            "xp": None
        }

    def add_reward(self, source, reward_type, amount):
        self.rewards.append({
            "source": source,
            "type": reward_type,
            "amount": amount
        })

    def set_user_info(self, key, value):
        if key in self.user_info:
            self.user_info[key] = value
        else:
            logging.warning(f"⚠️ Unknown key: {key}")

    def get_user_info(self, key, default=None):
        value = self.user_info.get(key, default)
        if value == "None":
            return default
        return value

    def get_all_user_info(self):
        return self.user_info.copy()


state = StateManager()