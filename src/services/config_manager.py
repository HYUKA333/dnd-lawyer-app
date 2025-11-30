import json
import os
from pathlib import Path
from typing import Dict, Any


class ConfigManager:
    """
    负责加载和保存 data/user_settings.json
    对应规格书: src/services/config_manager.py
    """

    DEFAULT_SETTINGS = {
        "api_provider": "openai",  # "google" or "openai"
        "api_key": "",
        "api_base_url": "",
        "model_name": "gemini-1.5-flash",
        "temperature": 0.1,
        "top_k": 10,
        "data_dir": "data",
        "chm_source_dir": "chm_source"
    }

    def __init__(self):
        self.root_dir = Path(os.getcwd())
        self.data_dir = self.root_dir / "data"
        self.settings_file = self.data_dir / "user_settings.json"

        self._ensure_dirs()
        self.settings = self.load_settings()

    def _ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> Dict[str, Any]:
        if not self.settings_file.exists():
            return self.DEFAULT_SETTINGS.copy()

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                settings = self.DEFAULT_SETTINGS.copy()
                settings.update(data)
                return settings
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self.DEFAULT_SETTINGS.copy()

    def save_settings(self, new_settings: Dict[str, Any]):
        self.settings.update(new_settings)
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def get(self, key: str):
        return self.settings.get(key, self.DEFAULT_SETTINGS.get(key))


# 全局单例
config_manager = ConfigManager()