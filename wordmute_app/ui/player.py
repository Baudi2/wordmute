"""Audio snippet playback for the review screen.

ffmpeg extracts the interval (plus context) to a temp wav, winsound
plays it asynchronously — works for every container/codec the pipeline
accepts, unlike relying on the system's media codecs directly."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CONTEXT_SEC = 0.7


class SnippetPlayer:
    def __init__(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="wordmute_play_"))
        self._count = 0

    def play(self, media, start: float, end: float) -> None:
        self.stop()
        self._count += 1
        wav = self._tmpdir / f"snippet_{self._count}.wav"
        begin = max(0.0, start - CONTEXT_SEC)
        duration = (end - start) + (start - begin) + CONTEXT_SEC
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{begin:.3f}", "-i", str(media),
            "-t", f"{duration:.3f}", "-vn", "-ac", "2", "-ar", "44100",
            str(wav),
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not wav.exists():
            detail = r.stderr.decode(errors="replace").strip()[:200]
            raise RuntimeError(detail or "ffmpeg could not extract snippet")
        if os.name == "nt":
            import winsound
            winsound.PlaySound(str(wav),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)

    def stop(self) -> None:
        if os.name == "nt":
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)

    def dispose(self) -> None:
        self.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
