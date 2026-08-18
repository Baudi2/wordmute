"""Freeing disk space after processing: delete the original/downloaded
video and the JSON files the app wrote around it — optionally the
clean output too. Files go to the Windows Recycle Bin (SHFileOperationW
with FOF_ALLOWUNDO), so a mis-click is recoverable."""

import ctypes
import sys
from pathlib import Path

from . import review

# transcript caches the engine writes next to a media file
CACHE_SUFFIXES = (".words.json", ".gigaam.words.json")


def resolve_source(output=None, fallback=None):
    """The review sidecar records the authoritative source path — it
    survives URL downloads, where the queue item itself has no local
    path. Fall back to a caller-known path (queue item / history)."""
    if output:
        sidecar = review.review_path_for(output)
        if sidecar.exists():
            try:
                return Path(review.load_review(sidecar)["source"])
            except (ValueError, OSError):
                pass
    return Path(fallback) if fallback else None


def related_files(source=None, output=None, include_output=False) -> list:
    """Every file the app knows around this video that exists right
    now: the source and its transcript caches, the review sidecar
    (useless once the source is gone) and any transcript cache left
    next to the OUTPUT — passes 2+ transcribe the output, and a run
    that ended on a pass with no matches could leave one behind.
    include_output adds the clean video itself.

    Safety rule: in keep-the-clean mode (include_output=False) the
    SOURCE is only listed when a clean copy actually exists on disk —
    when nothing was muted, no .clean file was written and the source
    is the user's only copy, so «удалить исходник» degrades to
    deleting just the JSON files. «Удалить все файлы» still removes
    everything."""
    files = []

    def add(path):
        if path:
            path = Path(path)
            if path.exists() and path not in files:
                files.append(path)

    if source:
        clean_exists = bool(output and Path(output).exists())
        if include_output or clean_exists:
            add(source)
        for suffix in CACHE_SUFFIXES:
            add(str(source) + suffix)
    if output:
        add(review.review_path_for(output))
        for suffix in CACHE_SUFFIXES:
            add(str(output) + suffix)
        if include_output:
            add(output)
    return files


# ------------------------------------------------------------ recycle bin
_FO_DELETE = 3
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def send_to_recycle_bin(paths) -> None:
    """Move files to the Recycle Bin. Raises OSError on failure."""
    if not paths:
        return
    if sys.platform != "win32":  # pragma: no cover — Windows-only app
        for p in paths:
            Path(p).unlink()
        return
    # double-null-terminated list: one trailing \0 here, ctypes adds
    # the final terminator
    joined = "\0".join(str(Path(p).resolve()) for p in paths) + "\0"
    op = _SHFILEOPSTRUCTW(
        None, _FO_DELETE, joined, None,
        _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI,
        0, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted:
        raise OSError(f"Recycle Bin move failed (code {code})")
