#!/usr/bin/env python3
"""
wordmute engine — mute unwanted words/phrases in video or audio files.

Pipeline: ASR with word-level timestamps (faster-whisper or GigaAM)
          -> match against word list -> ffmpeg mutes matched intervals,
          video stream copied untouched.

The matching semantics (norm/load_wordlist/find_hits) are shared with the
author's standalone CLI and must not diverge from it — word lists are
curated against exactly these rules.

Word list format (one entry per line, UTF-8):
    слово          exact match (case-insensitive, ё=е)
    блядск*        stem match: any word starting with "блядск"
    *корен*        substring match: "корен" anywhere in the word
    какого хрена   phrase: consecutive words matched together
    # comment      lines starting with # are ignored

Console output goes through a swappable reporter (set_reporter) so a GUI
can receive structured progress events; the default reporter prints the
same lines the CLI always has.

First run per video is slow (transcription); results are cached in
<video>.words.json / <video>.gigaam.words.json, so re-runs with an edited
word list take seconds.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- reporting
def _default_reporter(event: str, d: dict) -> None:
    if event == "model_load":
        if d["engine"] == "whisper":
            print(f"[model] loading whisper {d['model']} on {d['device']} "
                  f"({d['compute']}) ...")
        else:
            print(f"[model] loading GigaAM {d['model']} on {d['device']} ...")
    elif event == "cache_hit":
        print(f"[cache] using existing {d['engine']} transcript: {d['cache']}")
    elif event == "cache_saved":
        print(f"[cache] transcript saved -> {d['cache']}")
    elif event == "asr_start":
        print(f"[asr]   transcribing {d['file']} with {d['engine']} "
              f"(first run is the slow part) ...")
    elif event == "asr_progress":
        print(f"\r[asr]   {d['minutes']:6.1f} min processed", end="", flush=True)
    elif event == "asr_progress_end":
        print()
    elif event == "words_count":
        print(f"[asr]   {d['count']} words in transcript")
    elif event == "pass_start":
        print(f"\n===== pass {d['n']}/{d['total']} ({d['engine']}) =====")
    elif event == "match_none":
        if d["pass_n"] == 1:
            print("[match] no unwanted words found — nothing to do.")
        else:
            print("[match] no unwanted words left — output is clean.")
    elif event == "force_continue":
        print("[force] --force-passes set: continuing anyway to "
              "reach the guaranteed-fresh final pass.")
    elif event == "match_found":
        print(f"[match] {len(d['intervals'])} interval(s):")
        for s, e, t in d["intervals"]:
            print(f"        {fmt_ts(s)} - {fmt_ts(e)}   {t}")
    elif event == "mute_start":
        print("[ffmpeg] muting", d["count"], "segment(s) ...")
    elif event == "mute_progress":
        print(f"\r[ffmpeg] {fmt_ts(d['seconds'])} rendered",
              end="", flush=True)
    elif event == "mute_done":
        print(f"\n[done]  -> {d['out']}")
    elif event == "list_info":
        print(f"[list]  {d['exact']} exact, {d['stems']} stems, "
              f"{d['subs']} substrings, {d['phrases']} phrases loaded")
    elif event == "plan":
        print(f"[plan]  {len(d['plan'])} pass(es): "
              + " -> ".join(f"{e}({m})" for e, m in d["plan"]))
    elif event == "batch_count":
        print(f"[batch] {d['count']} file(s) to process")
    elif event == "file_start":
        print(f"\n########## [{d['n']}/{d['total']}] {d['name']} ##########")
    elif event == "interrupted":
        print("\n[batch] interrupted by user")
    elif event == "file_error":
        print(f"[error] {d['name']}: {d['error']}")
    elif event == "batch_done":
        print(f"\n[batch] finished: {d['done']}/{d['total']} ok"
              + (f", failed: {', '.join(d['failed'])}" if d["failed"] else ""))


_reporter = _default_reporter


def set_reporter(fn) -> None:
    """Replace console output with a callback fn(event: str, data: dict).
    Pass None to restore the default CLI printer."""
    global _reporter
    _reporter = fn if fn is not None else _default_reporter


def _emit(event: str, **data) -> None:
    _reporter(event, data)


# ---------------------------------------------------------------- CUDA DLLs
def add_cuda_dll_dirs():
    """On Windows, make cuBLAS/cuDNN DLLs visible — from pip packages
    in a normal install, or from the bundle in a frozen app (where
    site-packages doesn't exist)."""
    if os.name != "nt":
        return
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
    else:
        import site
        roots.extend(map(Path, site.getsitepackages()
                         + [site.getusersitepackages()]))
    # app-managed runtime environment (slim installer) — the GUI sets
    # this seam so the engine stays standalone
    runtime_site = os.environ.get("WORDMUTE_RUNTIME_SITE")
    if runtime_site:
        roots.append(Path(runtime_site))
    candidates = []
    for root in roots:
        for sub in (r"nvidia\cublas\bin", r"nvidia\cudnn\bin"):
            candidates.append(root / sub)
    for p in candidates:
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")


# Windows: GigaAM's longform pipeline (via pyannote/torchcodec) needs
# FFmpeg's SHARED build (separate DLLs), not the static winget default.
# Having it on the system PATH isn't always enough - Python's own DLL
# loader needs the directory registered explicitly, same story as CUDA
# above. The directory is discovered at runtime (winget locations, then
# PATH); the app can override with configure_ffmpeg_shared_dir().
FFMPEG_SHARED_BIN = None
_ffmpeg_dll_dir_registered = False


def configure_ffmpeg_shared_dir(path) -> None:
    """Explicitly set the FFmpeg shared-build bin directory (e.g. from an
    installer-written config), overriding automatic discovery."""
    global FFMPEG_SHARED_BIN, _ffmpeg_dll_dir_registered
    FFMPEG_SHARED_BIN = str(path) if path else None
    _ffmpeg_dll_dir_registered = False


def _has_shared_dlls(p: Path) -> bool:
    return p.is_dir() and any(p.glob("avcodec-*.dll"))


def discover_ffmpeg_shared_dir():
    """Search likely install locations for FFmpeg's shared-build DLLs:
    winget package folders (per-user and machine-wide), then PATH."""
    if os.name != "nt":
        return None
    roots = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Microsoft" / "WinGet" / "Packages")
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        pf = os.environ.get(env)
        if pf:
            roots.append(Path(pf) / "WinGet" / "Packages")
    candidates = []
    for root in roots:
        if not root.is_dir():
            continue
        for pkg in sorted(root.glob("Gyan.FFmpeg.Shared*"), reverse=True):
            candidates.extend(sorted(pkg.glob("ffmpeg-*shared/bin"), reverse=True))
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            candidates.append(Path(entry))
    for c in candidates:
        if _has_shared_dlls(c):
            return str(c)
    return None


def add_ffmpeg_shared_dll_dir():
    global _ffmpeg_dll_dir_registered, FFMPEG_SHARED_BIN
    if _ffmpeg_dll_dir_registered or os.name != "nt":
        return
    if FFMPEG_SHARED_BIN is None:
        FFMPEG_SHARED_BIN = discover_ffmpeg_shared_dir()
    if FFMPEG_SHARED_BIN and os.path.isdir(FFMPEG_SHARED_BIN):
        os.add_dll_directory(FFMPEG_SHARED_BIN)
        os.environ["PATH"] = FFMPEG_SHARED_BIN + os.pathsep + os.environ.get("PATH", "")
    _ffmpeg_dll_dir_registered = True


# ---------------------------------------------------------------- word list
def norm(word: str) -> str:
    """lowercase, ё->е, strip punctuation."""
    w = word.lower().replace("ё", "е")
    return re.sub(r"[^\w-]", "", w)


def load_wordlist(path: Path):
    return parse_wordlist_lines(
        path.read_text(encoding="utf-8").splitlines())


def parse_wordlist_lines(lines):
    exact, stems, phrases, subs = set(), [], [], []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.lower().replace("ё", "е")
        if " " in line:
            phrases.append(tuple(norm(w) for w in line.split()))
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            subs.append(norm(line[1:-1]))
        elif line.endswith("*"):
            stems.append(norm(line[:-1]))
        else:
            exact.add(norm(line))
    return exact, stems, phrases, subs


# ---------------------------------------------------------------- transcribe
_MODELS = {}         # (name, device) -> faster-whisper model, reused across passes
_GIGAAM_MODELS = {}  # model_name -> loaded GigaAM model, reused across passes


def get_whisper_model(model_name: str, device: str):
    key = (model_name, device)
    if key not in _MODELS:
        add_cuda_dll_dirs()
        from faster_whisper import WhisperModel
        # int8_float16: ~35% less VRAM than float16, same-or-faster
        # decode; CT2 falls back automatically on GPUs without int8
        compute = "int8_float16" if device == "cuda" else "int8"
        _emit("model_load", engine="whisper", model=model_name, device=device,
              compute=compute)
        _MODELS[key] = WhisperModel(model_name, device=device, compute_type=compute)
    return _MODELS[key]


def get_gigaam_model(model_name: str, device: str):
    if model_name not in _GIGAAM_MODELS:
        # Hugging Face's Xet storage backend produces lock-file paths with
        # characters illegal in Windows filenames (WinError 123)
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        add_ffmpeg_shared_dll_dir()
        import gigaam
        _emit("model_load", engine="gigaam", model=model_name, device=device)
        _GIGAAM_MODELS[model_name] = gigaam.load_model(model_name, device=device)
    return _GIGAAM_MODELS[model_name]


# GigaAM backend: "torch" = the original gigaam package (GPU-capable,
# needs pyannote + an HF token for longform); "onnx" = onnx-asr on
# onnxruntime — fast on plain CPU (~43-59x realtime), ~850 MB model,
# silero VAD, no Hugging Face account. Word output format identical.
GIGAAM_BACKEND = "torch"
_GIGAAM_ONNX = {}


def configure_gigaam_backend(name: str) -> None:
    global GIGAAM_BACKEND
    GIGAAM_BACKEND = name


def _gigaam_onnx_pipeline(model_name: str):
    if model_name not in _GIGAAM_ONNX:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        import onnx_asr
        onnx_name = "gigaam-" + model_name.replace("_", "-")
        _emit("model_load", engine="gigaam", model=model_name,
              device="cpu (onnx-asr)")
        _GIGAAM_ONNX[model_name] = (
            onnx_asr.load_model(onnx_name)
            .with_vad(onnx_asr.load_vad("silero"))
            .with_timestamps())
    return _GIGAAM_ONNX[model_name]


def _chars_to_words(tokens, times, offset: float):
    """Fold onnx-asr tokens into word dicts (times are RELATIVE to the
    VAD segment; a word's end gets one ~80 ms emission frame of pad).

    Two token shapes exist and BOTH must split into single words:
      * character-level (v3 ctc/rnnt): 'с','е',' ','м','ы' — a bare
        space token separates words;
      * SentencePiece subwords (the *_e2e_* models): ' Замен','ят',
        ' ли','?' — a LEADING space (or a raw '▁') starts a new word,
        punctuation attaches to the word before it.
    Getting this wrong once cost whole muted sentences: without the
    subword case every e2e segment folded into ONE 10-second 'word'."""
    words, cur = [], []
    start = end = 0.0

    def flush():
        text = "".join(cur).strip()
        if text:
            words.append({"w": text, "s": round(offset + start, 3),
                          "e": round(offset + end + 0.08, 3)})
        cur.clear()

    for tok, t in zip(tokens, times):
        if not tok:
            continue
        if tok.startswith((" ", "▁")) or not tok.strip():
            flush()                      # word boundary
        piece = tok.replace("▁", " ").strip()
        if not piece:
            continue
        if not cur:
            start = t
        cur.append(piece)
        end = t
    flush()
    return words


def _transcribe_gigaam_onnx(media: Path, model_name: str):
    pipe = _gigaam_onnx_pipeline(model_name)
    # onnx-asr reads WAV/numpy only — extract 16 kHz mono via ffmpeg
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(media),
                            "-vn", "-ac", "1", "-ar", "16000", tmp],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("ffmpeg audio extraction failed: "
                               + (r.stderr or "")[-300:])
        words = []
        for seg in pipe.recognize(tmp):
            words.extend(_chars_to_words(seg.tokens, seg.timestamps,
                                         seg.start))
            _emit("asr_progress", minutes=seg.end / 60)
        return words
    finally:
        os.unlink(tmp)


