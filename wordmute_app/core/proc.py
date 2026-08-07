"""Subprocess plumbing for a windowed app.

When the app runs without a console (pythonw / frozen GUI), child
console programs (ffmpeg, ffprobe, nvidia-smi) would each flash their
own terminal window. CREATE_NO_WINDOW suppresses that — but only when
we actually have no console, so CLI usage keeps its normal output."""

import os
import subprocess


def creationflags() -> int:
    if os.name != "nt":
        return 0
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            return subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    return 0


_installed = False


def install_global_no_window() -> None:
    """Our own subprocess calls pass creationflags explicitly, but
    libraries (GigaAM/pyannote/torchcodec, yt-dlp merges) spawn ffmpeg
    and friends themselves and flash console windows under pythonw.
    Patch Popen so every child of this process is windowless too.
    No-op when a console exists (CLI runs keep normal behavior)."""
    global _installed
    if _installed:
        return
    flag = creationflags()
    if not flag:
        return
    original_init = subprocess.Popen.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | flag
        original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = patched_init
    _installed = True
