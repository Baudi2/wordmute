"""Media probing via ffmpeg/ffprobe.

Duration is used for progress percent / ETA only; probing failures are
harmless (progress just shows raw minutes instead)."""

import re
import subprocess
from pathlib import Path

from .proc import creationflags


def media_duration(path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(Path(path))],
            capture_output=True, text=True, timeout=15,
            creationflags=creationflags(),
        )
        value = r.stdout.strip()
        if r.returncode == 0 and value:
            return float(value)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def audio_start_offset(path) -> float | None:
    """Where the first decoded audio sample sits on mute()'s clock
    (ffmpeg's filter t with every stream selected). Review sidecars
    saved before the file-clock fix counted from that sample instead of
    the file clock: 0.556009 s on a rutube episode, 0.483991 on its
    .clean.mp4. None when ffmpeg fails or shows no audio frame."""
    from ..engine.wordmute import INPUT_FLAGS
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info", *INPUT_FLAGS,
           "-i", str(Path(path)), "-map", "0", "-c", "copy",
           "-c:a", "pcm_s16le", "-filter:a:0", "ashowinfo",
           "-t", "1", "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=creationflags())
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"pts_time:(-?[0-9.]+)", r.stderr or "")
    return float(match.group(1)) if match else None