def _cache_path(media: Path, engine: str) -> Path:
    # whisper keeps the original untagged cache name for backward
    # compatibility with transcripts cached before GigaAM support existed.
    if engine == "whisper":
        return media.with_suffix(media.suffix + ".words.json")
    return media.with_suffix(media.suffix + f".{engine}.words.json")


FAST_MODE = False


def configure_fast_mode(on: bool) -> None:
    """Opt-in batched whisper decoding: ~2-4x faster on GPU, ~2.4x on
    CPU (at ~2x RAM), slightly higher miss risk (chunks lose cross-
    context). Requires VAD — the no-VAD path stays sequential."""
    global FAST_MODE
    FAST_MODE = bool(on)


def transcribe(media: Path, engine: str, model_name: str, device: str, language: str,
               force: bool = False, vad: bool = True):
    cache = _cache_path(media, engine)
    if cache.exists() and not force:
        _emit("cache_hit", engine=engine, cache=cache.name)
        return json.loads(cache.read_text(encoding="utf-8"))

    _emit("asr_start", file=media.name, engine=engine)

    if engine == "whisper":
        model = get_whisper_model(model_name, device)
        if FAST_MODE and vad:
            from faster_whisper import BatchedInferencePipeline
            segments, info = BatchedInferencePipeline(model=model).transcribe(
                str(media), language=language, word_timestamps=True,
                vad_filter=True, batch_size=8 if device == "cuda" else 4,
            )
        else:
            segments, info = model.transcribe(
                str(media), language=language, word_timestamps=True,
                vad_filter=vad,
            )
        words = []
        for seg in segments:
            for w in seg.words or []:
                words.append({"w": w.word.strip(), "s": round(w.start, 3),
                              "e": round(w.end, 3)})
            _emit("asr_progress", minutes=seg.end / 60)

    elif engine == "gigaam":
        if GIGAAM_BACKEND == "onnx":
            words = _transcribe_gigaam_onnx(media, model_name)
        else:
            model = get_gigaam_model(model_name, device)
            result = model.transcribe_longform(str(media), word_timestamps=True)
            words = [{"w": w.text.strip(), "s": round(w.start, 3),
                      "e": round(w.end, 3)} for w in result.words]

    else:
        raise ValueError(f"unknown engine: {engine!r} (use 'whisper' or 'gigaam')")

    # closes the pass for the stage-timing report (all engines)
    _emit("asr_progress_end")

    cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    _emit("cache_saved", cache=cache.name)
    return words


