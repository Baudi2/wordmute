"""Regression tests for the pre-0.7.0 audit, tier 2: hangs, broken
installs and misleading states."""

import json
import os
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint

from wordmute_app.core import config
from wordmute_app.core.jobs import JobOptions, QueueItem
from wordmute_app.engine import wordmute as engine


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    return MainWindow()


# ------------------------------------------------------------- queue/URLs
def test_url_key_merges_spellings_of_one_video(qapp):
    from wordmute_app.ui.main_window import MainWindow
    key = MainWindow._url_key
    assert key("https://youtu.be/abc123 ") == key(
        "https://www.youtube.com/watch?v=abc123&t=10s")
    assert key("https://m.youtube.com/watch?v=abc123") == "yt:abc123"
    assert key("https://rutube.ru/video/x/#frag") == "https://rutube.ru/video/x/"
    assert key("https://a/1") != key("https://a/2")


def test_same_url_is_queued_once(qapp, tmp_path, monkeypatch):
    """Two items for one video downloaded into ONE file while the
    first was being processed."""
    w = _window(tmp_path, monkeypatch)
    for url in ("https://youtu.be/abc123",
                "https://www.youtube.com/watch?v=abc123"):
        w._add_url_row(QueueItem(kind="url", url=url, format_spec="b",
                                 format_label="best"))
    assert w.queue.count() == 1


def test_start_asks_to_save_unsaved_word_list(qapp, tmp_path, monkeypatch):
    """The run reads the lists from disk: an unsaved entry the tester
    just confirmed was silently not muted. no_modal_dialogs answers
    Cancel, so Start must back out."""
    w = _window(tmp_path, monkeypatch)
    f = tmp_path / "v.mp4"
    f.touch()
    w._add_files([f])
    w.wordlists_tab.editor.appendPlainText("новоеслово")
    assert w.wordlists_tab.has_unsaved()
    w._start()
    assert w._worker is None
    assert w.wordlists_tab.has_unsaved()


# --------------------------------------------------------------- worker
def _worker(files, monkeypatch, words):
    from wordmute_app.ui.worker import ProcessWorker
    monkeypatch.setattr(engine, "transcribe", lambda *a, **k: words)
    monkeypatch.setattr(engine, "mute",
                        lambda media, iv, out, beep_hz=None:
                        Path(out).write_bytes(b"muted"))
    items = [QueueItem(kind="file", path=f) for f in files]
    worker = ProcessWorker(items, ({"бог"}, [], [], []),
                           [("whisper", "small")], JobOptions(device="cpu"))
    log = {"files": [], "events": []}
    worker.file_finished.connect(
        lambda i, ok, err: log["files"].append((i, ok, err)))
    worker.engine_event.connect(lambda e, d: log["events"].append((e, d)))
    return worker, log


def test_stale_clean_file_is_not_this_runs_result(qapp, tmp_path,
                                                  monkeypatch):
    """A .clean left by an earlier run (older word list) was presented
    as the result of a run that matched nothing."""
    src = tmp_path / "v.mp4"
    src.touch()
    (tmp_path / "v.clean.mp4").write_bytes(b"old mutes")
    worker, log = _worker([src], monkeypatch,
                          [{"w": "привет", "s": 1.0, "e": 1.5}])
    worker.run()
    assert log["files"] == [(0, True, "")]
    assert not [e for e, _ in log["events"] if e == "item_output"]


def test_worker_hands_the_reporter_back(qapp, tmp_path, monkeypatch):
    """Start during a review re-render replaced the process-global
    reporter outright and reset it to the default afterwards."""
    seen = []
    previous = lambda event, data: seen.append(event)   # noqa: E731
    engine.set_reporter(previous)
    try:
        src = tmp_path / "v.mp4"
        src.touch()
        worker, _ = _worker([src], monkeypatch,
                            [{"w": "бог", "s": 1.0, "e": 1.5}])
        worker.run()
        assert engine._reporter is previous
    finally:
        engine.set_reporter(None)


