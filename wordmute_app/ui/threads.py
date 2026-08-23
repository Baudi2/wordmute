"""Worker-thread lifetime, done once.

Every worker in the app emits its result as the last thing in run();
the slot receiving it runs on the GUI thread while the worker is still
unwinding. If that slot drops the last Python reference — the natural
`self._worker = None` — PySide deletes the QThread while Qt still
counts it as running and the process aborts on the spot:

    QThread: Destroyed while thread '' is still running

No traceback, no dialog, the window just vanishes (Windows exit code
0xC0000409). A tight loop of the old pattern reproduces it within ~20
iterations; in the wild it showed up once on «Проверить обновления».

start_thread() hands ownership to a Qt parent, so Python references
become plain references, and finished→deleteLater frees the object
once the thread has really stopped (QThread's destructor waits out the
finishing phase — the one documented-safe moment to delete it).

The same abort has a second door: a close-time wait that times out.
Model loading, a stalled download or an ffmpeg pass can outlive any
reasonable wait; if the owner window is then destroyed with the thread
still running, Qt aborts again. detach_thread() unparents such a
straggler and keeps it alive; main() gives the stragglers one more
chance at exit and hard-exits rather than let Qt tear them down.

Qt-only imports on purpose: the setup wizard uses this before the
engine packages exist."""

import time

from PySide6.QtCore import QObject, QThread

_DETACHED = []   # stragglers handed over by close paths (see above)


def start_thread(owner: QObject, thread: QThread) -> QThread:
    """Parent `thread` to `owner`, free it after it finishes, start it."""
    thread.setParent(owner)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


def wait_thread(thread, msecs: int = None) -> bool:
    """wait() on a worker started with start_thread — tolerating None
    and one Qt has already deleted (finished → deleteLater). Returns
    True when the thread is stopped (or was never there)."""
    if thread is None:
        return True
    try:
        if msecs is None:
            return bool(thread.wait())
        return bool(thread.wait(msecs))
    except RuntimeError:   # "Internal C++ object already deleted"
        return True


def detach_thread(thread) -> None:
    """A worker that ignored its cancel within the close-time budget must
    not die with its owner. Unparent it and keep it referenced until it
    really stops; shutdown_detached() collects it at exit."""
    if thread is None:
        return
    try:
        if not thread.isRunning():
            return
        thread.setParent(None)
    except RuntimeError:
        return
    _DETACHED.append(thread)


def shutdown_detached(msecs: int) -> bool:
    """Last call before the interpreter goes: wait up to `msecs` for
    every detached worker. False means something is still running and
    the caller should exit without Qt's teardown (os._exit)."""
    deadline = time.monotonic() + msecs / 1000
    stopped = True
    for thread in list(_DETACHED):
        remaining = max(0, int((deadline - time.monotonic()) * 1000))
        if not wait_thread(thread, remaining):
            stopped = False
    return stopped
