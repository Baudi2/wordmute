"""Queue-card thumbnails: one ffmpeg frame grab ~10% into the video,
cached under the app data dir (keyed by path+mtime+size so edits
invalidate). Audio files get no thumbnail (the card shows a glyph)."""

import hashlib
import subprocess
from pathlib import Path

from . import config
from .probe import media_duration
from .proc import creationflags

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"}
THUMB_W, THUMB_H = 192, 108  # 2x the 96x54 display size for hi-dpi


def thumbs_dir() -> Path:
    d = config.data_dir() / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumbnail_path(media) -> Path | None:
    media = Path(media)
    if media.suffix.lower() in AUDIO_EXTS:
        return None
    try:
        stat = media.stat()
    except OSError:
        return None
    key = hashlib.md5(
        f"{media}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8",
                                                            "replace")
    ).hexdigest()
    out = thumbs_dir() / f"{key}.jpg"
    if out.exists():
        return out
    duration = media_duration(media) or 0.0
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{duration * 0.1:.2f}", "-i", str(media),
        "-frames:v", "1",
        "-vf", (f"scale={THUMB_W}:{THUMB_H}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={THUMB_W}:{THUMB_H}"),
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20,
                           creationflags=creationflags())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out if r.returncode == 0 and out.exists() else None
