"""Review data: what was muted, where, by which pass — and re-rendering
after the user un-mutes false positives.

A review sidecar (<output>.wordmute.json) is written after each
successful job. Muting never alters the timeline (volume filter, no
cutting), so intervals from every pass share the source file's
timestamps; re-rendering is therefore ONE ffmpeg mute of the original
source with the still-muted intervals — no re-transcription ever."""

import json
import os
import shutil
from pathlib import Path

from ..engine import wordmute as engine

REVIEW_SUFFIX = ".wordmute.json"


def review_path_for(output) -> Path:
    output = Path(output)
    return output.with_suffix(output.suffix + REVIEW_SUFFIX)


def save_review(source, output, pad_ms: int, intervals: list,
                beep_hz=None) -> Path:
    """intervals: [{"s", "e", "text", "pass", "engine", "muted"}, ...]"""
    path = review_path_for(output)
    data = {
        "version": 1,
        "source": str(source),
        "output": str(output),
        "pad_ms": pad_ms,
        "beep_hz": beep_hz,
        "intervals": intervals,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load_review(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
            k in data for k in ("source", "output", "intervals")):
        raise ValueError("not a WordMute review file")
    return data


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def export_srt(data: dict, dest, muted_only: bool = True) -> int:
    """Write the review intervals as an SRT subtitle file (muted ones
    by default) — a reviewable/archivable record of what was cut.
    Returns the number of entries written."""
    entries = [iv for iv in data["intervals"]
               if not muted_only or iv.get("muted", True)]
    lines = []
    for n, iv in enumerate(entries, 1):
        lines += [str(n), f"{_srt_ts(iv['s'])} --> {_srt_ts(iv['e'])}",
                  iv.get("text", ""), ""]
    Path(dest).write_text("\n".join(lines), encoding="utf-8")
    return len(entries)


def apply_review(data: dict) -> None:
    """Rebuild the output from the original source, muting only the
    intervals still flagged muted. With everything un-muted the output
    becomes a plain copy of the source."""
    source = Path(data["source"])
    output = Path(data["output"])
    if not source.exists():
        raise FileNotFoundError(
            f"original file no longer exists: {source}")

    muted = [(iv["s"], iv["e"], iv["text"])
             for iv in data["intervals"] if iv.get("muted", True)]
    tmp = output.parent / (output.stem + ".tmp" + output.suffix)
    if muted:
        engine.mute(source, muted, tmp, beep_hz=data.get("beep_hz") or None)
    else:
        shutil.copyfile(source, tmp)
    os.replace(tmp, output)
    # the output's cached transcripts (either engine) are now stale
    for suffix in (".words.json", ".gigaam.words.json"):
        stale = output.with_suffix(output.suffix + suffix)
        if stale.exists():
            stale.unlink()
    save_review(source, output, data.get("pad_ms", 100), data["intervals"],
                beep_hz=data.get("beep_hz"))