# ---------------------------------------------------------------- matching
def find_hits(words, exact, stems, phrases, subs, pad_ms):
    normed = [norm(x["w"]) for x in words]
    pad = pad_ms / 1000.0
    idx_hits = []  # (first_word_idx, last_word_idx)

    # fast lookups that stay O(1)-ish regardless of list size
    stem_set = set(stems)
    max_stem = max(map(len, stems), default=0)
    sub_re = (re.compile("|".join(re.escape(s) for s in
                                  sorted(subs, key=len, reverse=True)))
              if subs else None)
    ph_by_first = {}
    for ph in phrases:
        ph_by_first.setdefault(ph[0], []).append(ph)

    def is_bad(nw: str) -> bool:
        if nw in exact:
            return True
        for L in range(1, min(len(nw), max_stem) + 1):
            if nw[:L] in stem_set:
                return True
        return bool(sub_re and sub_re.search(nw))

    for i, nw in enumerate(normed):
        if not nw:
            continue
        if is_bad(nw):
            idx_hits.append((i, i))
        for ph in ph_by_first.get(nw, ()):
            n = len(ph)
            if i + n <= len(normed) and tuple(normed[i:i + n]) == ph:
                idx_hits.append((i, i + n - 1))

    # neighbor-aware padding: never mute into the previous/next word
    hits = []
    for a, b in sorted(set(idx_hits)):
        s, e = words[a]["s"], words[b]["e"]
        prev_end = words[a - 1]["e"] if a > 0 else 0.0
        next_start = words[b + 1]["s"] if b + 1 < len(words) else e + pad
        s2 = min(max(s - pad, prev_end, 0.0), s)
        e2 = max(min(e + pad, next_start), e)
        text = " ".join(words[j]["w"] for j in range(a, b + 1))
        hits.append((s2, e2, text))

    # merge overlapping intervals
    merged = []
    for s, e, t in sorted(hits):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e),
                          merged[-1][2] + " | " + t)
        else:
            merged.append((s, e, t))
    return merged


