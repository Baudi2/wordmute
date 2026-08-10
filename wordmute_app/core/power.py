"""Keep Windows awake while a run is in progress.

An overnight batch dies silently when the PC goes to sleep mid-run.
SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) tells
Windows the system is in use; the DISPLAY may still turn off (we don't
pass ES_DISPLAY_REQUIRED — processing needs no screen). The state is
per-process-lifetime: it resets automatically if the app exits or
crashes, so a stuck "never sleeps" machine is impossible."""

import ctypes
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool) -> None:
    """Prevent (True) or re-allow (False) system sleep."""
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        return
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