# ---------------------------------------------------------- transcripts
def test_transcript_cache_stale_or_unreadable_is_a_miss(tmp_path):
    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    cache = engine._cache_path(media, "whisper")
    words = [{"w": "бог", "s": 1.0, "e": 1.5}]
    cache.write_text(json.dumps(words), encoding="utf-8")
    old = time.time() - 100
    os.utime(media, (old, old))
    assert engine._load_cache(cache, media) == words
    # the media was re-exported after the cache was written
    os.utime(media, None)
    os.utime(cache, (old, old))
    assert engine._load_cache(cache, media) is None
    # truncated by a crash mid-write
    os.utime(media, (old, old))
    cache.write_text('[{"w": "бо', encoding="utf-8")
    assert engine._load_cache(cache, media) is None


# ----------------------------------------------------------- settings
def test_corrupt_settings_are_set_aside_not_silently_replaced(tmp_path,
                                                              monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = config._settings_path()
    path.write_text("{broken", encoding="utf-8")
    settings = config.load_settings()
    assert settings["model"] == config.DEFAULT_SETTINGS["model"]
    assert not path.exists()
    assert list(path.parent.glob("settings.broken-*.json"))
    config.save_settings(settings)
    assert json.loads(path.read_text(encoding="utf-8"))["model"]
    assert not list(path.parent.glob("*.tmp"))      # atomic write


# ------------------------------------------------------------ install
def test_package_installed_requires_pips_record(tmp_path, monkeypatch):
    """A half-unpacked package (cancelled pip) passed the first-run
    gate; the wizard never came back."""
    from wordmute_app.core import runtime_env
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    site = runtime_env.site_packages()
    (site / "faster_whisper").mkdir(parents=True)
    assert runtime_env.package_installed("faster_whisper") is False
    info = site / "faster_whisper-1.2.1.dist-info"
    info.mkdir()
    (info / "RECORD").write_text("", encoding="utf-8")
    assert runtime_env.package_installed("faster_whisper") is True


def test_model_cache_with_an_incomplete_blob_is_not_downloaded(tmp_path):
    from wordmute_app.core import models
    d = tmp_path / "models--x"
    (d / "snapshots").mkdir(parents=True)
    (d / "blobs").mkdir()
    assert models.model_cache_complete(d) is True
    (d / "blobs" / "abc.incomplete").touch()
    assert models.model_cache_complete(d) is False


# ------------------------------------------------------------- reorder
def test_abort_during_the_landing_animation_commits(qapp):
    """QAbstractAnimation.stop() mid-flight does not emit finished:
    abort() left the lift floating and the viewport's mouse grab held
    — the whole window went mouse-dead."""
    from wordmute_app.ui.plan_widget import PassPlanWidget
    plan = PassPlanWidget()
    plan.resize(400, 300)
    plan.show()
    for _ in range(3):
        qapp.processEvents()
    plan.set_engines(["whisper", "gigaam"])
    for _ in range(3):
        qapp.processEvents()
    ctrl = plan._reorder
    ctrl._land_ms = 400
    ctrl._slide_ms = 0
    lst = plan.chips
    ctrl._begin(0, lst.visualItemRect(lst.item(0)).center())
    ctrl._drag_to(lst.visualItemRect(lst.item(1)).center() + QPoint(0, 8))
    ctrl._settle(cancel=False)
    assert ctrl._landing
    ctrl.abort()
    assert not ctrl._landing and ctrl._src == -1
    assert plan.engines() == ["gigaam", "whisper"]
    assert lst.viewport().mouseGrabber() is None


# ------------------------------------------------------------- updates
def test_release_url_must_be_github_https(monkeypatch):
    from wordmute_app.core import updates
    import io

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payload = json.dumps({"tag_name": "v9.9.9",
                          "html_url": "file:///C:/evil.exe"}).encode()
    monkeypatch.setattr(updates.urllib.request, "urlopen",
                        lambda request, timeout=15: Response(payload))
    result = updates.check_app_update()
    assert result["latest"] == "9.9.9"
    assert result["url"] == updates.APP_RELEASES_URL
