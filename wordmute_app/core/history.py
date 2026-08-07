"""Processing history: one JSONL line per finished queue item."""

import json
from datetime import datetime

from . import config


def history_path():
    return config.data_dir() / "history.jsonl"


def append_history(record: dict) -> None:
    record = {"time": datetime.now().isoformat(timespec="seconds"), **record}
    with history_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(limit: int = 200) -> list:
    """Most recent first."""
    try:
        lines = history_path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(records))


def clear_history() -> None:
    history_path().unlink(missing_ok=True)
