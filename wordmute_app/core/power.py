"""Keep Windows awake — and at full speed — while a run is in progress.

Sleep: an overnight batch dies silently when the PC goes to sleep
mid-run. SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
tells Windows the system is in use; the DISPLAY may still turn off (we
don't pass ES_DISPLAY_REQUIRED — processing needs no screen). The
state is per-process-lifetime: it resets automatically if the app
exits or crashes, so a stuck "never sleeps" machine is impossible.

Speed: Windows «Power Throttling» (EcoQoS) parks a process that is
not in the foreground on the slow, efficient cores at low clocks —
on laptops by default. A user on one saw recognition and downloads
crawl while WordMute sat behind the browser, then leap ahead by
minutes the moment they clicked it. SetProcessInformation(
ProcessPowerThrottling) with the EXECUTION_SPEED bit in the control
mask and a clear state mask opts a process out («always high QoS»);
a clear control mask hands it back to the system. The children we
spawn (ffmpeg, GigaAM's own ffmpeg) start throttled again, so a
Popen patch applies the same to each child while a run is on."""

import ctypes
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
PROCESS_POWER_THROTTLING = 4            # PROCESS_INFORMATION_CLASS

_full_speed = False


def keep_awake(on: bool) -> None:
    """Prevent (True) or re-allow (False) system sleep."""
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        return
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))


class _ThrottlingState(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong),
                ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong)]


def full_speed_for(handle, on: bool) -> bool:
    """Opt the process behind `handle` out of power throttling (True)
    or hand it back to Windows (False). Returns whether the call
    succeeded — it can't on Windows 10 before 1709 or on a handle
    without PROCESS_SET_INFORMATION."""
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        return False
    state = _ThrottlingState(
        PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED if on else 0, 0)
    try:
        return bool(ctypes.windll.kernel32.SetProcessInformation(
            ctypes.c_void_p(int(handle)), PROCESS_POWER_THROTTLING,
            ctypes.byref(state), ctypes.sizeof(state)))
    except (AttributeError, OSError):
        return False


def throttling_state(handle=None):
    """(ControlMask, StateMask) Windows holds for the process — for
    tests and diagnostics. None when it can't be read."""
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        return None
    kernel32 = ctypes.windll.kernel32
    if handle is None:
        handle = kernel32.GetCurrentProcess()
    state = _ThrottlingState(PROCESS_POWER_THROTTLING_CURRENT_VERSION, 0, 0)
    try:
        ok = kernel32.GetProcessInformation(
            ctypes.c_void_p(int(handle)), PROCESS_POWER_THROTTLING,
            ctypes.byref(state), ctypes.sizeof(state))
    except (AttributeError, OSError):
        return None
    return (state.ControlMask, state.StateMask) if ok else None


def full_speed(on: bool) -> bool:
    """This process: full speed in the background (True) or the
    default, system-managed throttling (False). Children spawned
    while it is on get the same (see install_child_full_speed)."""
    global _full_speed
    _full_speed = on
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        return False
    return full_speed_for(ctypes.windll.kernel32.GetCurrentProcess(), on)


_child_patch_installed = False


def install_child_full_speed() -> None:
    """Patch Popen so a child started during a run is opted out of
    power throttling like its parent (ffmpeg's mute pass runs for
    minutes; GigaAM and yt-dlp spawn ffmpeg themselves)."""
    global _child_patch_installed
    if _child_patch_installed or sys.platform != "win32":
        return
    original_init = subprocess.Popen.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if _full_speed:
            handle = getattr(self, "_handle", None)
            if handle is not None:
                full_speed_for(handle, True)

    subprocess.Popen.__init__ = patched_init
    _child_patch_installed = True
