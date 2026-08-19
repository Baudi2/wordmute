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


def remote_thumbnail_path(video_url: str, thumb_url: str) -> Path | None:
    """Fetch a video page's poster image into the thumb cache (keyed by
    the VIDEO url, so re-adding a link reuses it). The image goes
    through ffmpeg for the same scale/crop as local thumbs — that also
    converts webp (YouTube's default), which a frozen Qt without its
    imageformats plugins cannot load."""
    if not thumb_url:
        return None
    key = hashlib.md5(f"url|{video_url}".encode("utf-8",
                                                "replace")).hexdigest()
    out = thumbs_dir() / f"{key}.jpg"
    if out.exists():
        return out
    import os
    import tempfile
    import urllib.request
    try:
        with urllib.request.urlopen(thumb_url, timeout=15) as response:
            data = response.read()
    except OSError:
        return None
    fd, raw_name = tempfile.mkstemp(prefix="wm_thumb_")
    os.close(fd)          # an open fd blocks deletion on Windows
    raw = Path(raw_name)
    try:
        raw.write_bytes(data)
        cmd = [
            "ffmpeg", "-y", "-v", "error", "-i", str(raw),
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
    finally:
        raw.unlink(missing_ok=True)


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
