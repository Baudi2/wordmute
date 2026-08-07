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


def _is_media(p: Path) -> bool:
    return (p.suffix.lower() in MEDIA_EXTS
            and ".clean" not in p.suffixes
            and not p.stem.endswith(".clean"))


def expand_inputs(paths) -> list:
    """GUI-friendly variant of the engine's collect_inputs: expand files
    and directories into a list of media files (sorted within each dir,
    .clean outputs skipped), silently ignoring anything else."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(f for f in sorted(p.iterdir())
                         if f.is_file() and _is_media(f))
        elif p.is_file() and _is_media(p):
            files.append(p)
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
