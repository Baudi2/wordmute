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
