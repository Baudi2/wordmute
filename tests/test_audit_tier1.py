"""Regression tests for the pre-0.7.0 audit, tier 1: crashes and data
loss. Each test names the bug it pins."""

import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThread

from wordmute_app.core.jobs import JobOptions, QueueItem
from wordmute_app.engine import wordmute as engine
from wordmute_app.ui.threads import (detach_thread, shutdown_detached,
                                     wait_thread)


def _worker(files, monkeypatch, output_dir=None):
    from wordmute_app.ui.worker import ProcessWorker

    monkeypatch.setattr(engine, "transcribe",
                        lambda *a, **k: [{"w": "бог", "s": 1.0, "e": 1.5}])
    def fake_mute(media, iv, out, beep_hz=None):
        Path(out).write_bytes(b"muted")
        engine._emit("mute_done", out=str(out))   # as the real one does

    monkeypatch.setattr(engine, "mute", fake_mute)
    items = [QueueItem(kind="file", path=f) for f in files]
    worker = ProcessWorker(items, ({"бог"}, [], [], []),
                           [("whisper", "small")], JobOptions(device="cpu"),
                           output_dir=output_dir)
    log = {"files": [], "finished": [], "events": []}
    worker.file_finished.connect(
        lambda i, ok, err: log["files"].append((i, ok, err)))
    worker.all_finished.connect(lambda d, t: log["finished"].append((d, t)))
    worker.engine_event.connect(lambda e, d: log["events"].append((e, d)))
    return worker, log


# ---------------------------------------------------------------- worker
def test_unreachable_output_folder_fails_every_item_visibly(qapp, tmp_path,
                                                            monkeypatch):
    """mkdir of the output folder sat OUTSIDE the worker's try/finally:
    an unplugged drive killed the thread with all_finished never
    emitted — the window stayed «running» forever."""
    blocker = tmp_path / "file.txt"
    blocker.write_text("not a folder")
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.touch()
    b.touch()
    worker, log = _worker([a, b], monkeypatch, output_dir=blocker / "out")
    worker.run()
    assert [(i, ok) for i, ok, _ in log["files"]] == [(0, False), (1, False)]
    assert all("Output folder" in err for _, _, err in log["files"])
    assert log["finished"] == [(0, 2)]


def test_folder_mode_same_names_get_distinct_outputs(qapp, tmp_path,
                                                     monkeypatch):
    """Folder output keyed the result by file name alone: S1/01.mp4 and
    S2/01.mp4 overwrote each other's clean file and review sidecar."""
    s1, s2 = tmp_path / "S1", tmp_path / "S2"
    s1.mkdir()
    s2.mkdir()
    (s1 / "01.mp4").touch()
    (s2 / "01.mp4").touch()
    out_dir = tmp_path / "clean"
    worker, log = _worker([s1 / "01.mp4", s2 / "01.mp4"], monkeypatch,
                          output_dir=out_dir)
    worker.run()
    assert [ok for _, ok, _ in log["files"]] == [True, True]
    outputs = sorted(p.name for p in out_dir.glob("*.clean.mp4"))
    assert outputs == ["01 (2).clean.mp4", "01.clean.mp4"]
    emitted = [d["path"] for e, d in log["events"] if e == "item_output"]
    assert len(set(emitted)) == 2


# ---------------------------------------------------------------- engine
def test_mp3_output_uses_an_mp3_codec():
    """AAC forced into the mp3 container failed every .mp3 input at
    the mute stage («Invalid audio stream», code -22)."""
    args = engine._audio_codec_args(Path("talk.clean.mp3"))
    assert "libmp3lame" in args
    assert "aac" in engine._audio_codec_args(Path("talk.clean.mp4"))


