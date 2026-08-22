"""Worker lifetime: dropping the last Python reference to a QThread in
the slot of its final signal used to abort the process ("QThread:
Destroyed while thread is still running") — a tight loop of the old
pattern died within ~20 iterations. start_thread() must survive the
same loop. If this regresses, the whole pytest process aborts — that
IS the failure mode."""

from PySide6.QtCore import QObject, QThread, Signal

from wordmute_app.ui.threads import start_thread, wait_thread

DEFERRED_DELETE = 52   # QEvent.DeferredDelete


class _Ping(QThread):
    result = Signal(object)

    def run(self):
        self.result.emit(1)


class _Owner(QObject):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.done = 0

    def start(self):
        self.worker = _Ping()
        self.worker.result.connect(self._on_result)
        start_thread(self, self.worker)

    def _on_result(self, _):
        self.worker = None          # the app's pattern, now safe
        self.done += 1


def test_dropping_reference_in_result_slot_survives(qapp):
    owner = _Owner()
    for i in range(300):
        owner.start()
        while owner.done == i:
            qapp.processEvents()
        qapp.sendPostedEvents(None, DEFERRED_DELETE)   # like an idle loop
    assert owner.done == 300


def test_wait_thread_tolerates_none_and_deleted(qapp):
    wait_thread(None)                      # nothing running: no-op
    owner = _Owner()
    worker = _Ping()
    start_thread(owner, worker)
    assert worker.wait(5000)
    qapp.processEvents()
    qapp.sendPostedEvents(None, DEFERRED_DELETE)   # deleteLater ran
    wait_thread(worker, 100)               # "already deleted" swallowed