# ---------------------------------------------------------------- ffmpeg
def _creationflags() -> int:
    """Suppress child console windows when we have no console ourselves
    (GUI app); keeps normal behavior when run from a terminal."""
    if os.name != "nt":
        return 0
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            return subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    return 0


def _run_ffmpeg_with_progress(cmd) -> None:
    """Run ffmpeg reading its -progress output, emitting mute_progress
    events; raises RuntimeError with the stderr tail on failure."""
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                text=True, encoding="utf-8",
                                errors="replace",
                                creationflags=_creationflags())
        try:
            for line in proc.stdout:
                if line.startswith("out_time="):
                    try:
                        h, m, s = line.strip().split("=", 1)[1].split(":")
                        _emit("mute_progress",
                              seconds=int(h) * 3600 + int(m) * 60 + float(s))
                    except ValueError:
                        continue  # "out_time=N/A" etc.
            proc.wait()
        except BaseException:
            # a cancel raised from the reporter (or Ctrl+C) must not
            # leave ffmpeg writing the output in the background: the
            # orphan kept running to completion and a restarted run
            # then wrote the same .tmp file under it
            proc.kill()
            proc.wait()
            raise
        if proc.returncode:
            errf.seek(0)
            tail = errf.read()[-2000:].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ffmpeg failed (code {proc.returncode}): {tail.strip()}")


