"""Job option objects passed to the engine.

engine.process_file() reads argparse-style attributes off its `args`
parameter; JobOptions provides the same attribute names so the GUI can
call the engine without argparse."""

from dataclasses import dataclass, field
from pathlib import Path

from ..engine.wordmute import MEDIA_EXTS


@dataclass
class QueueItem:
    """One queue entry: either a local media file or a URL to download
    first and then process."""
    kind: str                          # "file" | "url"
    path: Path | None = None           # kind == "file"
    url: str = ""                      # kind == "url"
    format_spec: str = ""              # yt-dlp format selector
    format_label: str = "best quality"
    title: str = ""
    duration: float | None = None
    # per-item processing profile: "auto" follows the main setup;
    # "ru"/"en" force that language's word list, plan and ASR language
    lang_profile: str = "auto"

    @property
    def display_name(self) -> str:
        if self.kind == "file":
            return self.path.name
        return self.title or self.url


@dataclass
class JobOptions:
    device: str = "cuda"
    language: str = "ru"
    pad: int = 100
    list_only: bool = False
    retranscribe: bool = False
    force_passes: bool = False
    no_vad: bool = False
    beep_hz: int | None = None  # None/0 = mute with silence


def is_clean_output(p: Path) -> bool:
    """«name.clean.mp4» — a result of an earlier run, never an input."""
    return (p.suffix.lower() in MEDIA_EXTS
            and (".clean" in p.suffixes or p.stem.endswith(".clean")))


def _is_media(p: Path) -> bool:
    return p.suffix.lower() in MEDIA_EXTS and not is_clean_output(p)


def expand_inputs(paths, skipped: dict = None) -> list:
    """GUI-friendly variant of the engine's collect_inputs: expand files
    and directories into a list of media files (sorted within each dir,
    .clean outputs skipped). `skipped`, when given, collects what was
    left out — {"clean": [...], "not_media": [...]} — so the UI can say
    so: a dropped .clean file used to vanish without a word and the
    user concluded the app «does not see» the video. A folder's other
    files are normal and are not reported; its .clean outputs are."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if not f.is_file():
                    continue
                if _is_media(f):
                    files.append(f)
                elif skipped is not None and is_clean_output(f):
                    skipped["clean"].append(f)
        elif p.is_file():
            if _is_media(p):
                files.append(p)
            elif skipped is not None:
                key = "clean" if is_clean_output(p) else "not_media"
                skipped[key].append(p)
    return files


def scan_watch_dir(folder, seen: dict) -> list:
    """One watch-folder poll. seen maps path -> [size, ready]; a file is
    returned once, on the first scan where its size stopped changing
    (so half-copied files are never picked up)."""
    folder = Path(folder)
    ready = []
    if not folder.is_dir():
        return ready
    for f in sorted(folder.iterdir()):
        if not (f.is_file() and _is_media(f)):
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue
        state = seen.get(str(f))
        if state is None:
            seen[str(f)] = [size, False]
        elif not state[1]:
            if state[0] == size:
                state[1] = True
                ready.append(f)
            else:
                state[0] = size
    return ready


def build_plan(engine_names, whisper_model: str, gigaam_model: str) -> list:
    """Turn a pass sequence of engine names into the engine's plan
    format: [(engine, model), ...]."""
    model_for = {"whisper": whisper_model, "gigaam": gigaam_model}
    return [(e, model_for[e]) for e in engine_names]
