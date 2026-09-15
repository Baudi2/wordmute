"""Cached-transcript access and SRT export.

Works entirely from the transcript caches the engine writes next to
each media file (<media>.whisper.v2.words.json /
<media>.gigaam.v2.words.json) — never triggers transcription."""

import json
from pathlib import Path

from ..engine import wordmute as engine


class LegacyTranscriptError(FileNotFoundError):
    """Only a transcript cached by an older version exists: its times
    count from the first audio sample and run early on files whose audio
    starts after the video, so it is not shown."""


def load_transcript(media) -> tuple:
    """Return (words, engine_name) from the media file's cached
    transcript, preferring whisper's cache. Raises FileNotFoundError
    with a helpful message when no cache exists, LegacyTranscriptError
    when only an old-format one does."""
    media = Path(media)
    for engine_name in ("whisper", "gigaam"):
        cache = media.with_suffix(
            media.suffix + engine.CACHE_SUFFIX[engine_name])
        if cache.exists():
            return (json.loads(cache.read_text(encoding="utf-8")),
                    engine_name)
    if any(media.with_suffix(media.suffix + suffix).exists()
           for suffix in engine.LEGACY_CACHE_SUFFIXES):
        raise LegacyTranscriptError(
            f"the transcript next to {media.name} was made by an older "
            "version — process the file again to rebuild it")
    raise FileNotFoundError(
        f"no cached transcript next to {media.name} — process the file "
        "first (the cache appears after transcription)")


def srt_ts(t: float) -> str:
    ms = round(t * 1000)
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def group_words(words, max_gap=0.8, max_words=10, max_dur=5.0) -> list:
    """Group word entries into subtitle-sized blocks: a block breaks on
    a silence gap, a word-count cap, or a duration cap."""
    blocks = []
    current = []
    for w in words:
        if current:
            gap = w["s"] - current[-1]["e"]
            dur = w["e"] - current[0]["s"]
            if gap > max_gap or len(current) >= max_words or dur > max_dur:
                blocks.append(current)
                current = []
        current.append(w)
    if current:
        blocks.append(current)
    return blocks


def words_to_srt(words) -> str:
    blocks = [b for b in group_words(words)
              if " ".join(w["w"] for w in b).strip()]
    lines = []
    for i, block in enumerate(blocks, start=1):
        text = " ".join(w["w"] for w in block).strip()
        lines.append(f"{i}\n{srt_ts(block[0]['s'])} --> "
                     f"{srt_ts(block[-1]['e'])}\n{text}\n")
    return "\n".join(lines)


def export_srt(media, dest=None) -> Path:
    words, _ = load_transcript(media)
    dest = Path(dest) if dest else Path(media).with_suffix(".srt")
    dest.write_text(words_to_srt(words), encoding="utf-8")
    return dest
