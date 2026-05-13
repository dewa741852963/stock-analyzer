import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".stock_analyzer" / "config.json"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}

def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))

def get_api_key() -> str:
    return load_config().get("gemini_api_key", "")

def set_api_key(key: str):
    config = load_config()
    config["gemini_api_key"] = key.strip()
    save_config(config)
