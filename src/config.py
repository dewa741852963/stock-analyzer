import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".stock_analyzer" / "config.json"

DEFAULTS = {
    "ai_provider": "gemini",       # gemini | ollama | custom
    "gemini_api_key": "",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3",
    "custom_url": "",
    "custom_model": "",
    "custom_api_key": "",
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def get(key: str):
    return load_config().get(key, DEFAULTS.get(key, ""))


def set_values(**kwargs):
    config = load_config()
    config.update(kwargs)
    save_config(config)


# Backwards compat
def get_api_key() -> str:
    return get("gemini_api_key")


def set_api_key(key: str):
    set_values(gemini_api_key=key.strip())
