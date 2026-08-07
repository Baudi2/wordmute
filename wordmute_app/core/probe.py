"""Media duration probing via ffprobe (ships with ffmpeg).

Duration is used for progress percent / ETA only; probing failures are
harmless (progress just shows raw minutes instead)."""

import subprocess
from pathlib import Path


def media_duration(path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(Path(path))],
            capture_output=True, text=True, timeout=15,
        )
        value = r.stdout.strip()
        if r.returncode == 0 and value:
            return float(value)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None
