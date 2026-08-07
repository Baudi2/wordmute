"""App data directory, settings persistence, first-run word list setup.

Word list templates ship read-only inside the app; on first run they are
copied into the user's data dir and only those copies are ever edited,
so reinstalls/updates never clobber user customizations.
"""

import json
import os
import sys
from pathlib import Path
from shutil import copyfile

APP_NAME = "WordMute"

WORDLIST_TEMPLATES = {
    "russian": "words_russian.txt",
    "english": "words_english.txt",
}

DEFAULT_SETTINGS = {
    "device": "cuda",
    "model": "large-v3",
    "passes": 2,
    "pad_ms": 100,
    "language": "ru",
    "use_russian": True,
    "use_english": False,
}


def resources_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(sys._MEIPASS) / "wordmute_app" / "resources"
    return Path(__file__).resolve().parents[1] / "resources"


def data_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def wordlists_dir() -> Path:
    d = data_dir() / "wordlists"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_user_wordlists() -> dict:
    """Copy shipped templates into the user's data dir if not already
    there. Never overwrites existing (possibly user-edited) lists.
    Returns {list_key: Path}."""
    out = {}
    for key, name in WORDLIST_TEMPLATES.items():
        dst = wordlists_dir() / name
        if not dst.exists():
            copyfile(resources_dir() / name, dst)
        out[key] = dst
    return out


def _settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        stored = json.loads(_settings_path().read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            settings.update(stored)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    _settings_path().write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