def test_ffmpeg_child_is_killed_when_the_reporter_cancels(tmp_path,
                                                          monkeypatch):
    """A cancel raised from mute_progress used to leave ffmpeg running
    to completion in the background (a full-size .tmp next to the
    video, and a restarted run writing the same file under it)."""
    marker = tmp_path / "child-finished.txt"
    script = ("import sys, time\n"
              "print('out_time=00:00:01.000000', flush=True)\n"
              "time.sleep(6)\n"
              f"open({str(marker)!r}, 'w').write('x')\n")
    cmd = [sys.executable, "-c", script]

    class Cancelled(Exception):
        pass

    def reporter(event, data):
        if event == "mute_progress":
            raise Cancelled()

    monkeypatch.setattr(engine, "_reporter", reporter)
    started = time.monotonic()
    with pytest.raises(Cancelled):
        engine._run_ffmpeg_with_progress(cmd)
    assert time.monotonic() - started < 4      # did not wait out the sleep
    time.sleep(0.5)
    assert not marker.exists()                  # the child is dead


def test_failed_mute_leaves_no_tmp_file(tmp_path, monkeypatch):
    src = tmp_path / "v.mp4"
    src.touch()
    out = tmp_path / "v.clean.mp4"

    def failing_mute(media, intervals, tmp, beep_hz=None):
        Path(tmp).write_bytes(b"partial")
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(engine, "transcribe",
                        lambda *a, **k: [{"w": "бог", "s": 1.0, "e": 1.5}])
    monkeypatch.setattr(engine, "mute", failing_mute)
    args = JobOptions(device="cpu")
    with pytest.raises(RuntimeError):
        engine.process_file(src, out, ({"бог"}, [], [], []), args,
                            [("whisper", "small")])
    assert not list(tmp_path.glob("*.tmp.*"))


# ---------------------------------------------------------------- threads
class _Sleeper(QThread):
    def run(self):
        time.sleep(0.4)


def test_wait_thread_reports_timeout_and_stragglers_are_detached(qapp):
    """Close paths used to wait with a timeout and then destroy the
    owner regardless — a still-running QThread aborts the process."""
    from PySide6.QtCore import QObject
    from wordmute_app.ui.threads import start_thread
    owner = QObject()
    thread = _Sleeper()
    start_thread(owner, thread)
    assert wait_thread(thread, 10) is False
    detach_thread(thread)
    assert thread.parent() is None
    assert shutdown_detached(10) is False
    assert shutdown_detached(3000) is True


def test_add_url_dialog_close_detaches_a_running_fetch(qapp, monkeypatch):
    """Cancel/Esc while the format list loads destroyed the dialog with
    its fetch thread alive (yt-dlp has no cancel) → process abort."""
    from wordmute_app.core import downloader
    from wordmute_app.ui.url_dialog import AddUrlDialog

    def slow_list(url, cookies=None):
        time.sleep(0.4)
        return {"title": "t", "formats": [], "duration": 1}

    monkeypatch.setattr(downloader, "list_formats", slow_list)
    dialog = AddUrlDialog(auto_fetch=False)
    dialog.url_edit.setPlainText("https://example.com/v")
    dialog._auto_fetch = True
    dialog._fetch()
    assert len(dialog._fetchers) == 1
    worker = dialog._fetchers[0]
    dialog.reject()                       # Esc / Cancel
    assert dialog._fetchers == []
    assert worker.parent() is None        # detached, not destroyed
    assert shutdown_detached(3000) is True


def test_review_dialog_escape_goes_through_close_event(qapp, tmp_path,
                                                       monkeypatch):
    """QDialog.reject() skips closeEvent; with WA_DeleteOnClose that
    destroyed the dialog under a running re-render."""
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
    path = review.save_review(source, output, 100, [
        {"s": 1.0, "e": 1.5, "text": "бог", "pass": 1, "engine": "whisper",
         "muted": True}])
    dialog = review_dialog.ReviewDialog(path)
    seen = []
    original = review_dialog.ReviewDialog.closeEvent
    monkeypatch.setattr(review_dialog.ReviewDialog, "closeEvent",
                        lambda self, e: (seen.append(1), original(self, e)))
    dialog._worker = object()             # a re-render "in flight"
    dialog.reject()
    assert seen == [1]
    assert "Re-render in progress" in dialog.status_label.text()
    dialog._worker = None
    assert dialog.close() is True


def test_recycle_bin_warns_where_there_is_no_bin():
    from wordmute_app.core import cleanup
    assert cleanup._FOF_WANTNUKEWARNING == 0x4000
