"""A pass count of their own for English videos. With the main plan
GigaAM ×2 → Whisper, a video set to «Язык обработки → Английский» ran
Whisper ×3 (GigaAM can't do English, so its passes became Whisper
ones) — an hour of extra recognition, and no way to ask for two."""

import pytest

from wordmute_app.core import config
from wordmute_app.core.jobs import (ENGLISH_PASSES_MAX, QueueItem,
                                    english_plan)

MAIN = [("gigaam", "v3_rnnt"), ("gigaam", "v3_rnnt"), ("whisper", "large-v3")]


def test_english_plan_is_whisper_only_with_its_own_count():
    assert english_plan(MAIN, 2, "large-v3") == [("whisper", "large-v3")] * 2
    assert english_plan(MAIN, 1, "small") == [("whisper", "small")]
    # 0 = follow the main plan's count (how it worked before)
    assert english_plan(MAIN, 0, "large-v3") == [("whisper", "large-v3")] * 3
    assert english_plan(MAIN, None, "large-v3") == \
        [("whisper", "large-v3")] * 3
    # junk from a hand-edited settings file never breaks a run
    assert len(english_plan(MAIN, "x", "m")) == 3
    assert len(english_plan(MAIN, -4, "m")) == 3
    assert len(english_plan(MAIN, 99, "m")) == ENGLISH_PASSES_MAX


def test_default_follows_the_plan():
    assert config.DEFAULT_SETTINGS["english_passes"] == 0


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui import main_window as mw

    captured = {}

    class DummySignal:
        def connect(self, *a, **k):
            pass

    from PySide6.QtCore import QObject

    class FakeWorker(QObject):   # QObject: start_thread parents it
        def __init__(self, items, wordlist, plan, options, **kw):
            super().__init__()
            captured.update(items=list(items), plan=plan, **kw)
            for name in ("engine_event", "file_started", "file_finished",
                         "all_finished", "finished"):
                setattr(self, name, DummySignal())

        def start(self):
            pass

    monkeypatch.setattr(mw, "ProcessWorker", FakeWorker)
    monkeypatch.setattr(mw.MainWindow, "_gigaam_installed",
                        staticmethod(lambda: True))
    w = mw.MainWindow()
    w.plan.set_engines(["gigaam", "gigaam", "whisper"])
    yield w, captured, tmp_path
    w._worker = None          # fake worker: nothing to wait for on close
    w.close()


def _queue(w, tmp_path, *profiles):
    from wordmute_app.ui.main_window import ITEM_ROLE
    for n, profile in enumerate(profiles):
        f = tmp_path / f"v{n}.mp4"
        f.touch()
        w._add_files([f])
        w.queue.item(n).data(ITEM_ROLE).lang_profile = profile


def test_the_choice_reaches_the_english_profile(window):
    w, captured, tmp_path = window
    w.plan.set_english_passes(2)
    _queue(w, tmp_path, "auto", "en")
    w._start()
    whisper = w._settings["model"]
    assert [e for e, _ in captured["plan"]] == ["gigaam", "gigaam", "whisper"]
    assert captured["profiles"]["en"][1] == [("whisper", whisper)] * 2
    assert captured["profiles"]["en"][2] == "en"
    # the Russian profile keeps the main plan
    assert captured["profiles"]["ru"][1] == captured["plan"]
    assert "English videos: whisper(" in w.log.toPlainText()


def test_following_the_plan_keeps_the_old_behaviour(window):
    w, captured, tmp_path = window
    assert w.plan.english_passes() == 0
    _queue(w, tmp_path, "en")
    w._start()
    assert len(captured["profiles"]["en"][1]) == 3
    assert {e for e, _ in captured["profiles"]["en"][1]} == {"whisper"}


def test_the_card_counts_its_own_passes(window):
    w, captured, tmp_path = window
    w.plan.set_english_passes(2)
    _queue(w, tmp_path, "auto", "en")
    w._start()
    w._on_file_started(0, "v0.mp4")
    assert w._pass_total == 3
    assert w._pass_prefix() == "pass 1/3 · "
    w._on_file_started(1, "v1.mp4")
    assert w._pass_total == 2
    assert w._pass_prefix() == "pass 1/2 · "


def test_summary_and_combo_follow_the_plan(window):
    w, captured, tmp_path = window
    combo = w.plan.english_combo
    assert combo.itemText(0) == "same as the plan: Whisper ×3"
    assert [combo.itemText(i) for i in range(1, combo.count())] == [
        f"Whisper ×{n}" for n in range(1, ENGLISH_PASSES_MAX + 1)]
    assert "EN ×" not in w.setup_summary.text()
    w.plan.remove_pass(0)
    assert combo.itemText(0) == "same as the plan: Whisper ×2"
    w.plan.set_english_passes(1)
    assert "(EN ×1)" in w.setup_summary.text()
    w.plan.set_english_passes(0)
    assert "EN ×" not in w.setup_summary.text()


def test_the_choice_is_remembered(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    first = MainWindow()
    first.plan.set_english_passes(2)
    first.close()
    assert config.load_settings()["english_passes"] == 2
    second = MainWindow()
    assert second.plan.english_passes() == 2
    assert second.plan.english_combo.currentText() == "Whisper ×2"
    second.close()


def test_strings_are_translated(qapp):
    from wordmute_app.ui import i18n
    from wordmute_app.ui.plan_widget import PassPlanWidget

    i18n.set_language("ru")
    try:
        plan = PassPlanWidget()
        plan.set_engines(["gigaam", "whisper"])
        assert plan.english_combo.itemText(0) == "как в плане: Whisper ×2"
        assert "GigaAM не понимает" in plan.english_combo.toolTip()
        assert i18n.tr("English videos:") == "Английские видео:"
    finally:
        i18n.set_language("en")