FADE_S = 0.04  # linear ramp at each mute edge — hard cuts sound like clicks


def _fade_silence_filter(s: float, e: float) -> str:
    """Volume envelope: ramp down over FADE_S before the interval,
    silence inside, ramp back up after. Ramps sit OUTSIDE the already
    pad_ms-padded interval, so no muted word leaks; chained filters
    multiply, so close neighbors combine safely."""
    s0 = max(0.0, s - FADE_S)
    return (f"volume=enable='between(t,{s0:.3f},{e + FADE_S:.3f})'"
            f":volume='if(lt(t,{s:.3f}),({s:.3f}-t)/{FADE_S},"
            f"if(gt(t,{e:.3f}),(t-{e:.3f})/{FADE_S},0))'"
            f":eval=frame")


def _silence_filters(intervals) -> str:
    # volume expressions evaluate once per audio FRAME; default frames
    # (~1024 samples) are longer than the whole ramp, so split them to
    # 256 samples (~5 ms at 48 kHz) or the fade quantizes away
    return "asetnsamples=n=256," + ",".join(
        _fade_silence_filter(s, e) for s, e, _ in intervals
    )


def _beep_filtergraph(intervals, beep_hz: int) -> str:
    """Replace matched intervals with a beep tone: the original audio is
    silenced there while a sine tone (silenced everywhere else) is mixed
    in. amix halves levels, the trailing volume=2 restores them."""
    gate = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e, _ in intervals)
    return (f"[0:a]{_silence_filters(intervals)}[muted];"
            f"sine=frequency={beep_hz}[tone];"
            f"[tone]volume=enable='not({gate})':volume=0,volume=0.25[beep];"
            f"[muted][beep]amix=inputs=2:duration=first:"
            f"dropout_transition=0,volume=2[aout]")


# the muted audio must be re-encoded in a codec its container accepts —
# WebM refuses AAC outright (only Opus/Vorbis), lossless stays lossless
_AUDIO_CODEC_FOR = {
    ".webm": ["-c:a", "libopus", "-b:a", "160k"],
    ".opus": ["-c:a", "libopus", "-b:a", "160k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "6"],
    ".flac": ["-c:a", "flac"],
    ".wav": ["-c:a", "pcm_s16le"],
    # the mp3 muxer takes exactly one MP3 stream — AAC made every .mp3
    # input fail at the mute stage («Invalid audio stream», code -22)
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
}
_AUDIO_CODEC_DEFAULT = ["-c:a", "aac", "-b:a", "192k"]


def _audio_codec_args(out: Path) -> list:
    return _AUDIO_CODEC_FOR.get(out.suffix.lower(), _AUDIO_CODEC_DEFAULT)


def mute(media: Path, intervals, out: Path, beep_hz=None):
    filters = (_beep_filtergraph(intervals, beep_hz) if beep_hz
               else _silence_filters(intervals))
    # filter list can be huge -> pass via script file (avoids cmd length limits)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(filters)
        script = f.name
    audio_args = _audio_codec_args(out)
    if beep_hz:
        # a filter_complex graph needs explicit maps; secondary audio
        # tracks are not carried over in beep mode
        io_args = [
            "-filter_complex_script", script,
            "-map", "0:v?", "-map", "[aout]", "-map", "0:s?",
            "-c:v", "copy", "-c:s", "copy",
            *audio_args,
        ]
    else:
        io_args = [
            "-map", "0",
            "-c", "copy",
            *audio_args,
            "-filter_script:a", script,
        ]
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-progress", "pipe:1",
        "-err_detect", "ignore_err",
        "-fflags", "+genpts+igndts+discardcorrupt",
        "-i", str(media),
        *io_args,
        str(out),
    ]
    _emit("mute_start", count=len(intervals))
    try:
        _run_ffmpeg_with_progress(cmd)
    finally:
        os.unlink(script)
    _emit("mute_done", out=str(out))


