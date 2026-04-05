import json
import os
from .constants import BASE_DIR, DEFAULT_CONFIG

class ConfigManager:
    def __init__(self):
        self.config_path = os.path.join(BASE_DIR, "config.json")
        self.conf = self.load_config()

    def load_config(self):
        conf = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    conf.update(d)
            except Exception as e:
                print(f"Config load error: {e}")
        return conf

    def save_config(self, new_conf=None):
        if new_conf:
            self.conf.update(new_conf)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.conf, f, indent=4)
            return True
        except Exception as e:
            print(f"Config save error: {e}")
            return False

    def get(self, key, default=None):
        return self.conf.get(key, default)

    def set(self, key, value):
        self.conf[key] = value
