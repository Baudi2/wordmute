"""Review data: what was muted, where, by which pass — and re-rendering
after the user un-mutes false positives.

A review sidecar (<output>.wordmute.json) is written after each
successful job. Muting never alters the timeline (volume filter, no
cutting), so intervals from every pass share the source file's
timestamps; re-rendering is therefore ONE ffmpeg mute of the original
source with the still-muted intervals — no re-transcription ever.

All times are on the FILE clock (engine.extract_asr_wav). Version 1
sidecars counted from the first audio sample; migrate_clock() moves
them over once, when the Review window opens them."""

import json
import os
import shutil
import threading
from pathlib import Path

from . import config, probe
from ..engine import wordmute as engine

REVIEW_SUFFIX = ".wordmute.json"
REVIEW_VERSION = 2   # 2 = file-clock times

# Passes 2+ transcribe the ALREADY-MUTED output. Word timestamps are a
# little off, so a sliver of the word survives the first mute (or the
# model fills the silence from context) and the next pass catches the
# same word again — tens of ms apart, never identical: 08:21.393,
# 08:21.433, 08:21.240. Each pass muted its own interval on top of the
# previous output, so the file carries their UNION. The review lists
# that union once; a separate row per catch doubled the list, and
# unchecking one copy un-muted nothing while the others stayed checked.
SAME_WORD_GAP_S = 0.3   # same word, different pass, not quite touching


def _norm_text(text: str) -> str:
    return " ".join(w for w in (engine.norm(t) for t in text.split()) if w)


def _passes(iv) -> list:
    return list(iv.get("passes") or [iv.get("pass", 1)])


def _engines(iv) -> list:
    return [e for e in (iv.get("engines") or [iv.get("engine", "")]) if e]


def _variants(members) -> set:
    return {_norm_text(v) for m in members for v in m["text"].split(" / ")}


def _same_spot(members, iv) -> bool:
    end = max(m["e"] for m in members)
    if iv["s"] <= end:
        return True                     # overlapping = the same audio
    # a small gap only for the same word caught by ANOTHER pass: two
    # «боже» said 0.2 s apart in one pass stay two rows
    passes = {p for m in members for p in _passes(m)}
    return (iv["s"] - end <= SAME_WORD_GAP_S
            and passes.isdisjoint(_passes(iv))
            and not _variants(members).isdisjoint(_variants([iv])))


def _combine(members) -> dict:
    if len(members) == 1:
        return dict(members[0])
    # the earliest pass names the row: «повезло», not whisper's
    # «повезло.»; a word another engine heard differently is kept
    ordered = sorted(members, key=lambda m: (min(_passes(m)), m["s"]))
    texts, seen = [], set()
    for m in ordered:
        for variant in m["text"].split(" / "):
            key = _norm_text(variant)
            if key not in seen:
                seen.add(key)
                texts.append(variant)
    passes = sorted({p for m in members for p in _passes(m)})
    engines = []
    for m in ordered:
        for name in _engines(m):
            if name not in engines:
                engines.append(name)
    record = dict(ordered[0])
    record.update({
        "s": min(m["s"] for m in members),
        "e": max(m["e"] for m in members),
        "text": " / ".join(texts),
        "pass": passes[0],
        "engine": engines[0] if engines else record.get("engine", ""),
        # muted if ANY copy still mutes — that is what the output holds;
        # a family filter errs on the muted side
        "muted": any(m.get("muted", True) for m in members),
    })
    record.pop("passes", None)
    record.pop("engines", None)
    if len(passes) > 1:
        record["passes"] = passes
    if len(engines) > 1:
        record["engines"] = engines
    return record


def merge_intervals(intervals) -> list:
    """One record per muted spot, in time order (see SAME_WORD_GAP_S)."""
    clusters = []
    for iv in sorted(intervals, key=lambda r: (r["s"], r["e"])):
        if clusters and _same_spot(clusters[-1], iv):
            clusters[-1].append(iv)
        else:
            clusters.append([iv])
    return [_combine(c) for c in clusters]


def review_path_for(output) -> Path:
    output = Path(output)
    return output.with_suffix(output.suffix + REVIEW_SUFFIX)


def save_review(source, output, pad_ms: int, intervals: list,
                beep_hz=None, version: int = REVIEW_VERSION) -> Path:
    """intervals: [{"s", "e", "text", "pass", "engine", "muted"}, ...]"""
    path = review_path_for(output)
    data = {
        "version": version,
        "source": str(source),
        "output": str(output),
        "pad_ms": pad_ms,
        "beep_hz": beep_hz,
        "intervals": intervals,
    }
    config.write_text_atomic(path, json.dumps(data, ensure_ascii=False,
                                              indent=1))
    return path


def load_review(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
            k in data for k in ("source", "output", "intervals")):
        raise ValueError("not a WordMute review file")
    # sidecars written before 0.7.2 carry one row per catch; merged in
    # memory only — the file changes on the next re-render
    data["intervals"] = merge_intervals(data["intervals"])
    return data


def migrate_clock(data: dict):
    """Version-1 sidecars were saved while the ASR counted time from the
    first decoded audio sample: on files whose audio starts after the
    video every row sits that much early, and a re-render muted before
    the word. Shift the rows once onto the file clock by where mute()
    sees the source's first audio sample. Returns the shift applied, or
    None (already version 2, source missing, probe failed).

    Kept out of load_review on purpose: cleanup.resolve_source reads
    sidecars from the delete flows and must not spawn ffmpeg.
    merge_intervals uses only order and differences, so shifting after
    load_review's merge is exact. A row first caught by pass k was
    transcribed from an output re-encoded k-1 times — each re-encode
    starts ~23 ms earlier — so it lands up to (k-1) x 23 ms late,
    inside the 100 ms pad."""
    if data.get("version", 1) >= REVIEW_VERSION:
        return None
    source = Path(data["source"])
    if not source.exists():
        return None
    offset = probe.audio_start_offset(source)
    if offset is None:
        return None
    offset = round(offset, 6)
    for iv in data["intervals"]:
        iv["s"] = round(iv["s"] + offset, 3)
        iv["e"] = round(iv["e"] + offset, 3)
    data["version"] = REVIEW_VERSION
    return offset


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
    # a per-process/thread name: two review dialogs for the same file
    # (double-click + the Review button) could re-render into one .tmp
    tmp = output.parent / (
        f"{output.stem}.tmp-{os.getpid()}-{threading.get_ident()}"
        f"{output.suffix}")
    try:
        if muted:
            engine.mute(source, muted, tmp,
                        beep_hz=data.get("beep_hz") or None)
        else:
            shutil.copyfile(source, tmp)
        os.replace(tmp, output)
    except BaseException:
        tmp.unlink(missing_ok=True)   # no half-written .tmp left behind
        raise
    engine.drop_output_caches(output)   # they describe the old output
    # a version-1 sidecar the Review window could not migrate stays
    # version 1: it must never claim file-clock times it does not have
    save_review(source, output, data.get("pad_ms", 100), data["intervals"],
                beep_hz=data.get("beep_hz"),
                version=data.get("version", 1))
