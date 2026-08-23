"""Regression tests for the pre-0.7.0 audit, tier 3: diagnostics and
practices."""

import sys
import threading
import time

from PySide6.QtCore import QThread

from wordmute_app.ui.threads import shutdown_detached


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    return MainWindow()


# ------------------------------------------------------------ crash log
def test_crash_log_collects_tracebacks_from_every_thread(tmp_path,
                                                         monkeypatch):
    """Until now stderr went to devnull in the windowed build: a slot
    exception, a dead worker or Qt's fatal message left no trace."""
    import faulthandler
    from wordmute_app import main

    monkeypatch.setenv("APPDATA", str(tmp_path))
    old_hooks = (sys.excepthook, threading.excepthook)
    handle = main._install_crash_log()
    try:
        assert handle is not None
        assert faulthandler.is_enabled()
        try:
            raise ZeroDivisionError("main thread boom")
        except ZeroDivisionError:
            sys.excepthook(*sys.exc_info())

        def worker():
            raise KeyError("worker boom")

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        log = (tmp_path / "WordMute" / main.LOG_NAME).read_text(
            encoding="utf-8")
        assert "=== WordMute" in log
        assert "ZeroDivisionError: main thread boom" in log
        assert "KeyError: 'worker boom'" in log
    finally:
        sys.excepthook, threading.excepthook = old_hooks
        faulthandler.disable()
        if handle is not None:
            handle.close()
        main._log_handle = None


# ----------------------------------------------------------- close path
class _StuckWorker(QThread):
    """A ProcessWorker that ignores cancel for longer than the close
    budget — model loading, a stalled download."""

    def __init__(self):
        super().__init__()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        time.sleep(0.8)


def test_closing_with_a_stuck_worker_detaches_it(qapp, tmp_path,
                                                 monkeypatch, confirm_yes):
    """The window used to wait 15 s and then be destroyed with the
    thread still running — Qt aborts the process. Now the straggler is
    detached and collected at exit."""
    from wordmute_app.ui.threads import start_thread, wait_thread
    # only the window's close-time budget shrinks; shutdown_detached
    # below must keep its real wait
    from wordmute_app.ui import main_window as mw
    monkeypatch.setattr(mw, "wait_thread",
                        lambda thread, msecs=None: wait_thread(thread, 10))
    w = _window(tmp_path, monkeypatch)
    worker = _StuckWorker()
    start_thread(w, worker)
    w._worker = worker
    assert w.close() is True
    assert worker.cancelled
    assert worker.parent() is None          # detached, not destroyed
    assert shutdown_detached(3000) is True


# ----------------------------------------------------------- balloons
def test_balloon_click_runs_only_the_latest_action(qapp, tmp_path,
                                                   monkeypatch):
    """messageClicked fires for ANY balloon: the «Finished» balloon
    used to open the GitHub page when an update balloon had been shown
    earlier."""
    w = _window(tmp_path, monkeypatch)

    class FakeTray:
        def __init__(self):
            self.shown = []

        def showMessage(self, *args):
            self.shown.append(args)

    w._tray = FakeTray()
    calls = []
    w._show_balloon("update", lambda: calls.append("update"), 10)
    w._show_balloon("finished", lambda: calls.append("finished"), 10)
    w._on_balloon_clicked()
    w._on_balloon_clicked()                 # a second click does nothing
    assert calls == ["finished"]
    assert len(w._tray.shown) == 2


# ------------------------------------------------------------- review
def test_moved_sidecar_targets_the_moved_output(qapp, tmp_path, monkeypatch):
    """Re-render wrote to the absolute output path recorded at
    processing time, so a clean file renamed together with its sidecar
    stayed untouched while the dialog said «Output updated»."""
    from wordmute_app.core import review
    from wordmute_app.ui import review_dialog

    class DummyPlayer:
        def play(self, *a): pass
        def stop(self): pass
        def dispose(self): pass

    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    source = tmp_path / "v.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "v.clean.mp4"
    output.write_bytes(b"y")
    sidecar = review.save_review(source, output, 100, [
        {"s": 1.0, "e": 1.5, "text": "бог", "pass": 1, "engine": "whisper",
         "muted": True}])
    moved_out = tmp_path / "final.mp4"
    output.rename(moved_out)
    moved_sidecar = review.review_path_for(moved_out)
    sidecar.rename(moved_sidecar)
    dialog = review_dialog.ReviewDialog(moved_sidecar)
    assert dialog._data["output"] == str(moved_out)


# --------------------------------------------------------------- i18n
def test_gpu_warnings_are_translated_and_severity_survives(qapp, tmp_path,
                                                           monkeypatch):
    """Severity was detected on the displayed text («will fail»), so a
    translated warning could never be severe — and gpu.py's warnings
    never reached tr() at all."""
    from wordmute_app.ui import i18n
    w = _window(tmp_path, monkeypatch)
    w._settings["device"] = "cuda"          # and no GPU detected
    i18n.set_language("ru")
    try:
        w._refresh_warnings()
        text = w.warnings_label.text()
        assert "Видеокарта NVIDIA не найдена" in text
        assert "will fail" not in text
        assert w.warnings_label.property("severity") == "error"
    finally:
        i18n.set_language("en")


def test_error_status_is_translated_and_retry_follows_state(qapp, tmp_path,
                                                            monkeypatch):
    from wordmute_app.ui import i18n
    w = _window(tmp_path, monkeypatch)
    f = tmp_path / "v.mp4"
    f.touch()
    w._add_files([f])
    i18n.set_language("ru")
    try:
        w._active_rows = [0]
        w._on_file_finished(0, False, "boom")
        assert w.status_text(0).startswith("ошибка: boom")
        card = w._card(0)
        assert card.retry_button.isVisibleTo(card)
    finally:
        i18n.set_language("en")