def fmt_ts(t):
    m, s = divmod(t, 60)
    h, m = divmod(int(m), 60)
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ---------------------------------------------------------------- main
MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts", ".wmv",
              ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"}


def collect_inputs(paths):
    """Expand files and directories into a sorted list of media files."""
    files = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if (f.suffix.lower() in MEDIA_EXTS
                        and ".clean" not in f.suffixes
                        and not f.stem.endswith(".clean")):
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"input not found: {p}")
    if not files:
        sys.exit("no media files found in the given input(s)")
    return files


def output_for(inp: Path, out_arg, multi: bool) -> Path:
    if out_arg is None:
        return inp.with_suffix(".clean" + inp.suffix)
    if out_arg.is_dir() or multi:
        out_arg.mkdir(parents=True, exist_ok=True)
        return out_arg / (inp.stem + ".clean" + inp.suffix)
    return out_arg  # single input, explicit file path


def drop_output_caches(out: Path) -> None:
    """Passes 2+ transcribe the OUTPUT, which writes a cache next to it.
    That cache describes an intermediate state nothing ever reads again,
    so it must not outlive the run — a final pass that finds nothing
    used to leave a stray <out>.words.json sitting next to the video."""
    for suffix in (".words.json", ".gigaam.words.json"):
        stale = out.with_suffix(out.suffix + suffix)
        if stale.exists():
            stale.unlink()


def process_file(inp: Path, out: Path, wordlist, args, plan) -> None:
    """plan: list of (engine, model_name) tuples, one entry per pass."""
    try:
        _run_passes(inp, out, wordlist, args, plan)
    finally:
        drop_output_caches(out)


def _run_passes(inp: Path, out: Path, wordlist, args, plan) -> None:
    exact, stems, phrases, subs = wordlist
    current = inp
    n_passes = len(plan)

    for pass_n, (engine, model_name) in enumerate(plan, start=1):
        if n_passes > 1:
            _emit("pass_start", n=pass_n, total=n_passes, engine=engine)

        is_last = (pass_n == n_passes)
        force_this = ((args.retranscribe and pass_n == 1)
                      or (args.force_passes and is_last))

        words = transcribe(current, engine, model_name, args.device, args.language,
                           force=force_this, vad=not args.no_vad)
        _emit("words_count", count=len(words))

        intervals = find_hits(words, exact, stems, phrases, subs, args.pad)
        if not intervals:
            _emit("match_none", pass_n=pass_n)
            if args.force_passes and not is_last:
                _emit("force_continue")
                continue
            break

        _emit("match_found", intervals=intervals)

        if args.list_only:
            break

        tmp = out.parent / (out.stem + ".tmp" + out.suffix)
        try:
            mute(current, intervals, tmp,
                 beep_hz=getattr(args, "beep_hz", None))
            os.replace(tmp, out)
        except BaseException:
            # cancel or ffmpeg failure: never leave a half-written
            # «name.clean.tmp.mp4» next to the video
            tmp.unlink(missing_ok=True)
            raise
        # any cached transcript (from either engine) for the previous
        # version of the output is now stale
        drop_output_caches(out)
        current = out


