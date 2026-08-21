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
Qt-only imports on purpose: the setup wizard uses this before the
engine packages exist."""

from PySide6.QtCore import QObject, QThread


def start_thread(owner: QObject, thread: QThread) -> QThread:
    """Parent `thread` to `owner`, free it after it finishes, start it."""
    thread.setParent(owner)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


def wait_thread(thread, msecs: int = None) -> None:
    """wait() on a worker started with start_thread — tolerating None
    and one Qt has already deleted (finished → deleteLater)."""
    if thread is None:
        return
    try:
        if msecs is None:
            thread.wait()
        else:
            thread.wait(msecs)
    except RuntimeError:   # "Internal C++ object already deleted"
        pass