def main():
    ap = argparse.ArgumentParser(description="Mute unwanted words in media files.")
    ap.add_argument("-i", "--input", required=True, type=Path, nargs="+",
                    help="one or more video/audio files and/or directories "
                         "(directories are scanned for media files)")
    ap.add_argument("-w", "--words", required=True, type=Path)
    ap.add_argument("-o", "--output", type=Path,
                    help="output file (single input) or output directory; "
                         "default: <input>.clean.<ext> next to each input")
    ap.add_argument("--model", default="large-v3",
                    help="faster-whisper model for 'whisper' passes "
                         "(large-v3, medium, small...)")
    ap.add_argument("--gigaam-model", default="v3_e2e_rnnt",
                    help="GigaAM model for 'gigaam' passes "
                         "(v3_e2e_rnnt, v3_e2e_ctc, v3_rnnt, v3_ctc...)")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--language", default="ru",
                    help="whisper language code; ignored for gigaam passes")
    ap.add_argument("--pad", type=int, default=100,
                    help="padding in ms around each muted word (default 100)")
    ap.add_argument("--beep-hz", type=int, default=None,
                    help="replace muted words with a beep tone of this "
                         "frequency (e.g. 1000) instead of silence; "
                         "note: beep mode keeps only the first audio track")
    ap.add_argument("--list-only", action="store_true",
                    help="print timestamps, don't produce files")
    ap.add_argument("--retranscribe", action="store_true",
                    help="ignore cached transcripts")
    ap.add_argument("--no-vad", action="store_true",
                    help="disable voice activity detection for whisper passes "
                         "(try with --retranscribe if words at clip edges "
                         "are missed); has no effect on gigaam passes")
    ap.add_argument("--fast", action="store_true",
                    help="batched whisper decoding: ~2-4x faster, slightly "
                         "higher chance of missed words (chunks lose "
                         "cross-context) and ~2x RAM on CPU; ignored "
                         "with --no-vad")
    ap.add_argument("--gigaam-backend", choices=["torch", "onnx"],
                    default="torch",
                    help="onnx = onnx-asr runtime: fast on plain CPU, "
                         "~850 MB model, no HF token (pip install "
                         "onnx-asr[cpu,hub]); torch = original gigaam "
                         "package (GPU-capable)")
    ap.add_argument("--passes", type=int, default=2,
                    help="number of whisper passes; ignored if --engines is "
                         "given. Each extra pass re-transcribes the cleaned "
                         "output to catch words missed the first time "
                         "(default 2, stops early when clean)")
    ap.add_argument("--engines", type=str, default=None,
                    help="comma-separated engine sequence, one entry per "
                         "pass, e.g. 'gigaam,gigaam,whisper' for two GigaAM "
                         "passes followed by one whisper pass as a second "
                         "opinion. Overrides --passes. Valid engines: "
                         "'whisper', 'gigaam'.")
    ap.add_argument("--force-passes", action="store_true",
                    help="always run the full pass count, even if an "
                         "earlier pass finds nothing new to mute. The final "
                         "pass is also forced to ignore any cache and "
                         "re-transcribe completely fresh. Use this for e.g. "
                         "--engines gigaam,gigaam,whisper --force-passes: "
                         "passes 1-2 behave normally, pass 3 is guaranteed "
                         "to run with a brand-new transcription.")
    args = ap.parse_args()
    configure_fast_mode(args.fast)
    configure_gigaam_backend(args.gigaam_backend)

    if args.engines:
        engine_names = [e.strip().lower() for e in args.engines.split(",") if e.strip()]
        for e in engine_names:
            if e not in ("whisper", "gigaam"):
                sys.exit(f"unknown engine in --engines: {e!r} "
                          f"(valid: 'whisper', 'gigaam')")
        model_for = {"whisper": args.model, "gigaam": args.gigaam_model}
        plan = [(e, model_for[e]) for e in engine_names]
    else:
        plan = [("whisper", args.model)] * args.passes

    files = collect_inputs(args.input)
    wordlist = load_wordlist(args.words)
    exact, stems, phrases, subs = wordlist
    _emit("list_info", exact=len(exact), stems=len(stems),
          subs=len(subs), phrases=len(phrases))
    _emit("plan", plan=plan)
    if len(files) > 1:
        _emit("batch_count", count=len(files))

    failed = []
    for n, inp in enumerate(files, 1):
        if len(files) > 1:
            _emit("file_start", n=n, total=len(files), name=inp.name)
        out = output_for(inp, args.output, multi=len(files) > 1)
        try:
            process_file(inp, out, wordlist, args, plan)
        except KeyboardInterrupt:
            _emit("interrupted")
            break
        except Exception as exc:
            _emit("file_error", name=inp.name, error=str(exc))
            failed.append(inp.name)

    if len(files) > 1:
        done = len(files) - len(failed)
        _emit("batch_done", done=done, total=len(files), failed=failed)


if __name__ == "__main__":
    main()
